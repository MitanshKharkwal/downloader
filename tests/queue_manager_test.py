import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from download_manager.core.manager import DownloadManager
from download_manager.core.models import DownloadStatus, Priority

def test_queue_ordering():
    dm = DownloadManager("test_queue_dir", max_concurrent_downloads=1)
    dm._tasks = {}

    # Add multiple tasks to the queue. They will all be queued because we have max_concurrent=1
    # Actually, the first one will start immediately.
    t1 = dm.add("http://example.com/file1.txt")
    t2 = dm.add("http://example.com/file2.txt")
    t3 = dm.add("http://example.com/file3.txt")

    # Force all to be QUEUED and stop the engine
    with dm._lock:
        for t in [t1, t2, t3]:
            t.status = DownloadStatus.QUEUED
        dm._engines.clear()

    # We expect t1 -> t2 -> t3 if no priority
    # Let's set t3 to High
    dm.set_priority(t3.id, Priority.HIGH)
    
    # Let's set t2 to Low
    dm.set_priority(t2.id, Priority.LOW)
    
    # We will manually call _maybe_start_next and check what gets started
    dm._maybe_start_next()
    
    # t3 (High) should be the one to start
    assert t3.status == DownloadStatus.CONNECTING or t3.status == DownloadStatus.DOWNLOADING
    assert t1.status == DownloadStatus.QUEUED
    assert t2.status == DownloadStatus.QUEUED
    
    # Reset t3 to queued
    t3.status = DownloadStatus.QUEUED
    
    # Now set t1 to High. Both t1 and t3 are High. Since t1 was added first, it should start first.
    dm.set_priority(t1.id, Priority.HIGH)
    dm._maybe_start_next()
    
    assert t1.status == DownloadStatus.CONNECTING or t1.status == DownloadStatus.DOWNLOADING
    assert t3.status == DownloadStatus.QUEUED
    
    # Ensure num_connections was updated
    assert t1.num_connections == 16
    assert t2.num_connections == 2
    
    print("test_queue_ordering passed")

if __name__ == "__main__":
    test_queue_ordering()
