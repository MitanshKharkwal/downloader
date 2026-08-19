import os
import sys
import threading
import time
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.video_downloader import VideoDownload
from core.models import DownloadTask, DownloadStatus, DownloadType
from core.events import EventEmitter

def test_video_download_pause_resume():
    task = DownloadTask(
        source="ytdlp||best||https://www.youtube.com/watch?v=mock",
        dest_path="mock_video.mp4",
        type=DownloadType.VIDEO
    )
    events = EventEmitter()
    
    with patch("yt_dlp.YoutubeDL") as mock_ytdl_class:
        mock_ytdl = MagicMock()
        mock_ytdl_class.return_value.__enter__.return_value = mock_ytdl
        
        def mock_download(urls):
            opts = mock_ytdl_class.call_args[0][0] if mock_ytdl_class.call_args[0] else mock_ytdl_class.call_args[1]
            hook = opts["progress_hooks"][0]
            
            hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes": 1000, "speed": 50})
            
            for _ in range(50):
                time.sleep(0.05)
                try:
                    hook({"status": "downloading", "downloaded_bytes": 200, "total_bytes": 1000, "speed": 50})
                except Exception as e:
                    raise e
                    
        mock_ytdl.download.side_effect = mock_download
        
        dl = VideoDownload(task, events)
        dl.start()
        
        time.sleep(0.1)
        assert task.status == DownloadStatus.DOWNLOADING
        
        dl.pause()
        time.sleep(0.2)
        assert task.status == DownloadStatus.PAUSED
        
        dl.resume()
        time.sleep(0.1)
        assert task.status == DownloadStatus.DOWNLOADING
