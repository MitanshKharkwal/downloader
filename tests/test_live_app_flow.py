"""Run the desktop RPC against a real manager and an isolated local file server."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

from core.ipc_server import IpcServer
from core.manager import DownloadManager
from core.models import DownloadStatus, DownloadTask, DownloadType


def test_local_http_download_through_desktop_rpc(tmp_path):
    content = bytes(range(256)) * 8192
    received = []

    class FileHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            received.append(self.headers.get("X-Fixture"))
            requested = self.headers.get("Range")
            start, end = 0, len(content) - 1
            if requested:
                value = requested.removeprefix("bytes=")
                first, _, last = value.partition("-")
                start = int(first)
                end = int(last) if last else end
            self.send_response(206 if requested else 200)
            if requested:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            try:
                for offset in range(start, end + 1, 16384):
                    self.wfile.write(content[offset : min(offset + 16384, end + 1)])
                    time.sleep(0.002)
            except (BrokenPipeError, ConnectionResetError):
                pass

    files = ThreadingHTTPServer(("127.0.0.1", 0), FileHandler)
    thread = threading.Thread(target=files.serve_forever, daemon=True)
    thread.start()
    manager = DownloadManager(
        str(tmp_path),
        state_file=str(tmp_path / "state.json"),
        max_connections_per_download=2,
    )
    manager.events.off("status", manager._on_task_status_changed)
    ipc = IpcServer(manager, "local-test", port=0)
    ipc.start()

    def rpc(method, args=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{ipc._server.server_port}/rpc",
            data=json.dumps({"method": method, "args": args or {}}).encode(),
            headers={"X-Auth-Token": "local-test"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    try:
        url = f"http://127.0.0.1:{files.server_port}/fixture.bin"
        added = rpc(
            "add_download",
            {
                "source": url,
                "dest_dir": str(tmp_path / "chosen"),
                "headers": {"X-Fixture": "present"},
            },
        )
        task_id = added["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            task = rpc("list_tasks")["tasks"][0]
            if task["status"] in ("COMPLETED", "ERROR"):
                break
            time.sleep(0.05)
        assert task["status"] == "COMPLETED", task["error"]
        path = tmp_path / "chosen" / "fixture.bin"
        assert path.read_bytes() == content
        assert received and all(header == "present" for header in received)
        details = rpc("task_details", {"task_id": task_id})["task"]
        assert details["dest_path"] == str(path)
        assert "headers" not in details
        rpc("remove_task", {"task_id": task_id, "delete_files": True})
        assert not path.exists()
        assert rpc("list_tasks")["tasks"] == []
    finally:
        ipc.stop()
        manager.shutdown()
        files.shutdown()
        files.server_close()
        thread.join(timeout=5)


def test_completed_archive_extracts_without_touching_other_files(tmp_path):
    archive = tmp_path / "notes.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("notes/readme.txt", "ready")
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("keep")
    manager = DownloadManager(str(tmp_path), state_file=str(tmp_path / "state.json"))
    task = DownloadTask(
        "https://example.invalid/notes.zip", str(archive), DownloadType.HTTP
    )
    task.status = DownloadStatus.COMPLETED
    try:
        with patch.dict(
            sys.modules, {"win11toast": SimpleNamespace(toast=lambda *a, **kw: None)}
        ):
            manager._on_task_status_changed(task)
            deadline = time.monotonic() + 5
            extracted = tmp_path / "notes" / "readme.txt"
            while not extracted.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
        assert extracted.read_text() == "ready"
        assert unrelated.read_text() == "keep"
    finally:
        manager.shutdown()
