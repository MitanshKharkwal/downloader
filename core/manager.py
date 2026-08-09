"""The public surface of the core engine.

Everything else in the app -- the Windows PySide6 UI, the Android Kivy
UI, the browser-extension bridge -- should only ever talk to
DownloadManager. It doesn't need to know whether a given task is being
served by requests-based segmented HTTP or by libtorrent; it just adds
sources and gets DownloadTask updates back through the EventEmitter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse

import requests

from .events import EventEmitter
from .http_downloader import HttpDownload
from .models import DownloadStatus, DownloadTask, DownloadType, Priority
from .torrent_engine import TorrentDownload, TorrentSession

_MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)


def _cleanup_offline_task(task: DownloadTask) -> None:
    for path in (task.dest_path + ".part", task.dest_path + ".dmpart.json"):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    if os.path.exists(task.dest_path):
        try:
            if os.path.isdir(task.dest_path):
                shutil.rmtree(task.dest_path, ignore_errors=True)
            else:
                os.remove(task.dest_path)
        except OSError:
            pass


class TokenBucket:
    """A thread-safe token bucket rate limiter."""
    def __init__(self, rate: int):
        self._rate = rate
        self._capacity = rate
        self._tokens = float(rate)
        self._last_fill = time.time()
        self._lock = threading.Lock()
        
    @property
    def rate(self) -> int:
        return self._rate
        
    @rate.setter
    def rate(self, value: int) -> None:
        with self._lock:
            self._rate = value
            self._capacity = value
            self._tokens = float(value)
            self._last_fill = time.time()

    def consume(self, tokens: int) -> None:
        """Blocks until `tokens` are available. If rate is 0, does not block."""
        if self._rate <= 0:
            return
            
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self._last_fill
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                self._last_fill = now
                
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                
                # Not enough tokens, calculate wait time
                wait_time = (tokens - self._tokens) / self._rate
            
            # Wait outside the lock
            time.sleep(max(0.001, wait_time))


class DownloadManager:
    def __init__(
        self,
        download_dir: str,
        max_concurrent_downloads: int = 3,
        max_connections_per_download: int = 8,
        state_file: str | None = None,
        global_bandwidth_limit: int = 0,
    ) -> None:
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_connections_per_download = max_connections_per_download
        
        self.rate_limiter = TokenBucket(global_bandwidth_limit)
        self.state_file = state_file or os.path.join(download_dir, ".dm_state.json")

        os.makedirs(download_dir, exist_ok=True)
        self.events = EventEmitter()
        self._torrent_session = TorrentSession()

        self._tasks: dict[str, DownloadTask] = {}
        self._engines: dict[str, HttpDownload | TorrentDownload] = {}
        self._lock = threading.Lock()

        self.events.on("status", self._on_task_status_changed)
        self._load_state()

    # -- public API --------------------------------------------------------

    def add(self, source: str, dest_dir: str | None = None, filename: str | None = None) -> DownloadTask:
        """Add a URL, magnet URI, or .torrent path/URL to the queue.

        The type is auto-detected from `source` so callers (e.g. the
        browser-extension bridge or the Android intent handler) can just
        forward whatever the user clicked without branching themselves.
        
        If an existing non-terminal task (queued, connecting, downloading, paused) 
        already has the same source, this method returns the existing DownloadTask 
        instead of creating a duplicate.
        """
        dest_dir = dest_dir or self.download_dir
        os.makedirs(dest_dir, exist_ok=True)
        
        normalized_source = source
        if source.startswith("http://") or source.startswith("https://"):
            if source.lower().endswith(".torrent"):
                digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
                normalized_source = os.path.join(tempfile.gettempdir(), f"download_{digest}.torrent")

        with self._lock:
            for task in self._tasks.values():
                if task.status in (DownloadStatus.QUEUED, DownloadStatus.CONNECTING, DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED):
                    if task.source == source or task.source == normalized_source:
                        return task

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

    def cancel(self, task_id: str, delete_files: bool = True) -> None:
        engine = self._engines.get(task_id)
        if engine:
            engine.cancel(delete_files=delete_files)
        else:
            task = self._tasks.get(task_id)
            if task:
                task.status = DownloadStatus.CANCELED
                if delete_files:
                    _cleanup_offline_task(task)
        self._maybe_start_next()

    def retry(self, task_id: str) -> None:
        """Retry a failed download."""
        task = None
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == DownloadStatus.ERROR:
                task.status = DownloadStatus.QUEUED
                task.error_message = None
            else:
                task = None  # not retryable
        
        if task is not None:
            self._save_state()
            self.events.emit("status", task)
            self._maybe_start_next()

    def set_priority(self, task_id: str, priority: Priority) -> None:
        engine = None
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.priority == priority:
                return
            task.priority = priority
            
            # If it's an HTTP task, update its num_connections
            if task.type == DownloadType.HTTP:
                if priority == Priority.HIGH:
                    task.num_connections = 16
                elif priority == Priority.LOW:
                    task.num_connections = 2
                else:
                    task.num_connections = 8
                    
            is_active = task.status in (DownloadStatus.CONNECTING, DownloadStatus.DOWNLOADING)
            
            if is_active and task.type == DownloadType.HTTP:
                engine = self._engines.pop(task.id, None)
                task.status = DownloadStatus.QUEUED

        if engine:
            if hasattr(engine, "stop_threads"):
                engine.stop_threads()

        self._save_state()
        self.events.emit("status", task)
        self._maybe_start_next()

    def clear_finished(self) -> None:
        """Remove all completed, errored, or canceled tasks from the list."""
        with self._lock:
            to_remove = [
                tid for tid, t in self._tasks.items()
                if t.status in (DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED)
            ]
            for tid in to_remove:
                self._tasks.pop(tid, None)
        
        if to_remove:
            self._save_state()
            self.events.emit("tasks_cleared", to_remove)

    def get(self, task_id: str) -> DownloadTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    def shutdown(self) -> None:
        for task_id in list(self._engines):
            self.pause(task_id)
        self._torrent_session.shutdown()
        self._save_state()

    def set_global_speed_limit(self, limit_bps: int) -> None:
        self.rate_limiter.rate = limit_bps
        self._torrent_session.set_download_rate_limit(limit_bps)

    # -- scheduling ----------------------------------------------------------

    def _active_count(self) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING)
        )

    def _maybe_start_next(self) -> None:
        with self._lock:
            if self._active_count() >= self.max_concurrent_downloads:
                return
            queued_tasks = [t for t in self._tasks.values() if t.status == DownloadStatus.QUEUED]
            if not queued_tasks:
                return
                
            # Highest priority first, then oldest first
            queued_tasks.sort(key=lambda t: (-t.priority.value, t.created_at))
            next_task = queued_tasks[0]
            
            # Claim the slot immediately so concurrent threads don't over-fill
            next_task.status = DownloadStatus.CONNECTING
                
            # Instantiate engine and register it inside the lock so cancel()
            # knows it exists before we even start it.
            if next_task.type == DownloadType.HTTP:
                engine = HttpDownload(
                    next_task, self.events, num_connections=next_task.num_connections, rate_limiter=self.rate_limiter
                )
            else:
                engine = TorrentDownload(next_task, self.events, self._torrent_session)
            self._engines[next_task.id] = engine

        # start() touches engines/threads -- do it outside the lock so a
        # slow engine.start() call can't hold up other callers of add()/cancel().
        engine.start()

    def _start_task(self, task: DownloadTask) -> None:
        """Directly start a specific task (used by resume() for paused tasks)."""
        with self._lock:
            task.status = DownloadStatus.CONNECTING
            if task.type == DownloadType.HTTP:
                engine = HttpDownload(
                    task, self.events, num_connections=task.num_connections, rate_limiter=self.rate_limiter
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
        if name:
            return name
        # Python's built-in hash() is randomized per-process (PYTHONHASHSEED),
        # so the same URL would get a different fallback name every run --
        # confusing, and breaks matching a re-added URL back to its old
        # dest_path. hashlib is stable across runs and machines.
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        return f"download_{digest}"

    def _materialize_torrent_file(self, source: str) -> str:
        """If `source` is a remote .torrent URL, fetch it to a local temp
        file -- libtorrent needs the file on disk (or its raw bytes) to
        read metadata, it can't fetch it itself."""
        if source.startswith("http://") or source.startswith("https://"):
            resp = requests.get(source, timeout=30)
            resp.raise_for_status()
            
            digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
            path = os.path.join(tempfile.gettempdir(), f"download_{digest}.torrent")
            
            with open(path, "wb") as f:
                f.write(resp.content)
            return path
        return source  # already a local path

    def _save_state(self) -> None:
        with self._lock:
            try:
                manifest = [t.to_dict() for t in self._tasks.values()]
                tmp_file = self.state_file + ".tmp"
                with open(tmp_file, "w") as f:
                    json.dump(manifest, f, indent=2, default=str)
                os.replace(tmp_file, self.state_file)
            except OSError:
                pass  # persistence is best-effort; never let it break a download

    def _load_state(self) -> None:
        """Restores the task list from a previous session. Nothing is
        auto-started here -- tasks that were mid-download when the app
        last closed come back as PAUSED (safe default: no surprise
        bandwidth use, and HTTP tasks can resume exactly where they left
        off via their .dmpart.json sidecar once the person hits Resume).
        Queued/paused/terminal tasks keep their state as-is."""
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file) as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError):
            return  # corrupt or unreadable state file -- start with an empty queue rather than crash

        for entry in manifest:
            try:
                task = DownloadTask.from_dict(entry)
            except Exception as e:
                import traceback
                print(f"FAILED TO LOAD TASK: {e}")
                traceback.print_exc()
                continue  # skip a single malformed entry rather than losing the whole queue
            if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                task.status = DownloadStatus.PAUSED
                task.speed_bps = 0.0
            self._tasks[task.id] = task
