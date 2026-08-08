"""A minimal Range-aware HTTP server for testing, with an artificial
per-chunk delay so a test can reliably pause a download mid-flight
without racing real-world network speed.
"""

from __future__ import annotations

import http.server
import re
import threading
import time

CHUNK = 16 * 1024
DELAY = 0.03  # seconds between chunks -> ~530KB/s ceiling, easy to catch mid-flight


def make_handler(data: bytes):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            start, end = 0, len(data) - 1
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d+)-(\d+)?", rng)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else len(data) - 1
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            pos = start
            while pos <= end:
                chunk_end = min(pos + CHUNK, end + 1)
                self.wfile.write(data[pos:chunk_end])
                pos = chunk_end
                time.sleep(DELAY)

    return Handler


def start_server(data: bytes, port: int = 8765) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("127.0.0.1", port), make_handler(data))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
