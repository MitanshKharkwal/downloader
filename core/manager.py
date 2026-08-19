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
import shutil
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse
from typing import Any

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
        self._engines: dict[str, HttpDownload | TorrentDownload | Any] = {}
        self._lock = threading.Lock()

        self.events.on("status", self._on_task_status_changed)
        self._load_state()

        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self._scheduler_thread.start()

        self._urgent_task_id = None
        self._paused_for_urgent_task_ids = set()

    # -- public API --------------------------------------------------------

    def add(
        self,
        source: str,
        dest_dir: str | None = None,
        filename: str | None = None,
        headers: dict | None = None,
    ) -> DownloadTask:
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
                normalized_source = os.path.join(
                    tempfile.gettempdir(), f"download_{digest}.torrent"
                )

        is_torrent = bool(_MAGNET_RE.match(source)) or source.lower().endswith(
            ".torrent"
        )
        intended_dir = dest_dir
        intended_base = ""
        intended_ext = ""
        category = "Other"
        filename_is_explicit = filename is not None

        if not is_torrent:
            name = filename or self._filename_from_url(source)
            name = re.sub(r'[<>:"/\\|?*]', "_", name)
            if len(name) > 150:
                base, ext = os.path.splitext(name)
                if len(ext) > 20:
                    ext = ""
                name = base[: 150 - len(ext)] + ext

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
                            if os.path.abspath(task.dest_path) == os.path.abspath(
                                dest_dir
                            ):
                                return task
                        else:
                            if os.path.dirname(
                                os.path.abspath(task.dest_path)
                            ) == os.path.abspath(intended_dir):
                                task_base, task_ext = os.path.splitext(
                                    os.path.basename(task.dest_path)
                                )
                                if task_ext == intended_ext and task_base.startswith(
                                    intended_base
                                ):
                                    return task

        if _MAGNET_RE.match(source):
            task = DownloadTask(
                source=source,
                dest_path=dest_dir,
                type=DownloadType.TORRENT,
                category="Other",
            )
        elif source.lower().endswith(".torrent"):
            local_path = self._materialize_torrent_file(source)
            task = DownloadTask(
                source=local_path,
                dest_path=dest_dir,
                type=DownloadType.TORRENT,
                category="Other",
            )
        else:
            final_dest_dir = intended_dir
            name = intended_base + intended_ext

            os.makedirs(final_dest_dir, exist_ok=True)

            base, ext = os.path.splitext(name)
            target_path = os.path.join(final_dest_dir, name)
            counter = 1
            while os.path.exists(target_path) or os.path.exists(
                target_path + ".dmpart"
            ):
                target_path = os.path.join(final_dest_dir, f"{base} ({counter}){ext}")
                counter += 1

            task = DownloadTask(
                source=source,
                dest_path=target_path,
                type=DownloadType.HTTP,
                num_connections=self.max_connections_per_download,
                headers=headers or {},
                category=category,
                filename_is_explicit=filename_is_explicit,
            )

        with self._lock:
            self._tasks[task.id] = task
        self._save_state()
        self.events.emit("added", task)
        self._maybe_start_next()
        return task

    def pause(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.was_paused_for_urgent = False
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


    def pause_all(self) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if task.status in (
                DownloadStatus.DOWNLOADING,
                DownloadStatus.QUEUED,
                DownloadStatus.CONNECTING,
            ):
                self.pause(task.id)

    def resume_all(self) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if task.status == DownloadStatus.PAUSED:
                self.resume(task.id)

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
        """Retry a failed or completed download."""
        task = None
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (DownloadStatus.ERROR, DownloadStatus.COMPLETED):
                if task.status == DownloadStatus.COMPLETED:
                    _cleanup_offline_task(task)
                task.status = DownloadStatus.QUEUED
                task.error_message = None
                task.downloaded_bytes = 0
                task.total_bytes = 0
                task.completed_at = None
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

            is_active = task.status in (
                DownloadStatus.CONNECTING,
                DownloadStatus.DOWNLOADING,
            )

            if is_active and task.type == DownloadType.HTTP:
                engine = self._engines.pop(task.id, None)
                task.status = DownloadStatus.QUEUED

        if engine:
            if hasattr(engine, "stop_threads"):
                engine.stop_threads()

        self._save_state()
        self.events.emit("status", task)
        self._maybe_start_next()

    def set_urgent(self, task_id: str) -> None:
        """Feature 9: Bandwidth 'borrow' for one urgent download."""
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

        self.set_priority(task_id, Priority.HIGH)

        with self._lock:
            if task.status == DownloadStatus.PAUSED:
                self.resume(task_id)
            elif task.status == DownloadStatus.QUEUED:
                self._maybe_start_next()

    def clear_finished(self) -> None:
        """Remove all completed, errored, or canceled tasks from the list."""
        with self._lock:
            to_remove = [
                tid
                for tid, t in self._tasks.items()
                if t.status
                in (
                    DownloadStatus.COMPLETED,
                    DownloadStatus.ERROR,
                    DownloadStatus.CANCELED,
                )
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
        self._save_state()

    def get_config(self) -> dict:
        return {
            "download_dir": self.download_dir,
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "global_bandwidth_limit": self.rate_limiter.rate,
        }

    def set_config(self, config: dict) -> None:
        if "download_dir" in config:
            self.download_dir = config["download_dir"]
            os.makedirs(self.download_dir, exist_ok=True)
        if "max_concurrent_downloads" in config:
            self.max_concurrent_downloads = config["max_concurrent_downloads"]
        if "global_bandwidth_limit" in config:
            self.set_global_speed_limit(config["global_bandwidth_limit"])

        self._save_state()
        self._maybe_start_next()

    # -- scheduling ----------------------------------------------------------

    def _run_scheduler(self):
        """Background thread that enforces the smart schedule (e.g. download only at night)."""
        import datetime

        was_in_schedule = None
        was_metered = False

        while True:
            config = self.get_config()

            # Feature 6: Metered connection awareness
            is_metered = False
            try:
                from winrt.windows.networking.connectivity import (
                    NetworkCostType,
                    NetworkInformation,
                )

                profile = NetworkInformation.get_internet_connection_profile()
                if profile:
                    cost = profile.get_connection_cost()
                    is_metered = cost.network_cost_type != NetworkCostType.UNRESTRICTED
            except Exception:
                pass

            if config.get("pause_on_metered", True) and is_metered:
                if not was_metered:
                    self.pause_all()
                    was_metered = True
                time.sleep(60)
                continue
            elif was_metered:
                self.resume_all()
                was_metered = False

            if config.get("scheduler_enabled"):
                start_h = config.get("scheduler_start_hour", 2)
                end_h = config.get("scheduler_end_hour", 6)

                now = datetime.datetime.now().hour

                # Check if current hour is in schedule
                if start_h <= end_h:
                    in_schedule = start_h <= now < end_h
                else:
                    # Wraps around midnight (e.g. 22:00 to 06:00)
                    in_schedule = now >= start_h or now < end_h

                if not in_schedule:
                    # Outside schedule, pause active tasks
                    self.pause_all()
                    was_in_schedule = False
                else:
                    # Inside schedule, resume paused/queued tasks if we just entered schedule
                    if was_in_schedule is False:
                        self.resume_all()
                    was_in_schedule = True
            else:
                was_in_schedule = None

            time.sleep(60)

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

            config = self.get_config()
            if config.get("scheduler_enabled"):
                import datetime

                start_h = config.get("scheduler_start_hour", 2)
                end_h = config.get("scheduler_end_hour", 6)
                now = datetime.datetime.now().hour
                if start_h <= end_h:
                    in_schedule = start_h <= now < end_h
                else:
                    in_schedule = now >= start_h or now < end_h

                if not in_schedule:
                    return

            queued_tasks = [
                t for t in self._tasks.values() if t.status == DownloadStatus.QUEUED
            ]
            if not queued_tasks:
                return

            # Highest priority first, then oldest first
            queued_tasks.sort(key=lambda t: (-t.priority.value, t.created_at))
            next_task = queued_tasks[0]

            # Claim the slot immediately so concurrent threads don't over-fill
            next_task.status = DownloadStatus.CONNECTING
            next_task.speed_bps = 0.0

            # Instantiate engine and register it inside the lock so cancel()
            # knows it exists before we even start it.
            if next_task.type == DownloadType.HTTP:
                engine = HttpDownload(
                    next_task,
                    self.events,
                    num_connections=next_task.num_connections,
                    headers=next_task.headers,
                    rate_limiter=self.rate_limiter,
                )
            elif next_task.type == DownloadType.VIDEO:
                from core.video_downloader import VideoDownload

                engine = VideoDownload(next_task, self.events)
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
            task.speed_bps = 0.0
            if task.type == DownloadType.HTTP:
                engine = HttpDownload(
                    task,
                    self.events,
                    num_connections=task.num_connections,
                    headers=task.headers,
                    rate_limiter=self.rate_limiter,
                )
            elif task.type == DownloadType.VIDEO:
                from core.video_downloader import VideoDownload

                engine = VideoDownload(task, self.events)
            else:
                engine = TorrentDownload(task, self.events, self._torrent_session)
            self._engines[task.id] = engine
        engine.start()

    def _on_task_status_changed(self, task: DownloadTask) -> None:
        self._save_state()
        if task.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.ERROR,
            DownloadStatus.CANCELED,
        ):
            if task.status == DownloadStatus.COMPLETED:
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
                                    single_item = os.path.join(
                                        extract_dir, extracted_items[0]
                                    )
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

                        from win11toast import toast

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

            if task.id == getattr(self, "_urgent_task_id", None) and task.status in (
                DownloadStatus.COMPLETED,
                DownloadStatus.ERROR,
                DownloadStatus.CANCELED,
            ):
                self._urgent_task_id = None
                for tid in list(getattr(self, "_paused_for_urgent_task_ids", [])):
                    with self._lock:
                        t = self._tasks.get(tid)
                        should_resume = t and getattr(t, "was_paused_for_urgent", False)
                        if should_resume:
                            t.was_paused_for_urgent = False
                    if should_resume:
                        self.resume(tid)
                if hasattr(self, "_paused_for_urgent_task_ids"):
                    self._paused_for_urgent_task_ids.clear()

            self._maybe_start_next()

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
                with open(tmp_file, "w") as f:
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
            if "download_dir" in config:
                self.download_dir = config["download_dir"]
            if "max_concurrent_downloads" in config:
                self.max_concurrent_downloads = config["max_concurrent_downloads"]
            if "global_bandwidth_limit" in config:
                self.rate_limiter.rate = config["global_bandwidth_limit"]
                self._torrent_session.set_download_rate_limit(
                    config["global_bandwidth_limit"]
                )
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
                    task.dest_path = os.path.join(
                        os.path.dirname(task.dest_path), new_name
                    )

            except Exception as e:
                import traceback

                print(f"FAILED TO LOAD TASK: {e}")
                traceback.print_exc()
                continue  # skip a single malformed entry rather than losing the whole queue
            if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING):
                task.status = DownloadStatus.PAUSED
                task.speed_bps = 0.0
            self._tasks[task.id] = task

    def export_queue(self, file_path: str) -> None:
        """Feature 10: Export a download queue as a shareable file."""
        import json

        with self._lock:
            tasks_manifest = [t.to_dict() for t in self._tasks.values()]
        with open(file_path, "w") as f:
            json.dump(tasks_manifest, f, indent=2, default=str)

    def import_queue(self, file_path: str) -> None:
        """Feature 10: Import a download queue from a shareable file."""
        import json

        with open(file_path, "r") as f:
            manifest = json.load(f)
        for entry in manifest:
            try:
                source = entry.get("source")
                if not source:
                    continue
                filename = entry.get("dest_path")
                if filename:
                    import os

                    filename = os.path.basename(filename)

                # Re-add via manager.add for collision handling, path resolution, and engine setup
                task = self.add(source, filename=filename, headers=entry.get("headers"))
                if "mirrors" in entry:
                    task.mirrors = entry["mirrors"]
                if "file_priorities" in entry:
                    task.file_priorities = entry["file_priorities"]
            except Exception:
                continue
