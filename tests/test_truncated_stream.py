import os
import sys
import time
import pytest
from local_range_server import start_server

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manager import DownloadManager
from core.models import DownloadStatus

def test_truncated_download():
    # Server returns truncated data
    data = os.urandom(1024 * 100) # 100 KB
    
    # We want a server that advertises 100KB but closes connection after 20KB
    import http.server
    import socketserver
    import threading
    
    class TruncatedHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", "102400")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
        def do_GET(self):
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-102399/102400")
            self.send_header("Content-Length", "102400")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            # Send only 20KB then close
            self.wfile.write(data[:20480])
            
    class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    server = ThreadingServer(("127.0.0.1", 8769), TruncatedHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    
    try:
        dm = DownloadManager("test_truncated_dir")
        dm._tasks = {}
        task = dm.add("http://127.0.0.1:8769/test.bin")
        
        start = time.time()
        while task.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
            time.sleep(0.1)
            if time.time() - start > 15:
                break
                
        assert task.status == DownloadStatus.ERROR
        assert any(term in task.error_message for term in ("stream truncated", "truncated", "IncompleteRead", "Connection broken"))
    finally:
        server.shutdown()
