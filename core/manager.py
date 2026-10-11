"""The public surface of the core engine.

Everything else in the app -- the WinUI 3 desktop app, the browser-extension bridge -- should only ever talk to
DownloadManager. It doesn't need to know whether a given task is being
served by requests-based segmented HTTP or by libtorrent; it just adds
sources and gets DownloadTask updates back through the EventEmitter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from .events import EventEmitter
from .http_downloader import HttpDownload
from .models import DownloadStatus, DownloadTask, DownloadType, Priority
from .paths import cleanup_task_files, safe_filename, unique_path
from .safety import inspect_download
from .torrent_engine import TorrentDownload, TorrentSession, inspect_torrent_file

_MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)
LOW_PRIORITY_RATE_BPS = 1024 * 1024


def _cleanup_offline_task(task: DownloadTask) -> None:
    cleanup_task_files(task)


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

    def consume(self, tokens: int, cancel_event=None) -> None:
        """Blocks until `tokens` are available. If rate is 0, does not block."""
        if self._rate <= 0:
            return

        while True:
            if cancel_event is not None and cancel_event.is_set():
                return
            with self._lock:
                if self._rate <= 0:
                    return
                now = time.time()
                elapsed = now - self._last_fill
                max_tokens = max(self._capacity, tokens)
                self._tokens = min(max_tokens, self._tokens + elapsed * self._rate)
                self._last_fill = now

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return

                # Not enough tokens, calculate wait time
                wait_time = (tokens - self._tokens) / self._rate

            # Wait outside the lock
            time.sleep(min(0.1, max(0.001, wait_time)))


class PriorityRateLimiter:
    """Apply the global limit plus a live per-task background-mode cap."""

    def __init__(self, task: DownloadTask, global_limiter: TokenBucket):
        self.task = task
        self.global_limiter = global_limiter
        self.local_limiter = TokenBucket(0)
        self.refresh()

    def refresh(self) -> None:
        rate = LOW_PRIORITY_RATE_BPS if self.task.priority == Priority.LOW else 0
        if self.local_limiter.rate != rate:
            self.local_limiter.rate = rate

    def consume(self, tokens: int, cancel_event=None) -> None:
        self.refresh()
        self.global_limiter.consume(tokens, cancel_event)
        self.local_limiter.consume(tokens, cancel_event)


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

        self._config: dict[str, Any] = {
            "download_dir": download_dir,
            "max_concurrent_downloads": max_concurrent_downloads,
            "global_bandwidth_limit": global_bandwidth_limit,
            "scheduler_enabled": False,
            "scheduler_start_hour": 2,
            "scheduler_end_hour": 6,
            "pause_on_metered": False,
            "auto_extract": True,
            "defender_scan_enabled": True,
            "category_dirs": {},
        }

        self.rate_limiter = TokenBucket(global_bandwidth_limit)
        self.state_file = state_file or os.path.join(download_dir, ".dm_state.json")

        os.makedirs(download_dir, exist_ok=True)
        self.events = EventEmitter()
        self._torrent_session = TorrentSession()

        self._tasks: dict[str, DownloadTask] = {}
        self._engines: dict[str, HttpDownload | TorrentDownload | Any] = {}
        self._lock = threading.RLock()
        self._operations = threading.RLock()
        self._stop_event = threading.Event()
        self._policy_paused: set[str] = set()
        self._metered = False
        self._suspend_starts = False
        self._urgent_task_id: str | None = None
        self._paused_for_urgent_task_ids: set[str] = set()
        self._safety_scans: set[str] = set()

        self.events.on("status", self._on_task_status_changed)
        self._load_state()

        self._scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._scheduler_thread.start()

    # -- public API --------------------------------------------------------

    def apply_config(self) -> None:
        if not hasattr(self, "app_config"):
            return
        config = self.app_config  # type: ignore
        self.download_dir = str(config.get("download_dir"))
        self.max_concurrent_downloads = int(config.get("max_concurrent"))
        self._config["max_concurrent_downloads"] = self.max_concurrent_downloads
        self._config["download_dir"] = self.download_dir

        limit_kbps = int(config.get("max_bandwidth_kbps"))
        limit_bps = limit_kbps * 1024 if limit_kbps > 0 else None
        self._config["global_bandwidth_limit"] = limit_bps or 0
        self.rate_limiter.rate = limit_bps or 0
        if self._torrent_session:
            self._torrent_session.set_download_rate_limit(limit_bps or 0)

        self._maybe_start_next()

    def add(
        self,
        source: str,
        dest_dir=None,
        filename=None,
        headers=None,
        mirrors=None,
        file_priorities=None,
    ) -> DownloadTask:
        with self._operations:
            if not isinstance(source, str) or not source.strip():
                raise ValueError("Source must be a URL, magnet, or torrent file")
            source = source.strip()
            parsed = urlparse(source)
            if not (
                _MAGNET_RE.match(source)
                or (parsed.scheme in ("http", "https") and parsed.netloc)
                or (source.lower().endswith(".torrent") and os.path.isfile(source))
            ):
                raise ValueError("Source must be an HTTP(S) URL, magnet, or existing torrent file")
            if headers is not None and (
                not isinstance(headers, dict)
                or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())
            ):
                raise ValueError("Headers must contain text keys and values")
            if mirrors is not None and (
                not isinstance(mirrors, list)
                or any(
                    not isinstance(url, str)
                    or urlparse(url).scheme not in ("http", "https")
                    or not urlparse(url).netloc
                    for url in mirrors
                )
            ):
                raise ValueError("Mirrors must be HTTP(S) URLs")
            if file_priorities is not None and (
                not isinstance(file_priorities, list)
                or any(type(p) is not int or not 0 <= p <= 7 for p in file_priorities)
            ):
                raise ValueError("File priorities must be integers from 0 to 7")
            if file_priorities and not source.lower().endswith(".torrent"):
                raise ValueError("File selection requires a .torrent file")
            return self._add(source, dest_dir, filename, headers, mirrors, file_priorities)

    def reserve_filename(self, task: DownloadTask, name: str) -> str:
        with self._lock:
            if safe_filename(name) == os.path.basename(task.dest_path):
                return task.dest_path
            task.dest_path = unique_path(
                os.path.dirname(task.dest_path),
                name,
                [t.dest_path for t in self._tasks.values() if t.id != task.id],
            )
            return task.dest_path

    def add_video(self, url: str, format_id="best", filename="video.mp4") -> DownloadTask:
        if (
            not isinstance(url, str)
            or urlparse(url).scheme not in ("http", "https")
            or not urlparse(url).netloc
        ):
            raise ValueError("Video URL must be HTTP or HTTPS")
        if format_id not in ("best", "worst", "bestaudio"):
            raise ValueError("Unsupported video format")
        with self._operations, self._lock:
            directory = self._config.get("category_dirs", {}).get("Video") or os.path.join(
                self.download_dir, "Video"
            )
            os.makedirs(directory, exist_ok=True)
            task = DownloadTask(
                source=f"ytdlp||{format_id}||{url}",
                dest_path=unique_path(
                    directory, filename, [t.dest_path for t in self._tasks.values()]
                ),
                type=DownloadType.VIDEO,
                category="Video",
                filename_is_explicit=True,
            )
            self._tasks[task.id] = task
        self._save_state()
        self.events.emit("added", task)
        self._maybe_start_next()
        return task

    def _add(
        self,
        source: str,
        dest_dir: str | None = None,
        filename: str | None = None,
        headers: dict | None = None,
        mirrors: list[str] | None = None,
        file_priorities: list[int] | None = None,
    ) -> DownloadTask:
        """Add a URL, magnet URI, or .torrent path/URL to the queue.

        The type is auto-detected from `source` so callers (e.g. the
        browser-extension bridge or the Android intent handler) can just
        forward whatever the user clicked without branching themselves.

        If an existing non-terminal task (queued, connecting, downloading, paused)
        already has the same source, this method returns the existing DownloadTask
        instead of creating a duplicate.
        """
        explicit_destination = dest_dir is not None
        dest_dir = dest_dir or self.download_dir
        os.makedirs(dest_dir, exist_ok=True)

        normalized_source = source
        if source.startswith("http://") or source.startswith("https://"):
            if source.lower().endswith(".torrent"):
                digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
                normalized_source = os.path.join(
                    tempfile.gettempdir(), f"download_{digest}.torrent"
                )

        is_torrent = bool(_MAGNET_RE.match(source)) or source.lower().endswith(".torrent")
        intended_dir = dest_dir
        intended_base = ""
        intended_ext = ""
        category = "Other"
        filename_is_explicit = filename is not None

        if not is_torrent:
            name = safe_filename(filename or self._filename_from_url(source))

            category = ""
            ext = os.path.splitext(name)[1].lower()
            if ext in (".exe", ".msi", ".bat", ".sh", ".apk"):
                category = "Programs"
            elif ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"):
                category = "Video"
            elif ext in (".mp3", ".wav", ".flac", ".m4a", ".aac"):
                category = "Music"
            elif ext in (
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".txt",
            ):
                category = "Documents"
            elif ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso"):
                category = "Compressed"
            elif ext in (
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".webp",
                ".tif",
                ".tiff",
            ):
                category = "Photos"
            else:
                category = "Other"

            category_dirs = self.get_config().get("category_dirs", {})
            if explicit_destination:
                intended_dir = dest_dir
            elif category_dirs.get(category):
                intended_dir = category_dirs[category]
            else:
                intended_dir = os.path.join(dest_dir, category)
            intended_base, intended_ext = os.path.splitext(name)

        with self._lock:
            for task in self._tasks.values():
                if task.status in (
                    DownloadStatus.QUEUED,
                    DownloadStatus.CONNECTING,
                    DownloadStatus.DOWNLOADING,
                    DownloadStatus.PAUSED,
                ):
                    if task.source == source or task.source == normalized_source:
                        if task.type == DownloadType.TORRENT:
                            if os.path.abspath(
                                os.path.dirname(task.dest_path)
                                if task.owns_dest_dir
                                else task.dest_path
                            ) == os.path.abspath(
                                dest_dir
                                if explicit_destination
                                else (
                                    self._config.get("category_dirs", {}).get("Torrents")
                                    or dest_dir
                                )
                            ):
                                return task
                        else:
                            if os.path.dirname(os.path.abspath(task.dest_path)) == os.path.abspath(
                                intended_dir
                            ):
                                task_base, task_ext = os.path.splitext(
                                    os.path.basename(task.dest_path)
                                )
                                if task_ext == intended_ext and task_base.startswith(intended_base):
                                    return task

        category_dirs = self.get_config().get("category_dirs", {})
        torrent_dir = dest_dir if explicit_destination else category_dirs.get("Torrents")
        if not torrent_dir:
            torrent_dir = dest_dir

        if _MAGNET_RE.match(source):
            task = DownloadTask(
                source=source,
                dest_path=torrent_dir,
                type=DownloadType.TORRENT,
                category="Torrents",
            )
        elif source.lower().endswith(".torrent"):
            local_path = self._materialize_torrent_file(source)
            if file_priorities is not None:
                preview = inspect_torrent_file(local_path, scrape_timeout=0)
                files = preview["files"]
                if len(file_priorities) != len(files) or not any(
                    priority > 0 and not file["pad"]
                    for priority, file in zip(file_priorities, files)
                ):
                    raise ValueError("Select at least one downloadable torrent file")
                if any(priority > 0 and file["pad"] for priority, file in zip(file_priorities, files)):
                    raise ValueError("Torrent padding files cannot be selected")
            task = DownloadTask(
                source=local_path,
                dest_path=torrent_dir,
                type=DownloadType.TORRENT,
                category="Torrents",
            )
        else:
            final_dest_dir = intended_dir
            name = intended_base + intended_ext

            os.makedirs(final_dest_dir, exist_ok=True)

            with self._lock:
                target_path = unique_path(
                    final_dest_dir, name, [t.dest_path for t in self._tasks.values()]
                )

            task = DownloadTask(
                source=source,
                dest_path=target_path,
                type=DownloadType.HTTP,
                num_connections=self.max_connections_per_download,
                headers=headers or {},
                category=category,
                filename_is_explicit=filename_is_explicit,
                health={
                    "state": "waiting",
                    "requested_connections": self.max_connections_per_download,
                    "authentication_forwarded": any(
                        key.lower() in ("authorization", "cookie") for key in (headers or {})
                    ),
                    "cookies_forwarded": any(key.lower() == "cookie" for key in (headers or {})),
                    "referrer_forwarded": any(
                        key.lower() in ("referer", "referrer") for key in (headers or {})
                    ),
                },
                safety={"status": "pending", "sha256": "", "warnings": []},
            )

        task.mirrors = mirrors or []
        task.file_priorities = file_priorities or []
        with self._lock:
            if task.type == DownloadType.TORRENT:
                task.dest_path = os.path.join(task.dest_path, task.id)
                task.owns_dest_dir = True
            else:
                task.dest_path = unique_path(
                    os.path.dirname(task.dest_path),
                    os.path.basename(task.dest_path),
                    [t.dest_path for t in self._tasks.values()],
                )
            self._tasks[task.id] = task
        self._save_state()
        self.events.emit("added", task)
        self._maybe_start_next()
        return task

    def add_batch(self, items: list[dict]) -> dict[str, int]:
        if not isinstance(items, list) or not 1 <= len(items) <= 200:
            raise ValueError("Batch must contain between 1 and 200 links")
        added = skipped = failed = 0
        for item in items:
            try:
                if not isinstance(item, dict):
                    raise ValueError("Each batch item must be an object")
                source = item.get("source")
                if not isinstance(source, str) or not source.strip():
                    raise ValueError("Each batch item needs a source URL")
                before = {task.id for task in self.list_tasks()}
                task = self.add(
                    source,
                    filename=item.get("filename"),
                    headers=item.get("headers"),
                )
                if task.id in before:
                    skipped += 1
                else:
                    added += 1
            except (ValueError, TypeError, OSError):
                failed += 1
        return {"added": added, "skipped": skipped, "failed": failed}

    def inspect_torrent(self, path: str) -> dict:
        return inspect_torrent_file(path)

    def pause(self, task_id: str, *, policy: bool = False) -> None:
        with self._operations:
            task = self.get(task_id)
            if not task:
                return
            if not policy:
                self._policy_paused.discard(task_id)
                self._paused_for_urgent_task_ids.discard(task_id)
                task.was_paused_for_urgent = False
                if self._urgent_task_id == task_id:
                    self._urgent_task_id = None
                    self._policy_paused.update(self._paused_for_urgent_task_ids)
                    self._paused_for_urgent_task_ids.clear()
            if task.status not in (
                DownloadStatus.CONNECTING,
                DownloadStatus.DOWNLOADING,
                DownloadStatus.QUEUED,
            ):
                return
            engine = self._engines.get(task_id)
            if engine:
                engine.pause()
            else:
                task.status = DownloadStatus.PAUSED
                self.events.emit("status", task)
            task.speed_bps = 0
            if policy:
                self._policy_paused.add(task_id)
            self._save_state()
        self._maybe_start_next()

    def resume(self, task_id: str) -> None:
        with self._operations:
            task = self.get(task_id)
            if not task or task.status not in (
                DownloadStatus.PAUSED,
                DownloadStatus.QUEUED,
            ):
                return
            task.status = DownloadStatus.QUEUED
            self._policy_paused.discard(task_id)
            self._save_state()
        self._maybe_start_next()

    def pause_all(self) -> None:
        with self._operations:
            self._suspend_starts = True
            try:
                for task in self.list_tasks():
                    self.pause(task.id)
            finally:
                self._suspend_starts = False

    def resume_all(self) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if task.status == DownloadStatus.PAUSED:
                self.resume(task.id)

    def cancel(self, task_id: str, delete_files: bool = False) -> None:
        with self._operations:
            task = self.get(task_id)
            if not task:
                return
            engine = self._engines.pop(task_id, None)
            if engine:
                engine.cancel(delete_files=delete_files)
            elif delete_files:
                _cleanup_offline_task(task)
            task.status = DownloadStatus.CANCELED
            task.speed_bps = 0
            self._policy_paused.discard(task_id)
            self._save_state()
        self.events.emit("status", task)

    def retry(self, task_id: str) -> None:
        with self._operations:
            task = self.get(task_id)
            if not task or task.status not in (
                DownloadStatus.ERROR,
                DownloadStatus.COMPLETED,
                DownloadStatus.CANCELED,
            ):
                return
            engine = self._engines.pop(task_id, None)
            if engine:
                engine.stop_threads()
            if task.status == DownloadStatus.COMPLETED:
                _cleanup_offline_task(task)
            task.status = DownloadStatus.QUEUED
            task.error_message = ""
            task.downloaded_bytes = 0
            task.total_bytes = 0
            task.completed_at = None
            self._save_state()
        self._maybe_start_next()

    def set_priority(self, task_id: str, priority: Priority) -> None:
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

            engine = self._engines.get(task_id)
            if engine and hasattr(engine, "on_priority_changed"):
                engine.on_priority_changed()

        self._save_state()
        self.events.emit("status", task)
        self._maybe_start_next()

    def set_urgent(self, task_id: str) -> None:
        """Feature 9: Bandwidth 'borrow' for one urgent download."""
        with self._operations:
            task = self.get(task_id)
            if not task or task.status not in (
                DownloadStatus.QUEUED,
                DownloadStatus.PAUSED,
                DownloadStatus.CONNECTING,
                DownloadStatus.DOWNLOADING,
            ):
                raise ValueError("Only pending downloads can be made urgent")
            self._set_urgent(task_id)

    def _set_urgent(self, task_id: str) -> None:
        self._urgent_task_id = task_id

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            for tid, t in self._tasks.items():
                if tid != task_id and t.status in (
                    DownloadStatus.DOWNLOADING,
                    DownloadStatus.CONNECTING,
                ):
                    t.was_paused_for_urgent = True
                    self._paused_for_urgent_task_ids.add(tid)

        for tid in list(self._paused_for_urgent_task_ids):
            self.pause(tid)
            self._paused_for_urgent_task_ids.add(tid)
            paused_task = self.get(tid)
            if paused_task:
                paused_task.was_paused_for_urgent = True

        self.set_priority(task_id, Priority.HIGH)

        should_resume = False
        should_start = False
        with self._lock:
            if task.status == DownloadStatus.PAUSED:
                should_resume = True
            elif task.status == DownloadStatus.QUEUED:
                should_start = True

        if should_resume:
            self.resume(task_id)
        elif should_start:
            self._maybe_start_next()

    def clear_finished(self) -> None:
        for task in self.list_tasks():
            if task.status in (
                DownloadStatus.COMPLETED,
                DownloadStatus.ERROR,
                DownloadStatus.CANCELED,
            ):
                self.remove_task(task.id)

    def remove_task(self, task_id: str, delete_files: bool = False) -> None:
        with self._operations:
            if not self.get(task_id):
                return
            self.cancel(task_id, delete_files=delete_files)
            with self._lock:
                self._tasks.pop(task_id, None)
            self._save_state()
        self.events.emit("tasks_cleared", [task_id])

    def remove_tasks(self, task_ids: list[str], delete_files: bool = False) -> dict[str, int]:
        if (
            not isinstance(task_ids, list)
            or not 1 <= len(task_ids) <= 500
            or any(not isinstance(task_id, str) or not task_id for task_id in task_ids)
        ):
            raise ValueError("Select between 1 and 500 downloads")
        removed = missing = 0
        for task_id in dict.fromkeys(task_ids):
            if self.get(task_id) is None:
                missing += 1
                continue
            self.remove_task(task_id, delete_files=delete_files)
            removed += 1
        return {"removed": removed, "missing": missing}

    def get(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[DownloadTask]:
        with self._lock:
            return list(self._tasks.values())

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._scheduler_thread is not threading.current_thread():
            self._scheduler_thread.join()
        for task_id in list(self._engines):
            self.pause(task_id)
        for engine in list(self._engines.values()):
            engine.stop_threads()
        self._engines.clear()
        self._torrent_session.shutdown()
        self._save_state()

    def set_global_speed_limit(self, limit_bps: int) -> None:
        self._config["global_bandwidth_limit"] = limit_bps
        self.rate_limiter.rate = limit_bps
        self._torrent_session.set_download_rate_limit(limit_bps)
        self._rebalance_bandwidth()
        self._save_state()

    def _rebalance_bandwidth(self):
        limit = self._config["global_bandwidth_limit"]
        active = [
            t
            for t in self.list_tasks()
            if t.status in (DownloadStatus.CONNECTING, DownloadStatus.DOWNLOADING)
        ]
        torrents = any(t.type == DownloadType.TORRENT for t in active)
        streams = any(t.type != DownloadType.TORRENT for t in active)
        torrent_limit = max(1, limit // 2) if limit and torrents and streams else limit
        stream_limit = max(1, limit - torrent_limit) if limit and torrents and streams else limit
        if self.rate_limiter.rate != stream_limit:
            self.rate_limiter.rate = stream_limit
        self._torrent_session.set_download_rate_limit(torrent_limit)

    def get_config(self) -> dict:
        return self._config.copy()

    def set_config(self, config: dict) -> None:
        if not isinstance(config, dict):
            raise ValueError("Config must be an object")
        allowed = set(self._config) | {"category_dirs"}
        if set(config) - allowed:
            raise ValueError("Unknown configuration setting")
        for key, value in config.items():
            if key in (
                "max_concurrent_downloads",
                "global_bandwidth_limit",
                "scheduler_start_hour",
                "scheduler_end_hour",
            ):
                maximum = (
                    100 if key == "max_concurrent_downloads" else 23 if "hour" in key else 10**12
                )
                minimum = 1 if key == "max_concurrent_downloads" else 0
                if type(value) is not int or not minimum <= value <= maximum:
                    raise ValueError(f"Invalid {key}")
            elif key in (
                "scheduler_enabled",
                "pause_on_metered",
                "auto_extract",
                "defender_scan_enabled",
            ):
                if type(value) is not bool:
                    raise ValueError(f"Invalid {key}")
            elif key == "download_dir":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Download directory is required")
                os.makedirs(value, exist_ok=True)
            elif key == "category_dirs":
                if not isinstance(value, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) and v.strip()
                    for k, v in value.items()
                ):
                    raise ValueError("Category directories must be paths")
        self._config.update(config)

        if "download_dir" in config:
            self.download_dir = config["download_dir"]
            os.makedirs(self.download_dir, exist_ok=True)
        if "max_concurrent_downloads" in config:
            self.max_concurrent_downloads = config["max_concurrent_downloads"]
        if "global_bandwidth_limit" in config:
            self.set_global_speed_limit(config["global_bandwidth_limit"])

        self._save_state()
        self._maybe_start_next()

        if hasattr(self, "app_config"):
            self.app_config.update(
                {
                    **config,
                    "max_concurrent": self.max_concurrent_downloads,
                    "max_bandwidth_kbps": self._config["global_bandwidth_limit"] // 1024,
                }
            )

    # -- scheduling ----------------------------------------------------------

    def _run_scheduler(self):
        """Background thread that enforces the smart schedule (e.g. download only at night)."""
        while not self._stop_event.is_set():
            with self._operations:
                for task in self.list_tasks():
                    if task.status in (
                        DownloadStatus.COMPLETED,
                        DownloadStatus.ERROR,
                        DownloadStatus.CANCELED,
                    ):
                        engine = self._engines.pop(task.id, None)
                        if engine:
                            engine.stop_threads()
            self._rebalance_bandwidth()
            self._metered = False
            try:
                from winrt.windows.networking.connectivity import (  # type: ignore[import-not-found]
                    NetworkCostType,
                    NetworkInformation,
                )

                profile = NetworkInformation.get_internet_connection_profile()
                self._metered = bool(
                    profile
                    and profile.get_connection_cost().network_cost_type
                    != NetworkCostType.UNRESTRICTED
                )
            except ImportError:
                pass
            except Exception:
                pass
            if not self._downloads_allowed():
                for task in self.list_tasks():
                    if task.status in (
                        DownloadStatus.CONNECTING,
                        DownloadStatus.DOWNLOADING,
                    ):
                        self.pause(task.id, policy=True)
            else:
                for tid in list(self._policy_paused):
                    self.resume(tid)
                self._maybe_start_next()
            self._stop_event.wait(1)

    def _downloads_allowed(self) -> bool:
        import datetime

        config = self.get_config()
        if (
            self._stop_event.is_set()
            or self._suspend_starts
            or (config.get("pause_on_metered") and self._metered)
        ):
            return False
        if not config.get("scheduler_enabled"):
            return True
        start, end = config["scheduler_start_hour"], config["scheduler_end_hour"]
        hour = datetime.datetime.now().hour
        return start <= hour < end if start <= end else hour >= start or hour < end

    def _active_count(self) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING)
        )

    def _maybe_start_next(self) -> None:
        # Serialize starts with user actions; callbacks from worker threads only
        # wake the scheduler, so stopping a worker cannot deadlock on this lock.
        with self._operations:
            while self._downloads_allowed():
                with self._lock:
                    if self._active_count() >= self.max_concurrent_downloads:
                        return
                    queued = sorted(
                        (
                            t
                            for t in self._tasks.values()
                            if t.status == DownloadStatus.QUEUED
                            and (self._urgent_task_id is None or t.id == self._urgent_task_id)
                        ),
                        key=lambda t: (-t.priority.value, t.created_at),
                    )
                    if not queued:
                        return
                    task = queued[0]
                    existing = self._engines.get(task.id)
                    if existing:
                        task.status = DownloadStatus.PAUSED
                        existing.resume()
                        if task.status == DownloadStatus.PAUSED:
                            return
                        continue
                    task.status = DownloadStatus.CONNECTING
                    task.speed_bps = 0
                    engine: Any
                    if task.type == DownloadType.HTTP:
                        engine = HttpDownload(
                            task,
                            self.events,
                            num_connections=task.num_connections,
                            headers=task.headers,
                            rate_limiter=PriorityRateLimiter(task, self.rate_limiter),
                            reserve_filename=self.reserve_filename,
                        )
                    elif task.type == DownloadType.VIDEO:
                        from .video_downloader import VideoDownload

                        engine = VideoDownload(
                            task,
                            self.events,
                            rate_limiter=PriorityRateLimiter(task, self.rate_limiter),
                        )
                    else:
                        engine = TorrentDownload(task, self.events, self._torrent_session)
                    self._engines[task.id] = engine
                self._rebalance_bandwidth()
                engine.start()

    def _start_task(self, task: DownloadTask) -> None:
        self.resume(task.id)

    def _on_task_status_changed(self, task: DownloadTask) -> None:
        self._save_state()
        if task.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.ERROR,
            DownloadStatus.CANCELED,
        ):
            if task.status == DownloadStatus.COMPLETED:
                self._start_safety_scan(task)
                config = self.get_config()
                if config.get("auto_extract", True):
                    ext = os.path.splitext(task.dest_path)[1].lower()
                    if ext == ".zip":
                        # Spawn a background thread to extract to a folder of the same name
                        def extract_zip(file_path):
                            import shutil
                            import zipfile

                            extract_dir = os.path.splitext(file_path)[0]
                            os.makedirs(extract_dir, exist_ok=True)
                            try:
                                with zipfile.ZipFile(file_path, "r") as zip_ref:
                                    zip_ref.extractall(extract_dir)

                                # Check if it created a single top-level folder
                                extracted_items = os.listdir(extract_dir)
                                if len(extracted_items) == 1:
                                    single_item = os.path.join(extract_dir, extracted_items[0])
                                    if os.path.isdir(single_item):
                                        # Move everything up one level
                                        for item in os.listdir(single_item):
                                            shutil.move(
                                                os.path.join(single_item, item),
                                                extract_dir,
                                            )
                                        os.rmdir(single_item)
                            except Exception:
                                pass  # Extraction failed, fail silently

                        threading.Thread(
                            target=extract_zip, args=(task.dest_path,), daemon=True
                        ).start()

                # Feature 7: Native OS notifications with quick actions
                def show_toast():
                    try:
                        import os

                        from win11toast import toast  # type: ignore

                        res = toast(
                            "Download Completed",
                            task.dest_path,
                            buttons=["Open", "Open Folder", "Delete"],
                        )
                        if res == "Open":
                            os.startfile(task.dest_path)
                        elif res == "Open Folder":
                            os.startfile(os.path.dirname(task.dest_path))
                        elif res == "Delete":
                            os.remove(task.dest_path)
                    except Exception:
                        pass

                threading.Thread(target=show_toast, daemon=True).start()

            if task.id == getattr(self, "_urgent_task_id", None):
                self._urgent_task_id = None
                for tid in self._paused_for_urgent_task_ids:
                    self._policy_paused.add(tid)
                self._paused_for_urgent_task_ids.clear()

    def _start_safety_scan(self, task: DownloadTask, *, force: bool = False) -> None:
        with self._lock:
            current = str(task.safety.get("status", "pending"))
            if task.id in self._safety_scans or (
                not force and current not in ("", "pending", "error")
            ):
                return
            self._safety_scans.add(task.id)
            task.safety = {"status": "checking", "sha256": "", "warnings": []}

        def scan() -> None:
            try:
                task.safety = inspect_download(
                    task.dest_path,
                    bool(self.get_config().get("defender_scan_enabled", True)),
                )
            except (OSError, ValueError) as exc:
                task.safety = {
                    "status": "error",
                    "sha256": "",
                    "warnings": [f"Safety scan failed: {exc}"],
                    "defender": "error",
                }
            finally:
                with self._lock:
                    self._safety_scans.discard(task.id)
                self._save_state()
                self.events.emit("safety", task)

        threading.Thread(target=scan, daemon=True).start()

    def rescan_task(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task or task.status != DownloadStatus.COMPLETED:
            raise ValueError("Only completed downloads can be scanned")
        self._start_safety_scan(task, force=True)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _filename_from_url(url: str) -> str:
        import re

        path = unquote(urlparse(url).path)
        name = os.path.basename(path.rstrip("/"))
        if name:
            name = re.sub(r'[<>:"/\\|?*]', "_", name)
            if len(name) > 150:
                base, ext = os.path.splitext(name)
                if len(ext) > 20:
                    ext = ""
                name = base[: 150 - len(ext)] + ext
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
                tasks_manifest = [t.to_dict() for t in self._tasks.values()]
                state = {"config": self.get_config(), "tasks": tasks_manifest}
                tmp_file = self.state_file + ".tmp"
                fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(state, f, indent=2, default=str)
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

        if isinstance(manifest, dict):
            config = manifest.get("config", {})
            self._config.update(config)
            if "download_dir" in config:
                self.download_dir = config["download_dir"]
            if "max_concurrent_downloads" in config:
                self.max_concurrent_downloads = config["max_concurrent_downloads"]
            if "global_bandwidth_limit" in config:
                self.rate_limiter.rate = config["global_bandwidth_limit"]
                self._torrent_session.set_download_rate_limit(config["global_bandwidth_limit"])
            task_list = manifest.get("tasks", [])
        else:
            task_list = manifest  # Legacy state file format

        for entry in task_list:
            try:
                task = DownloadTask.from_dict(entry)

                # Enforce safe filename lengths for older corrupt tasks
                dest_name = os.path.basename(task.dest_path)
                if len(dest_name) > 150:
                    base, ext = os.path.splitext(dest_name)
                    if len(ext) > 20:
                        ext = ""
                    new_name = base[: 150 - len(ext)] + ext
                    task.dest_path = os.path.join(os.path.dirname(task.dest_path), new_name)

            except Exception as e:
                import traceback

                print(f"FAILED TO LOAD TASK: {e}")
                traceback.print_exc()
                continue  # skip a single malformed entry rather than losing the whole queue
            if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                task.status = DownloadStatus.PAUSED
                task.speed_bps = 0.0
            self._tasks[task.id] = task

    def task_details(self, task_id: str) -> dict:
        with self._operations:
            task = self.get(task_id)
            if not task:
                raise ValueError("Download no longer exists")
            result = {k: v for k, v in task.to_dict().items() if k != "headers"}
            engine = self._engines.get(task_id)
            result["files"] = engine.list_files() if isinstance(engine, TorrentDownload) else []
            return result

    def set_file_priorities(self, task_id: str, priorities: list[int]) -> None:
        with self._operations:
            task = self.get(task_id)
            if not task or task.type != DownloadType.TORRENT:
                raise ValueError("Select a torrent download")
            if (
                not isinstance(priorities, list)
                or not priorities
                or any(type(p) is not int or not 0 <= p <= 7 for p in priorities)
                or not any(priorities)
            ):
                raise ValueError("Select at least one file; priorities must be 0 to 7")
            engine = self._engines.get(task_id)
            if not isinstance(engine, TorrentDownload):
                raise ValueError("Torrent metadata unavailable; resume the download first")
            files = engine.list_files()
            if len(files) != len(priorities) or not any(
                priority > 0 and not file["pad"] for priority, file in zip(priorities, files)
            ):
                raise ValueError("Select at least one downloadable file")
            engine.set_file_priorities(priorities)
            task.file_priorities = list(priorities)
            self._save_state()

    def export_queue(self, file_path: str) -> None:
        """Feature 10: Export a download queue as a shareable file."""
        import json

        with self._lock:
            tasks_manifest = [
                {k: v for k, v in t.to_dict().items() if k != "headers"}
                for t in self._tasks.values()
            ]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(tasks_manifest, f, indent=2, default=str)

    def import_queue(self, file_path: str) -> dict:
        """Feature 10: Import a download queue from a shareable file."""
        import json

        with open(file_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if not isinstance(manifest, list) or len(manifest) > 10000:
            raise ValueError("Queue must be a list of at most 10000 downloads")
        imported = failed = 0
        for entry in manifest:
            try:
                source = entry.get("source")
                if not source:
                    failed += 1
                    continue
                filename = entry.get("dest_path")
                if filename:
                    import os

                    filename = os.path.basename(filename)

                # Re-add via manager.add for collision handling, path resolution, and engine setup
                if source.startswith("ytdlp||"):
                    _, quality, url = source.split("||", 2)
                    self.add_video(url, quality, filename or "video.mp4")
                else:
                    self.add(
                        source,
                        filename=filename,
                        headers=entry.get("headers"),
                        mirrors=entry.get("mirrors"),
                        file_priorities=entry.get("file_priorities"),
                    )
                imported += 1
            except Exception:
                failed += 1
        return {"imported": imported, "failed": failed}
