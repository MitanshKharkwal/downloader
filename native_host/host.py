#!/usr/bin/env python3
"""Native messaging host for the browser extension.

Chrome launches this as a short-lived subprocess whenever the
extension calls `chrome.runtime.sendNativeMessage`: it writes one
length-prefixed JSON message to our stdin, we write one length-prefixed
JSON response to stdout, and Chrome kills the process. See:
https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging

This process's only job is translating that into a plain HTTP POST to
the desktop app's local IPC server (see windows_app/ipc_server.py). If
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

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")
IPC_PORT = 47821  # must match windows_app/ipc_server.py's DEFAULT_PORT
LAUNCH_CMD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_launch_command.txt")


def read_message() -> dict:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)  # Chrome closed the pipe
    length = struct.unpack("=I", raw_length)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


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
    """Best-effort: if a launch command has been configured, start the
    app. Silent no-op if it hasn't -- the caller just won't get a
    successful retry and will report a clear error instead."""
    if not os.path.exists(LAUNCH_CMD_FILE):
        return
    with open(LAUNCH_CMD_FILE) as f:
        cmd = f.read().strip()
    if cmd:
        try:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def post_to_app(source: str, filename: str | None = None, retries: int = 5, delay: float = 0.6) -> dict:
    token = _read_token()
    if token is None:
        return {"ok": False, "error": "desktop app has never run -- no IPC token found yet"}

    payload = json.dumps({"source": source, "filename": filename}).encode()
    launched = False

    def _try_once() -> dict | None:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{IPC_PORT}/add",
                data=payload,
                headers={"X-Auth-Token": token, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
            return None

    for _attempt in range(retries):
        result = _try_once()
        if result is not None:
            return result
        if not launched:
            _try_launch_app()
            launched = True
            # A cold Kivy start (GL/font init, etc.) can genuinely take
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

    return {"ok": False, "error": "could not reach the desktop app after retries -- is it running?"}


def handle(message: dict) -> dict:
    action = message.get("action")

    if action == "ping":
        return {"ok": True, "pong": True, "app_token_found": _read_token() is not None}

    if action == "add":
        source = message.get("source")
        if not source:
            return {"ok": False, "error": "missing 'source'"}
        return post_to_app(source, filename=message.get("filename"))

    return {"ok": False, "error": f"unknown action: {action!r}"}


def main() -> None:
    message = read_message()
    send_message(handle(message))


if __name__ == "__main__":
    main()
