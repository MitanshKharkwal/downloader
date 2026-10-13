import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.events import EventEmitter
from core.http_downloader import HttpDownload
from core.models import DownloadStatus, DownloadTask, DownloadType


def test_segmented_download_reports_each_connection(tmp_path):
    content = os.urandom(2 * 1024 * 1024)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested = self.headers.get("Range", "")
            if requested.startswith("bytes="):
                start_text, end_text = requested[6:].split("-", 1)
                start = int(start_text)
                end = int(end_text) if end_text else len(content) - 1
                chunk = content[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
            else:
                chunk = content
                self.send_response(200)
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", '"segment-fixture"')
            self.end_headers()
            self.wfile.write(chunk)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        destination = tmp_path / "segmented.bin"
        task = DownloadTask(
            f"http://127.0.0.1:{server.server_port}/file",
            str(destination),
            DownloadType.HTTP,
            num_connections=8,
        )
        HttpDownload(task, EventEmitter(), num_connections=8).start()
        deadline = time.monotonic() + 10
        while task.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
            assert time.monotonic() < deadline, "segmented download timed out"
            time.sleep(0.02)

        assert task.status == DownloadStatus.COMPLETED, task.error_message
        assert destination.read_bytes() == content
        assert task.supports_ranges
        assert len(task.parts) == 8
        assert task.parts[0]["start"] == 0
        assert task.parts[-1]["end"] == len(content) - 1
        assert all(part["status"] == "complete" for part in task.parts)
        assert all(part["downloaded_bytes"] == part["size_bytes"] for part in task.parts)
        assert sum(part["downloaded_bytes"] for part in task.parts) == len(content)
        assert all(
            left["end"] + 1 == right["start"]
            for left, right in zip(task.parts, task.parts[1:])
        )
    finally:
        server.shutdown()
        server.server_close()
