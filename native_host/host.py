#!/usr/bin/env python3
"""Native messaging host for the browser extension.

Chrome launches this as a short-lived subprocess whenever the
extension calls `chrome.runtime.sendNativeMessage`: it writes one
length-prefixed JSON message to our stdin, we write one length-prefixed
JSON response to stdout, and Chrome kills the process. See:
https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging

This process's only job is translating that into a plain HTTP POST to
the desktop app's local IPC server (see core/ipc_server.py). If
the app isn't running yet, it tries to launch it (via a configurable
launch command) and retries briefly before giving up.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_DATA_DIR = os.environ.get("DOWNLOAD_MANAGER_DATA_DIR") or os.path.join(
    os.path.expanduser("~"), ".download_manager"
)
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")
IPC_PORT = int(os.environ.get("DOWNLOAD_MANAGER_IPC_PORT", "47821"))


def read_message() -> dict:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)  # Chrome closed the pipe
    if len(raw_length) != 4:
        raise ValueError("Incomplete message header")
    length = struct.unpack("=I", raw_length)[0]
    if length > 1024 * 1024:
        raise ValueError("Message too large")
    data = sys.stdin.buffer.read(length)
    if len(data) != length:
        raise ValueError("Incomplete message")
    message = json.loads(data.decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("Message must be an object")
    return message


def send_message(message: dict) -> None:
    encoded = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _read_token() -> str | None:
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            token = f.read().strip()
        return token or None
    return None


def _try_launch_app() -> None:
    if getattr(sys, "frozen", False):
        root = os.path.dirname(os.path.dirname(sys.executable))
        command = [os.path.join(root, "downloader-daemon.exe")]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        command = [sys.executable, os.path.join(root, "daemon.py")]
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except OSError:
        pass


def _connection_status() -> dict:
    token = _read_token()
    if token is None:
        return {
            "ok": False,
            "pong": True,
            "app_token_found": False,
            "error": "Desktop app has not created an IPC token yet",
        }
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{IPC_PORT}/rpc",
            data=b'{"method":"get_capabilities","args":{}}',
            headers={"X-Auth-Token": token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            connected = json.loads(response.read()).get("ok") is True
        result = {"ok": connected, "pong": True, "app_token_found": True}
        if not connected:
            result["error"] = "Desktop app did not accept the connection check"
        return result
    except urllib.error.HTTPError as exc:
        error = (
            "Desktop app rejected the native host token"
            if exc.code == 401
            else f"Desktop app returned HTTP {exc.code}"
        )
    except (OSError, ValueError):
        error = "Desktop app is not reachable"
    return {"ok": False, "pong": True, "app_token_found": True, "error": error}


def post_to_app(
    source: str,
    filename: str | None = None,
    headers: dict | None = None,
    verify: bool = False,
    retries: int = 5,
    delay: float = 0.6,
) -> dict:
    token = _read_token()
    if token is None:
        _try_launch_app()
        for _ in range(20):
            time.sleep(0.5)
            token = _read_token()
            if token:
                break
    if token is None:
        return {
            "ok": False,
            "error": "desktop app has never run -- no IPC token found yet",
        }

    payload = json.dumps(
        {
            "source": source,
            "filename": filename,
            "headers": headers or {},
            "verify": verify,
        }
    ).encode()
    launched = False

    def _try_once() -> dict | None:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{IPC_PORT}/add",
                data=payload,
                headers={"X-Auth-Token": token, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12 if verify else 2) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
                return json.loads(body)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
            return None

    for _attempt in range(retries):
        result = _try_once()
        if result is not None:
            return result
        if not launched:
            _try_launch_app()
            launched = True
            # A cold start (loading .NET runtime, font init, etc.) can genuinely take
            # several seconds -- give it real time to come up rather than
            # burning through the same short budget used for "app is
            # already running, just being briefly slow to respond".
            for _ in range(12):
                time.sleep(1.0)
                result = _try_once()
                if result is not None:
                    return result
        else:
            time.sleep(delay)

    return {
        "ok": False,
        "error": "could not reach the desktop app after retries -- is it running?",
    }


def handle(message: dict) -> dict:
    action = message.get("action")

    if action == "ping":
        return _connection_status()

    if action == "add":
        source = message.get("source")
        if not source:
            return {"ok": False, "error": "missing 'source'"}
        return post_to_app(
            source,
            filename=message.get("filename"),
            headers=message.get("headers"),
            verify=message.get("verify") is True,
        )

    return {"ok": False, "error": f"unknown action: {action!r}"}


def main() -> None:
    try:
        message = read_message()
        send_message(handle(message))
    except (ValueError, OSError) as exc:
        send_message({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
