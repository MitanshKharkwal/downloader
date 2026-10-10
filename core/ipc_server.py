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
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Ensure we can type hint DownloadManager without circular imports
from typing import TYPE_CHECKING

from core.models import Priority
from core.updater import check_for_update, download_update, install_update
from core.version import APP_VERSION

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
    fd = os.open(token_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
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

            try:
                length = int(self.headers.get("Content-Length", 0))
                if length < 0 or length > 1024 * 1024:
                    self._send_json(413, {"ok": False, "error": "Request too large"})
                    return
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict) or not isinstance(body.get("args", {}), dict):
                    raise ValueError("Expected an object")
            except (json.JSONDecodeError, ValueError, TimeoutError):
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
                    result = manager.add(body["source"], filename=filename, headers=headers)
                    if body.get("verify") is True:
                        deadline = time.monotonic() + 8
                        while result.status.value == "connecting" and time.monotonic() < deadline:
                            time.sleep(0.05)
                        if result.status.value == "error":
                            error = result.error_message or "The source rejected the request"
                            manager.remove_task(result.id, delete_files=True)
                            self._send_json(
                                422,
                                {
                                    "ok": False,
                                    "error": f"{error}. The browser download was left active.",
                                },
                            )
                            return
                    public = {k: v for k, v in result.to_dict().items() if k != "headers"}
                    self._send_json(200, {"ok": True, **public})
                except (ValueError, TypeError, KeyError) as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            if self.path == "/batch_add":
                try:
                    result = manager.add_batch(body.get("items"))
                    self._send_json(200, {"ok": True, **result})
                except (ValueError, TypeError, KeyError) as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            # New JSON-RPC for C# frontend
            if self.path == "/rpc":
                method = body.get("method")
                args = body.get("args", {})

                try:
                    if method == "get_capabilities":
                        self._send_json(
                            200,
                            {
                                "ok": True,
                                "protocol": 2,
                                "version": APP_VERSION,
                                "features": [
                                    "download_health",
                                    "download_all",
                                    "safety_scan",
                                    "signed_updates",
                                ],
                            },
                        )
                    elif method == "list_tasks":
                        tasks = []
                        for task in manager.list_tasks():
                            tasks.append(
                                {
                                    "id": task.id,
                                    "name": task.name or "",
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
                    elif method == "add_download":
                        task = manager.add(
                            args.get("source"),
                            dest_dir=args.get("dest_dir"),
                            filename=args.get("filename"),
                            headers=args.get("headers"),
                            mirrors=args.get("mirrors"),
                        )
                        self._send_json(200, {"ok": True, "id": task.id})
                    elif method == "task_details":
                        self._send_json(
                            200,
                            {"ok": True, "task": manager.task_details(args["task_id"])},
                        )
                    elif method == "rescan_task":
                        manager.rescan_task(args["task_id"])
                        self._send_json(200, {"ok": True})
                    elif method == "check_for_updates":
                        self._send_json(200, {"ok": True, "update": check_for_update()})
                    elif method == "download_update":
                        update = check_for_update()
                        package = download_update(update)
                        self._send_json(200, {"ok": True, "package": package})
                    elif method == "install_update":
                        install_update(args["path"])
                        self._send_json(200, {"ok": True})
                    elif method == "set_file_priorities":
                        manager.set_file_priorities(args["task_id"], args["priorities"])
                        self._send_json(200, {"ok": True})
                    elif method == "set_urgent":
                        task = manager.get(args["task_id"])
                        if not task or task.status.value not in (
                            "queued",
                            "paused",
                            "connecting",
                            "downloading",
                        ):
                            raise ValueError("Only pending downloads can be made urgent")
                        manager.set_urgent(task.id)
                        self._send_json(200, {"ok": True})
                    elif method == "export_queue":
                        manager.export_queue(args["file_path"])
                        self._send_json(200, {"ok": True})
                    elif method == "import_queue":
                        result = manager.import_queue(args["file_path"])
                        self._send_json(200, {"ok": True, **result})
                    elif method == "add_video_task":
                        task = manager.add_video(
                            args.get("url"),
                            args.get("format_id", "best"),
                            args.get("filename", "video.mp4"),
                        )
                        self._send_json(200, {"ok": True, "id": task.id})

                    elif method == "fetch_video_info":
                        import yt_dlp  # type: ignore

                        url = args.get("url")
                        from urllib.parse import urlparse

                        if (
                            not isinstance(url, str)
                            or urlparse(url).scheme not in ("http", "https")
                            or not urlparse(url).netloc
                        ):
                            raise ValueError("Video URL must be HTTP or HTTPS")
                        ydl_opts = {
                            "quiet": True,
                            "no_warnings": True,
                            "noplaylist": True,
                            "socket_timeout": 20,
                        }
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
                        delete_files = args.get("delete_files", False)
                        manager.cancel(args["task_id"], delete_files=delete_files)
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
                        self._send_json(200, {"ok": True, "config": manager.get_config()})
                    elif method == "set_config":
                        manager.set_config(args.get("config", {}))
                        self._send_json(200, {"ok": True})
                    elif method == "get_settings":
                        if hasattr(manager, "app_config"):
                            self._send_json(
                                200,
                                {"ok": True, "settings": manager.app_config.settings},
                            )
                        else:
                            self._send_json(500, {"ok": False, "error": "No config available"})

                    elif method == "update_settings":
                        if hasattr(manager, "app_config"):
                            settings = args.get("settings", {})
                            if not isinstance(settings, dict):
                                raise ValueError("Settings must be an object")
                            translated = {
                                k: v
                                for k, v in settings.items()
                                if k in manager.get_config() or k == "category_dirs"
                            }
                            if "max_concurrent" in settings:
                                translated["max_concurrent_downloads"] = settings["max_concurrent"]
                            if "max_bandwidth_kbps" in settings:
                                value = settings["max_bandwidth_kbps"]
                                if type(value) is not int or value < 0:
                                    raise ValueError("Invalid bandwidth")
                                translated["global_bandwidth_limit"] = value * 1024
                            if (
                                "run_on_startup" in settings
                                and type(settings["run_on_startup"]) is not bool
                            ):
                                raise ValueError("Invalid startup setting")
                            manager.set_config(translated)
                            manager.app_config.update(settings)
                            manager.app_config.apply_run_on_startup()
                            self._send_json(200, {"ok": True})
                        else:
                            self._send_json(500, {"ok": False, "error": "No config available"})

                    else:
                        self._send_json(400, {"ok": False, "error": "Unknown RPC method"})
                except (ValueError, TypeError, KeyError) as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            self._send_json(404, {"ok": False, "error": "not found"})

    return Handler


class IpcServer:
    """Runs on a background thread inside the desktop app process."""

    def __init__(self, manager: DownloadManager, token: str, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self._server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(manager, token))
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
