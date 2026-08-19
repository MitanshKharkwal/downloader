import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manager import DownloadManager
from core.models import DownloadStatus
from tests.local_range_server import start_server


def test_explicit_filename():
    data = b"hello world"
    # We will pass extra_headers to the mock server to simulate Content-Disposition
    server = start_server(data, port=8768)

    # We need to hack the local_range_server slightly or just use a custom mock server for this test
    # Actually, a simpler way without modifying local_range_server is to mock requests.get/head
    import requests

    original_get = requests.get
    original_head = requests.head

    class MockResponse:
        def __init__(self, is_head=False):
            self.status_code = 200
            self.headers = {
                "Content-Length": str(len(data)),
                "Content-Disposition": 'attachment; filename="server_suggested_name.dat"',
            }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, chunk_size):
            yield data

        def raise_for_status(self):
            pass

    def mock_get(*args, **kwargs):
        if "test_explicit.bin" in args[0]:
            return MockResponse()
        return original_get(*args, **kwargs)

    def mock_head(*args, **kwargs):
        if "test_explicit.bin" in args[0]:
            return MockResponse(is_head=True)
        return original_head(*args, **kwargs)

    requests.get = mock_get
    requests.head = mock_head

    try:
        import shutil
        shutil.rmtree("test_explicit_dir", ignore_errors=True)
        dm = DownloadManager("test_explicit_dir")

        # Test 1: Explicit filename
        url = "http://127.0.0.1:8768/test_explicit.bin"
        t1 = dm.add(url, filename="my_explicit_name.bin")

        while t1.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
            time.sleep(0.1)

        assert t1.status == DownloadStatus.COMPLETED
        assert os.path.basename(t1.dest_path) == "my_explicit_name.bin"
        assert t1.filename_is_explicit is True

        # Test 2: Auto-generated filename
        t2 = dm.add(url + "?auto=1")  # different url to avoid duplicate detection

        while t2.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
            time.sleep(0.1)

        assert t2.status == DownloadStatus.COMPLETED
        assert os.path.basename(t2.dest_path) == "server_suggested_name.dat"
        assert getattr(t2, "filename_is_explicit", False) is False

        print("test_explicit_filename passed")

    finally:
        requests.get = original_get
        requests.head = original_head
        server.shutdown()


if __name__ == "__main__":
    test_explicit_filename()
