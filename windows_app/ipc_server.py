"""Local IPC server for the desktop app.

The browser extension can't talk to a Python object living inside our
GUI process directly -- it talks to a native messaging host, which is
a short-lived subprocess Chrome spawns per connection. That host needs
some way to reach the *actual* running app to hand off a URL or
magnet link. A tiny localhost-only HTTP server is the simplest thing
that works reliably across process boundaries and survives us
swapping the native host's implementation later.

Security model: bound to 127.0.0.1 only (never 0.0.0.0), and every
request must include a per-install shared token that only the app and
the native host manifest are supposed to know, so an arbitrary local
process/webpage can't queue downloads into the app.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

DEFAULT_PORT = 47821


def load_or_create_token(token_path: str) -> str:
    if os.path.exists(token_path):
        with open(token_path) as f:
            token = f.read().strip()
        if token:
            return token
    token = secrets.token_hex(24)
    os.makedirs(os.path.dirname(os.path.abspath(token_path)) or ".", exist_ok=True)
    with open(token_path, "w") as f:
        f.write(token)
    return token


def _make_handler(add_callback: Callable[[str], dict], token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep the app's console quiet; the GUI shows status instead

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return self.headers.get("X-Auth-Token") == token

        def do_GET(self):
            if self.path == "/ping":
                self._send_json(200, {"ok": True, "app": "download-manager"})
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if self.path != "/add":
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            if not self._authorized():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                source = body["source"]
            except (json.JSONDecodeError, KeyError, ValueError):
                self._send_json(400, {"ok": False, "error": "expected JSON body with a 'source' field"})
                return

            try:
                result = add_callback(source)
                self._send_json(200, {"ok": True, **result})
            except Exception as exc:  # noqa: BLE001 - report, don't crash the server
                self._send_json(500, {"ok": False, "error": str(exc)})

    return Handler


class IpcServer:
    """Runs on a background thread inside the desktop app process."""

    def __init__(self, add_callback: Callable[[str], dict], token: str, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self._server = HTTPServer(("127.0.0.1", port), _make_handler(add_callback, token))
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
