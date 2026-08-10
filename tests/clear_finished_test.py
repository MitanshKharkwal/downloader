import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manager import DownloadManager
from core.models import DownloadStatus


def test_clear_finished():
    dm = DownloadManager("test_clear_dir")
    dm._tasks = {}

    # 1. QUEUED task (should not be cleared)
    t1 = dm.add("http://example.com/queued.txt")
    t1.status = DownloadStatus.QUEUED

    # 2. COMPLETED task (should be cleared)
    t2 = dm.add("http://example.com/completed.txt")
    t2.status = DownloadStatus.COMPLETED

    # 3. ERROR task (should be cleared)
    t3 = dm.add("http://example.com/error.txt")
    t3.status = DownloadStatus.ERROR

    # 4. DOWNLOADING task (should not be cleared)
    t4 = dm.add("http://example.com/downloading.txt")
    t4.status = DownloadStatus.DOWNLOADING

    dm.clear_finished()

    tasks = dm.list_tasks()
    task_ids = {t.id for t in tasks}

    assert t1.id in task_ids
    assert t2.id not in task_ids
    assert t3.id not in task_ids
    assert t4.id in task_ids

    print("test_clear_finished passed")


if __name__ == "__main__":
    test_clear_finished()
