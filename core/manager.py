"""The public surface of the core engine.

Everything else in the app -- the Windows PySide6 UI, the Android Kivy
UI, the browser-extension bridge -- should only ever talk to
DownloadManager. It doesn't need to know whether a given task is being
served by requests-based segmented HTTP or by libtorrent; it just adds
sources and gets DownloadTask updates back through the EventEmitter.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from urllib.parse import unquote, urlparse

import requests

from .events import EventEmitter
from .http_downloader import HttpDownload
from .models import DownloadStatus, DownloadTask, DownloadType
from .torrent_engine import TorrentDownload, TorrentSession

_MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)


class DownloadManager:
    def __init__(
        self,
        download_dir: str,
        max_concurrent_downloads: int = 3,
        max_connections_per_download: int = 8,
        state_file: str | None = None,
    ) -> None:
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_connections_per_download = max_connections_per_download
        self.state_file = state_file or os.path.join(download_dir, ".dm_state.json")

        os.makedirs(download_dir, exist_ok=True)
        self.events = EventEmitter()
        self._torrent_session = TorrentSession()

        self._tasks: dict[str, DownloadTask] = {}
        self._engines: dict[str, HttpDownload | TorrentDownload] = {}
        self._lock = threading.Lock()

        self.events.on("status", self._on_task_status_changed)

    # -- public API --------------------------------------------------------

    def add(self, source: str, dest_dir: str | None = None, filename: str | None = None) -> DownloadTask:
        """Add a URL, magnet URI, or .torrent path/URL to the queue.

        The type is auto-detected from `source` so callers (e.g. the
        browser-extension bridge or the Android intent handler) can just
        forward whatever the user clicked without branching themselves.
        """
        dest_dir = dest_dir or self.download_dir
        os.makedirs(dest_dir, exist_ok=True)

        if _MAGNET_RE.match(source):
            task = DownloadTask(source=source, dest_path=dest_dir, type=DownloadType.TORRENT)
        elif source.lower().endswith(".torrent"):
            local_path = self._materialize_torrent_file(source)
            task = DownloadTask(source=local_path, dest_path=dest_dir, type=DownloadType.TORRENT)
        else:
            name = filename or self._filename_from_url(source)
            task = DownloadTask(
                source=source,
                dest_path=os.path.join(dest_dir, name),
                type=DownloadType.HTTP,
                num_connections=self.max_connections_per_download,
            )

        with self._lock:
            self._tasks[task.id] = task
        self._save_state()
        self.events.emit("added", task)
        self._maybe_start_next()
        return task

    def pause(self, task_id: str) -> None:
        engine = self._engines.get(task_id)
        if engine:
            engine.pause()

    def resume(self, task_id: str) -> None:
        engine = self._engines.get(task_id)
        if engine:
            engine.resume()
        else:
            # Was queued (never started) or app restarted -- just (re)start it.
            self._start_task(self._tasks[task_id])

    def cancel(self, task_id: str, delete_files: bool = False) -> None:
        engine = self._engines.get(task_id)
        if engine:
            if isinstance(engine, TorrentDownload):
                engine.cancel(delete_files=delete_files)
            else:
                engine.cancel()
        else:
            task = self._tasks.get(task_id)
            if task:
                task.status = DownloadStatus.CANCELED
        self._maybe_start_next()

    def get(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def shutdown(self) -> None:
        for task_id in list(self._engines):
            self.pause(task_id)
        self._torrent_session.shutdown()
        self._save_state()

    # -- scheduling ----------------------------------------------------------

    def _active_count(self) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING)
        )

    def _maybe_start_next(self) -> None:
        if self._active_count() >= self.max_concurrent_downloads:
            return
        for task in self._tasks.values():
            if task.status == DownloadStatus.QUEUED:
                self._start_task(task)
                break

    def _start_task(self, task: DownloadTask) -> None:
        if task.type == DownloadType.HTTP:
            engine: HttpDownload | TorrentDownload = HttpDownload(
                task, self.events, num_connections=task.num_connections
            )
        else:
            engine = TorrentDownload(task, self.events, self._torrent_session)
        self._engines[task.id] = engine
        engine.start()

    def _on_task_status_changed(self, task: DownloadTask) -> None:
        self._save_state()
        if task.status in (DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED):
            self._maybe_start_next()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _filename_from_url(url: str) -> str:
        path = unquote(urlparse(url).path)
        name = os.path.basename(path.rstrip("/"))
        return name or f"download_{abs(hash(url)) % 10_000_000}"

    def _materialize_torrent_file(self, source: str) -> str:
        """If `source` is a remote .torrent URL, fetch it to a local temp
        file -- libtorrent needs the file on disk (or its raw bytes) to
        read metadata, it can't fetch it itself."""
        if source.startswith("http://") or source.startswith("https://"):
            resp = requests.get(source, timeout=30)
            resp.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=".torrent")
            with os.fdopen(fd, "wb") as f:
                f.write(resp.content)
            return path
        return source  # already a local path

    def _save_state(self) -> None:
        try:
            manifest = [t.to_dict() for t in self._tasks.values()]
            with open(self.state_file, "w") as f:
                json.dump(manifest, f, indent=2, default=str)
        except OSError:
            pass  # persistence is best-effort; never let it break a download
