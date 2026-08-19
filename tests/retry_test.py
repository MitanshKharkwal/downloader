import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from local_range_server import start_server

from core.manager import DownloadManager
from core.models import DownloadStatus


def test_retry():
    data = os.urandom(1024 * 512)  # 512 KB
    server = start_server(data, port=8766)

    dm = DownloadManager("test_retry_dir")
    dm._tasks = {}

    url = "http://127.0.0.1:8766/test_retry.bin"
    task = dm.add(url)

    # Wait for it to start downloading and fetch some bytes
    while (
        task.status not in (DownloadStatus.DOWNLOADING, DownloadStatus.COMPLETED)
        or task.downloaded_bytes == 0
    ):
        time.sleep(0.05)

    # Simulate a network error by shutting down the server temporarily
    # Wait, instead of shutting down, just forcefully set the task to error to simulate a fatal error
    engine = dm._engines.get(task.id)
    if engine:
        engine.cancel(delete_files=False)

    # Wait for cancellation
    while task.status != DownloadStatus.CANCELED:
        time.sleep(0.05)

    # Manually mark as ERROR
    task.status = DownloadStatus.ERROR
    task.error_message = "Mock Error"

    downloaded_before_retry = task.downloaded_bytes
    print(f"Downloaded before retry: {downloaded_before_retry}")

    # Now retry
    dm.retry(task.id)

    assert task.status in (
        DownloadStatus.QUEUED,
        DownloadStatus.CONNECTING,
        DownloadStatus.DOWNLOADING,
    )
    assert task.error_message is None

    # Wait for completion
    while task.status != DownloadStatus.COMPLETED:
        time.sleep(0.1)
        if task.status == DownloadStatus.ERROR:
            raise Exception("Task errored during retry")

    assert task.downloaded_bytes == len(data), (
        f"Downloaded {task.downloaded_bytes}, expected {len(data)}"
    )

    with open(task.dest_path, "rb") as f:
        assert f.read() == data

    print("test_retry passed")
    server.shutdown()


def test_retry_completed():
    data = os.urandom(1024 * 128)  # 128 KB
    server = start_server(data, port=8768)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        dm = DownloadManager(tmpdir)
        url = "http://127.0.0.1:8768/test_retry_completed.bin"
        task = dm.add(url)

        # Wait for completion
        while task.status != DownloadStatus.COMPLETED:
            time.sleep(0.05)

        assert os.path.exists(task.dest_path)

        # Now retry the completed task
        dm.retry(task.id)

        # It should go back to queued and restart download, and dest_path should be cleared/started again
        assert task.status in (
            DownloadStatus.QUEUED,
            DownloadStatus.CONNECTING,
            DownloadStatus.DOWNLOADING,
        )
        assert task.completed_at is None
        assert task.downloaded_bytes == 0

        # Wait for completion again
        while task.status != DownloadStatus.COMPLETED:
            time.sleep(0.05)

        assert os.path.exists(task.dest_path)
        with open(task.dest_path, "rb") as f:
            assert f.read() == data

    print("test_retry_completed passed")
    server.shutdown()


if __name__ == "__main__":
    test_retry()
    test_retry_completed()
