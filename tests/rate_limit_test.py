import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from local_range_server import start_server

from core.manager import DownloadManager
from core.models import DownloadStatus


def test_rate_limit():
    data = os.urandom(1024 * 512)  # 512 KB
    server = start_server(data, port=8767)

    # 200 KB/s limit
    limit = 200 * 1024
    dm = DownloadManager("test_rate_dir", global_bandwidth_limit=limit)
    dm._tasks = {}

    url = "http://127.0.0.1:8767/test_rate.bin"
    task = dm.add(url)

    start_time = time.time()

    while task.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
        time.sleep(0.1)

    duration = time.time() - start_time

    assert task.status == DownloadStatus.COMPLETED
    assert task.downloaded_bytes == len(data)

    # At 200KB/s, 512KB should take at least (512-200)/200 = 1.56 seconds
    # because the bucket starts full.
    assert duration >= 1.5, f"Downloaded too fast: {duration}s"

    print(f"test_rate_limit passed: 512KB took {duration:.2f}s with 200KB/s limit.")
    server.shutdown()


if __name__ == "__main__":
    test_rate_limit()
