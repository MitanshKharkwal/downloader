import threading
import time
import os
import yt_dlp

from core.models import DownloadTask, DownloadStatus
from core.events import EventEmitter

class VideoDownload:
    """An engine that uses yt-dlp to download video/audio streams."""
    def __init__(self, task: DownloadTask, events: EventEmitter):
        self.task = task
        self.events = events
        self._thread = None
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._delete_on_cancel = False
        
        self._format_id = "best"
        self._url = self.task.source
        if self.task.source.startswith("ytdlp||"):
            parts = self.task.source.split("||", 2)
            if len(parts) == 3:
                self._format_id = parts[1]
                self._url = parts[2]

    def start(self) -> None:
        if self.task.status not in (DownloadStatus.QUEUED, DownloadStatus.ERROR):
            return
            
        self.task.status = DownloadStatus.CONNECTING
        self.events.emit("status", self.task)
        
        self._cancel_event.clear()
        self._pause_event.clear()
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.task.status != DownloadStatus.DOWNLOADING:
            return
        self.task.status = DownloadStatus.PAUSED
        self._pause_event.set()
        self._cancel_event.set() 
        self.events.emit("status", self.task)

    def resume(self) -> None:
        if self.task.status != DownloadStatus.PAUSED:
            return
        self.task.status = DownloadStatus.DOWNLOADING
        self._pause_event.clear()
        self._cancel_event.clear()
        self.events.emit("status", self.task)
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self, delete_files: bool = False) -> None:
        self._delete_on_cancel = delete_files
        self._cancel_event.set()
        self.task.status = DownloadStatus.CANCELED
        self.events.emit("status", self.task)
        
    def stop_threads(self) -> None:
        self._cancel_event.set()

    def _progress_hook(self, d):
        if self._cancel_event.is_set():
            raise Exception("Cancelled")
            
        if d['status'] == 'downloading':
            self.task.status = DownloadStatus.DOWNLOADING
            self.task.downloaded_bytes = d.get('downloaded_bytes', self.task.downloaded_bytes)
            self.task.total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or self.task.total_bytes
            self.task.speed_bps = d.get('speed', 0) or 0
            self.events.emit("status", self.task)

    def _run(self):
        try:
            ydl_opts = {
                'format': self._format_id,
                'outtmpl': self.task.dest_path, 
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'no_warnings': True,
                'continuedl': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self._url])
                
            if self._cancel_event.is_set():
                if self._delete_on_cancel:
                    try:
                        if os.path.exists(self.task.dest_path):
                            os.remove(self.task.dest_path)
                    except: pass
                return
                
            self.task.status = DownloadStatus.COMPLETED
            self.task.completed_at = time.time()
            self.task.speed_bps = 0
            self.events.emit("status", self.task)
            
        except Exception as e:
            if str(e) == "Cancelled":
                pass 
            else:
                self.task.status = DownloadStatus.ERROR
                self.task.error_message = str(e)
                self.events.emit("status", self.task)
