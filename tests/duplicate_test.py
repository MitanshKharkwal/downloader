import os
import sys

# Ensure the package root (download_manager_1) is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from download_manager.core.manager import DownloadManager
from download_manager.core.models import DownloadStatus

def test_duplicate_detection():
    dm = DownloadManager("test_duplicates_dir")
    
    # Mock requests.get to avoid hanging on example.com
    import requests
    class MockResponse:
        def raise_for_status(self): pass
        @property
        def content(self): return b""
    requests.get = lambda url, **kwargs: MockResponse()
    
    # Mock _maybe_start_next so it stays QUEUED and doesn't fail parsing an empty torrent
    dm._maybe_start_next = lambda: None
    
    # Clean state
    dm._tasks = {}
    
    url = "http://example.com/file.zip"
    
    t1 = dm.add(url)
    assert t1.source == url
    assert len(dm._tasks) == 1
    
    t2 = dm.add(url)
    assert t2 is t1
    assert len(dm._tasks) == 1
    
    # Test torrent duplicates
    torrent_url = "http://example.com/file.torrent"
    t3 = dm.add(torrent_url)
    assert t3.type.value == "torrent"
    assert len(dm._tasks) == 2
    
    t4 = dm.add(torrent_url)
    assert t4 is t3
    assert len(dm._tasks) == 2
    
    print("test_duplicate_detection passed")

if __name__ == "__main__":
    test_duplicate_detection()
