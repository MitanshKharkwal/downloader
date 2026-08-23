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

import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Ensure we can type hint DownloadManager without circular imports
from typing import TYPE_CHECKING
from core.models import Priority

if TYPE_CHECKING:
    from core.manager import DownloadManager

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


def _make_handler(manager: DownloadManager, token: str):
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
            provided = self.headers.get("X-Auth-Token", "")
            return hmac.compare_digest(provided, token)

        def do_GET(self):
            if self.path == "/ping":
                self._send_json(200, {"ok": True, "app": "download-manager"})
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self._authorized():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, ValueError):
                self._send_json(400, {"ok": False, "error": "invalid JSON"})
                return

            # Legacy support for browser extension
            if self.path == "/add":
                if "source" not in body:
                    self._send_json(
                        400,
                        {
                            "ok": False,
                            "error": "expected JSON body with a 'source' field",
                        },
                    )
                    return
                try:
                    filename = body.get("filename")
                    headers = body.get("headers")
                    result = manager.add(
                        body["source"], filename=filename, headers=headers
                    )
                    self._send_json(200, {"ok": True, **result.to_dict()})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            # New JSON-RPC for C# frontend
            if self.path == "/rpc":
                method = body.get("method")
                args = body.get("args", {})

                try:
                    if method == "list_tasks":
                        tasks = []
                        for task in manager.list_tasks():
                            tasks.append(
                                {
                                    "id": task.id,
                                    "source": task.source,
                                    "status": task.status.value.upper(),
                                    "priority": task.priority.value,
                                    "downloaded_bytes": task.downloaded_bytes or 0,
                                    "total_bytes": task.total_bytes or 0,
                                    "speed_bps": task.speed_bps or 0.0,
                                    "file_path": task.dest_path or "",
                                    "error": task.error_message or "",
                                    "category": getattr(task, "category", "") or "",
                                    "created_at": task.created_at or 0,
                                    "description": task.description or "",
                                }
                            )
                        self._send_json(200, {"ok": True, "tasks": tasks})
                    elif method == "add_video_task":
                        # source format: ytdlp||format_id||url
                        url = args["url"]
                        format_id = args.get("format_id", "best")
                        source = f"ytdlp||{format_id}||{url}"
                        # Need to bypass manager.add since it assumes HTTP or Torrent based on regex/extension
                        # Let's just create a DownloadTask and insert it directly
                        from core.models import DownloadTask, DownloadType

                        name = args.get("filename", "video.mp4")
                        final_dest_dir = os.path.join(manager.download_dir, "Video")
                        os.makedirs(final_dest_dir, exist_ok=True)
                        base, ext = os.path.splitext(name)
                        target_path = os.path.join(final_dest_dir, name)
                        counter = 1
                        while os.path.exists(target_path) or os.path.exists(
                            target_path + ".dmpart"
                        ):
                            target_path = os.path.join(
                                final_dest_dir, f"{base} ({counter}){ext}"
                            )
                            counter += 1

                        task = DownloadTask(
                            source=source,
                            dest_path=target_path,
                            type=DownloadType.VIDEO,
                        )
                        with manager._lock:
                            manager._tasks[task.id] = task
                        manager._save_state()
                        manager.events.emit("added", task)
                        manager._maybe_start_next()
                        self._send_json(200, {"ok": True, "id": task.id})

                    elif method == "fetch_video_info":
                        import yt_dlp

                        url = args.get("url")
                        ydl_opts = {"quiet": True, "no_warnings": True}
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=False)
                                self._send_json(
                                    200,
                                    {"ok": True, "title": info.get("title", "Video")},
                                )
                        except Exception as e:
                            self._send_json(500, {"ok": False, "error": str(e)})

                    elif method == "pause":
                        manager.pause(args["task_id"])
                        self._send_json(200, {"ok": True})
                    elif method == "resume":
                        task_id = args.get("task_id")
                        if task_id:
                            manager.resume(task_id)
                        self._send_json(200, {"ok": True})
                    elif method == "retry":
                        task_id = args.get("task_id")
                        if task_id:
                            manager.retry(task_id)
                        self._send_json(200, {"ok": True})
                    elif method == "pause_all":
                        manager.pause_all()
                        self._send_json(200, {"ok": True})
                    elif method == "resume_all":
                        manager.resume_all()
                        self._send_json(200, {"ok": True})
                    elif method == "cancel":
                        manager.cancel(args["task_id"])
                        self._send_json(200, {"ok": True})
                    elif method == "set_priority":
                        task_id = args.get("task_id")
                        priority_raw = args.get("priority")
                        if not task_id or priority_raw is None:
                            self._send_json(
                                400,
                                {
                                    "ok": False,
                                    "error": "Missing task_id or priority",
                                },
                            )
                            return
                        try:
                            priority = Priority(int(priority_raw))
                        except (ValueError, TypeError):
                            self._send_json(
                                400,
                                {
                                    "ok": False,
                                    "error": f"Invalid priority: {priority_raw}",
                                },
                            )
                            return
                        manager.set_priority(task_id, priority)
                        self._send_json(200, {"ok": True})
                    elif method == "clear_finished":
                        manager.clear_finished()
                        self._send_json(200, {"ok": True})
                    elif method == "remove_task":
                        task_id = args.get("task_id")
                        delete_files = args.get("delete_files", False)
                        if task_id:
                            manager.remove_task(task_id, delete_files)
                        self._send_json(200, {"ok": True})
                    elif method == "shutdown":
                        manager.shutdown()
                        self._send_json(200, {"ok": True})
                        import threading

                        threading.Timer(0.5, lambda: __import__("os")._exit(0)).start()
                    elif method == "get_config":
                        self._send_json(
                            200, {"ok": True, "config": manager.get_config()}
                        )
                    elif method == "set_config":
                        manager.set_config(args.get("config", {}))
                        self._send_json(200, {"ok": True})
                    else:
                        self._send_json(400, {"ok": False, "error": "unknown method"})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            self._send_json(404, {"ok": False, "error": "not found"})

    return Handler


class IpcServer:
    """Runs on a background thread inside the desktop app process."""

    def __init__(
        self, manager: DownloadManager, token: str, port: int = DEFAULT_PORT
    ) -> None:
        self.port = port
        self._server = HTTPServer(("127.0.0.1", port), _make_handler(manager, token))
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
