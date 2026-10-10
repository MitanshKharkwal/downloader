import os
import threading
import time

import yt_dlp  # type: ignore

from core.events import EventEmitter
from core.models import DownloadStatus, DownloadTask


class VideoDownload:
    """An engine that uses yt-dlp to download video/audio streams."""

    def __init__(self, task: DownloadTask, events: EventEmitter, rate_limiter=None):
        self.rate_limiter = rate_limiter
        self._last_bytes = 0
        self._last_filename = None
        self.task = task
        self.events = events
        self._thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_requested = False
        self._delete_on_cancel = False

        self._format_id = "best"
        self._url = self.task.source
        if self.task.source.startswith("ytdlp||"):
            parts = self.task.source.split("||", 2)
            if len(parts) == 3:
                self._format_id = parts[1]
                self._url = parts[2]

    def start(self) -> None:
        if self.task.status not in (
            DownloadStatus.QUEUED,
            DownloadStatus.ERROR,
            DownloadStatus.CONNECTING,
        ):
            return

        self.task.status = DownloadStatus.CONNECTING
        self.events.emit("status", self.task)

        self._cancel_event.clear()
        self._pause_event.clear()
        self._pause_requested = False

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _join(self):
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()

    def pause(self) -> None:
        if self.task.status not in (
            DownloadStatus.CONNECTING,
            DownloadStatus.DOWNLOADING,
        ):
            return
        self._pause_requested = True
        self._cancel_event.set()
        self._join()
        self.task.status = DownloadStatus.PAUSED
        self.task.speed_bps = 0
        self.events.emit("status", self.task)

    def resume(self) -> None:
        if self.task.status != DownloadStatus.PAUSED:
            return
        self._join()
        self.task.status = DownloadStatus.QUEUED
        self.start()

    def cancel(self, delete_files: bool = False) -> None:
        self._delete_on_cancel = delete_files
        self._pause_requested = False
        self._cancel_event.set()
        self._join()
        if delete_files:
            from .paths import cleanup_task_files

            cleanup_task_files(self.task)
        self.task.status = DownloadStatus.CANCELED
        self.task.speed_bps = 0
        self.events.emit("status", self.task)

    def stop_threads(self) -> None:
        self._cancel_event.set()
        self._join()

    def on_priority_changed(self) -> None:
        if hasattr(self.rate_limiter, "refresh"):
            self.rate_limiter.refresh()
        self.task.speed_bps = 0

    def _progress_hook(self, d):
        if self._cancel_event.is_set():
            raise Exception("Cancelled")

        if d["status"] == "downloading":
            current = d.get("downloaded_bytes", 0)
            filename = d.get("filename")
            if filename != self._last_filename:
                self._last_bytes = 0
                self._last_filename = filename
            if self.rate_limiter:
                self.rate_limiter.consume(
                    max(0, current - self._last_bytes), self._cancel_event
                )
            self._last_bytes = current
            if self._cancel_event.is_set():
                raise RuntimeError("Cancelled")
            self.task.status = DownloadStatus.DOWNLOADING
            self.task.downloaded_bytes = d.get(
                "downloaded_bytes", self.task.downloaded_bytes
            )
            self.task.total_bytes = (
                d.get("total_bytes")
                or d.get("total_bytes_estimate")
                or self.task.total_bytes
            )
            self.task.speed_bps = d.get("speed", 0) or 0
            self.events.emit("progress", self.task)

    def _run(self):
        try:
            if (
                os.path.exists(self.task.dest_path)
                and os.path.getsize(self.task.dest_path) > 0
            ):
                self.task.status = DownloadStatus.COMPLETED
                self.task.completed_at = time.time()
                self.task.speed_bps = 0
                self.events.emit("status", self.task)
                return

            ydl_opts = {
                "format": self._format_id,
                "outtmpl": self.task.dest_path.replace("%", "%%"),
                "noplaylist": True,
                "socket_timeout": 10,
                "retries": 2,
                "progress_hooks": [self._progress_hook],
                "quiet": True,
                "no_warnings": True,
                "continuedl": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self._url])

            if self._cancel_event.is_set():
                if getattr(self, "_pause_requested", False):
                    self.task.status = DownloadStatus.PAUSED
                    self.events.emit("status", self.task)
                else:
                    if self._delete_on_cancel:
                        try:
                            if os.path.exists(self.task.dest_path):
                                os.remove(self.task.dest_path)
                        except OSError:
                            pass
                return

            self.task.status = DownloadStatus.COMPLETED
            self.task.completed_at = time.time()
            self.task.speed_bps = 0
            self.events.emit("status", self.task)

        except Exception as e:
            if getattr(self, "_pause_requested", False):
                self.task.status = DownloadStatus.PAUSED
                self.events.emit("status", self.task)
            elif self._cancel_event.is_set():
                self.task.status = DownloadStatus.CANCELED
                self.events.emit("status", self.task)
            else:
                self.task.status = DownloadStatus.ERROR
                self.task.error_message = str(e)
                self.events.emit("status", self.task)
