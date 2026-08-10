"""Segmented HTTP downloader with pause/resume.

This is the piece that makes a download manager faster than a plain
browser save: split the file into N byte ranges, pull them in parallel
over separate connections, and persist enough state on disk that a
paused or crashed download picks up where it left off instead of
restarting.

Falls back to a single honest streaming connection when the server
doesn't advertise Range support.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

import requests

from .events import EventEmitter
from .models import DownloadStatus, DownloadTask

DEFAULT_CHUNK = 256 * 1024  # bytes read per requests.iter_content() call
SPEED_WINDOW_SECONDS = 5
MAX_CONSECUTIVE_SEGMENT_FAILURES = (
    6  # ~6 retries * 1.5s backoff before giving up loudly
)

# requests' default User-Agent ("python-requests/X.X") gets blocked outright
# by a lot of CDNs and file hosts as basic anti-bot/anti-hotlinking
# protection -- discovered this the hard way against a real file host that
# reset the connection every time. A normal browser UA avoids that class of
# problem entirely; callers can still override it via the `headers` param.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class _Segment:
    start: int
    end: int  # inclusive
    downloaded: int = 0  # bytes already written for this segment

    @property
    def remaining_start(self) -> int:
        return self.start + self.downloaded

    @property
    def done(self) -> bool:
        return self.downloaded >= (self.end - self.start + 1)


class HttpDownload:
    def __init__(
        self,
        task: DownloadTask,
        events: EventEmitter,
        num_connections: int = 8,
        chunk_size: int = DEFAULT_CHUNK,
        headers: dict | None = None,
        rate_limiter=None,
    ) -> None:
        self.task = task
        self.events = events
        self.num_connections = max(1, num_connections)
        self.chunk_size = chunk_size
        self.extra_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Encoding": "identity",
            **(headers or {}),
        }
        self.rate_limiter = rate_limiter

        self._segments: list[_Segment] = []
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # set == "not paused, go ahead"
        self._cancel_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._controller_thread: threading.Thread | None = None
        self._speed_samples: deque[tuple[float, int]] = deque()
        self._etag: str | None = None
        self._last_modified: str | None = None
        self._unknown_size: bool = False

    # -- public API ----------------------------------------------------

    def start(self) -> None:
        self.task.status = DownloadStatus.CONNECTING
        self.events.emit("status", self.task)
        self._controller_thread = threading.Thread(target=self._run, daemon=True)
        self._controller_thread.start()

    def pause(self) -> None:
        if self.task.status not in (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.CONNECTING,
            DownloadStatus.QUEUED,
        ):
            return  # already finished/errored/canceled -- nothing to pause
        self.task.status = DownloadStatus.PAUSED
        self._cancel_event.set()
        self._pause_event.set()
        self._save_state()
        self.events.emit("status", self.task)

    def resume(self) -> None:
        if self.task.status != DownloadStatus.PAUSED:
            return
        self.task.status = DownloadStatus.DOWNLOADING
        self._cancel_event.clear()
        self._pause_event.set()
        self.events.emit("status", self.task)
        self._controller_thread = threading.Thread(target=self._run, daemon=True)
        self._controller_thread.start()

    def cancel(self, delete_files: bool = False) -> None:
        self._delete_on_cancel = delete_files
        self._cancel_event.set()
        self._pause_event.set()  # wake up any thread blocked on pause
        self.task.status = DownloadStatus.CANCELED
        self.events.emit("status", self.task)

    def stop_threads(self) -> None:
        """Stop threads without changing task status or deleting files (used for restarting engines)."""
        self._cancel_event.set()
        self._pause_event.set()

        # If the controller thread is dead/never started, cleanup immediately.
        if not self._controller_thread or not self._controller_thread.is_alive():
            self._cleanup_state_file()

    # -- internals -------------------------------------------------------

    @property
    def _part_path(self) -> str:
        return self.task.dest_path + ".part"

    @property
    def _state_path(self) -> str:
        return self.task.dest_path + ".dmpart.json"

    def _run(self) -> None:
        try:
            if not self._load_or_probe():
                return
            self._allocate_file()
            self.task.status = DownloadStatus.DOWNLOADING
            self.events.emit("status", self.task)

            monitor = threading.Thread(target=self._speed_monitor, daemon=True)
            monitor.start()

            self._threads = [
                threading.Thread(
                    target=self._download_segment, args=(seg,), daemon=True
                )
                for seg in self._segments
                if not seg.done
            ]
            for t in self._threads:
                t.start()

            while any(t.is_alive() for t in self._threads):
                if self._cancel_event.is_set():
                    for t in self._threads:
                        t.join(timeout=2.0)
                    break
                self._tune_segments()
                # Use wait instead of sleep to allow faster exit on cancel
                self._cancel_event.wait(1.0)

            if self._cancel_event.is_set():
                return

            if all(seg.done for seg in self._segments):
                os.replace(self._part_path, self.task.dest_path)
                self._cleanup_state_file()
                self.task.status = DownloadStatus.COMPLETED
                self.task.completed_at = time.time()
                self.events.emit("status", self.task)
                self.events.emit("complete", self.task)
            elif self.task.status != DownloadStatus.PAUSED:
                self.task.status = DownloadStatus.ERROR
                self.task.error_message = "download ended before all segments completed"
                self.events.emit("status", self.task)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.task.status = DownloadStatus.ERROR
            self.task.error_message = str(exc)
            self.events.emit("status", self.task)
            self.events.emit("error", self.task, exc)
        finally:
            if self.task.status == DownloadStatus.CANCELED:
                self._cleanup_state_file()
                if getattr(self, "_delete_on_cancel", False):
                    for path in (self._part_path, self.task.dest_path):
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except OSError:
                            pass

    def _load_or_probe(self) -> bool:
        """Resume from a saved .dmpart.json if it matches, else probe fresh."""
        if os.path.exists(self._state_path) and os.path.exists(self._part_path):
            try:
                with open(self._state_path) as f:
                    state = json.load(f)
                part_size_ok = os.path.getsize(self._part_path) == state.get(
                    "total_bytes"
                )
                if state.get("source") == self.task.source and part_size_ok:
                    try:
                        probe_headers = dict(self.extra_headers)
                        with requests.head(
                            self.task.source,
                            headers=probe_headers,
                            allow_redirects=True,
                            timeout=15,
                        ) as head_resp:
                            if head_resp.status_code == 200:
                                current_etag = head_resp.headers.get("ETag")
                                current_lm = head_resp.headers.get("Last-Modified")
                                if (
                                    state.get("etag")
                                    and current_etag
                                    and state.get("etag") != current_etag
                                ) or (
                                    state.get("last_modified")
                                    and current_lm
                                    and state.get("last_modified") != current_lm
                                ):
                                    raise ValueError("ETag/Last-Modified mismatch")
                    except (requests.RequestException, ValueError):
                        pass  # network error or mismatch, fall through to fresh probe
                    else:
                        self._segments = [_Segment(**s) for s in state["segments"]]
                        self.task.total_bytes = state["total_bytes"]
                        self.task.downloaded_bytes = sum(
                            s.downloaded for s in self._segments
                        )
                        self.task.supports_ranges = state.get("supports_ranges", True)
                        self._etag = state.get("etag")
                        self._last_modified = state.get("last_modified")
                        return True
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # corrupt sidecar, fall through to a fresh probe

        probe_headers = dict(self.extra_headers)
        probe_headers["Range"] = "bytes=0-0"

        sources = [self.task.source] + getattr(self.task, "mirrors", [])
        last_exc = None

        for source in sources:
            try:
                with requests.get(
                    source,
                    headers=probe_headers,
                    stream=True,
                    allow_redirects=True,
                    timeout=15,
                ) as resp:
                    resp.raise_for_status()
                    accepts_ranges = resp.status_code == 206

                    if accepts_ranges:
                        cr = resp.headers.get("Content-Range", "")
                        total_str = cr.split("/")[-1] if "/" in cr else "0"
                        total = int(total_str) if total_str.isdigit() else 0
                    else:
                        total = int(resp.headers.get("Content-Length", 0))

                    self._etag = resp.headers.get("ETag")
                    self._last_modified = resp.headers.get("Last-Modified")

                    if not getattr(self.task, "filename_is_explicit", False):
                        new_name = None
                        cd = resp.headers.get("Content-Disposition", "")
                        if cd:
                            import urllib.parse

                            m = re.search(
                                r"filename\*=UTF-8''([^; ]+)", cd, re.IGNORECASE
                            )
                            if m:
                                new_name = urllib.parse.unquote(m.group(1))
                            else:
                                m = re.search(r'filename="([^"]+)"', cd)
                                if not m:
                                    m = re.search(r"filename=([^; ]+)", cd)
                                if m:
                                    new_name = m.group(1)

                        if (
                            not new_name
                            and not os.path.splitext(self.task.dest_path)[1]
                        ):
                            ct = (
                                resp.headers.get("Content-Type", "")
                                .split(";")[0]
                                .strip()
                            )
                            if ct:
                                ext = mimetypes.guess_extension(ct)
                                if ext:
                                    if ext == ".htm":
                                        ext = ".html"
                                    new_name = (
                                        os.path.basename(self.task.dest_path) + ext
                                    )

                        if new_name and new_name != os.path.basename(
                            self.task.dest_path
                        ):
                            new_name = re.sub(r'[<>:"/\\|?*]', "_", new_name)
                            if len(new_name) > 150:
                                base, ext = os.path.splitext(new_name)
                                if len(ext) > 20:
                                    ext = ""
                                new_name = base[: 150 - len(ext)] + ext
                            dest_dir = os.path.dirname(self.task.dest_path)
                            target_path = os.path.join(dest_dir, new_name)
                            base, ext = os.path.splitext(new_name)
                            counter = 1
                            while os.path.exists(target_path) or os.path.exists(
                                target_path + ".dmpart"
                            ):
                                target_path = os.path.join(
                                    dest_dir, f"{base} ({counter}){ext}"
                                )
                                counter += 1
                            self.task.dest_path = target_path
                            self.events.emit("status", self.task)

                    break  # Success! Stop trying mirrors.
            except requests.RequestException as e:
                last_exc = e
                continue
        else:
            if last_exc:
                raise last_exc
            else:
                raise RuntimeError("No sources available to probe.")

        if total <= 0 or not accepts_ranges:
            if total <= 0:
                self._unknown_size = True
            # Server can't or won't do ranged requests -- single stream, no
            # parallelism, but still resumable-ish for progress reporting.
            self.task.supports_ranges = False
            self.task.total_bytes = total
            self.task.downloaded_bytes = 0
            segment_end = (
                sys.maxsize
                if (total <= 0 and not accepts_ranges)
                else max(total - 1, 0)
            )
            self._segments = [_Segment(0, segment_end)]
            self.num_connections = 1
            return True

        self.task.supports_ranges = True
        self.task.total_bytes = total
        self.task.downloaded_bytes = 0
        self._segments = self._plan_segments(total, self.num_connections)
        return True

    @staticmethod
    def _plan_segments(total: int, n: int) -> list[_Segment]:
        n = max(1, min(n, total) or 1)
        base = total // n
        segments = []
        start = 0
        for i in range(n):
            end = start + base - 1 if i < n - 1 else total - 1
            segments.append(_Segment(start=start, end=end))
            start = end + 1
        return segments

    def _allocate_file(self) -> None:
        import shutil

        dest_dir = os.path.dirname(os.path.abspath(self.task.dest_path)) or "."
        os.makedirs(dest_dir, exist_ok=True)

        if self.task.total_bytes > 0:
            free_space = shutil.disk_usage(dest_dir).free
            if free_space < self.task.total_bytes:
                raise RuntimeError(
                    f"Not enough disk space. Required: {self.task.total_bytes}, Available: {free_space}"
                )

        try:
            if self.task.total_bytes <= 0:
                if not os.path.exists(self._part_path):
                    open(self._part_path, "wb").close()
            elif (
                not os.path.exists(self._part_path)
                or os.path.getsize(self._part_path) != self.task.total_bytes
            ):
                with open(self._part_path, "wb") as f:
                    f.truncate(self.task.total_bytes)
        except OSError as e:
            if getattr(e, "errno", None) == 28:
                raise RuntimeError(
                    "Out of disk space (ENOSPC) during file allocation."
                ) from e
            raise

    def _download_segment(self, seg: _Segment) -> None:
        headers = dict(self.extra_headers)
        consecutive_failures = 0
        sources = [self.task.source] + getattr(self.task, "mirrors", [])
        try:
            current_source_idx = self._segments.index(seg) % len(sources)
        except ValueError:
            current_source_idx = 0

        with requests.Session() as session, open(self._part_path, "r+b") as f:
            while not seg.done and not self._cancel_event.is_set():
                self._pause_event.wait()  # blocks here while paused
                if self._cancel_event.is_set():
                    return

                source = sources[current_source_idx]
                range_start = seg.remaining_start
                if self.task.supports_ranges:
                    headers["Range"] = f"bytes={range_start}-{seg.end}"

                try:
                    with session.get(
                        source, headers=headers, stream=True, timeout=30
                    ) as resp:
                        resp.raise_for_status()
                        f.seek(range_start)
                        for chunk in resp.iter_content(chunk_size=self.chunk_size):
                            if self._cancel_event.is_set():
                                return
                            self._pause_event.wait()
                            if not chunk:
                                continue

                            n = len(chunk)
                            remaining = (seg.end - seg.start + 1) - seg.downloaded
                            if remaining > 0 and n > remaining:
                                chunk = chunk[:remaining]
                                n = remaining

                            if self.rate_limiter:
                                self.rate_limiter.consume(n)

                            f.write(chunk)
                            seg.downloaded += n
                            consecutive_failures = (
                                0  # this segment is making real progress again
                            )
                            with self._lock:
                                self.task.downloaded_bytes += n
                                if self.task.total_bytes <= 0 or self._unknown_size:
                                    # Server never gave us a Content-Length (e.g.
                                    # chunked transfer encoding) -- there's no way
                                    # to know the real total in advance, so mirror
                                    # it to what's downloaded so far. Otherwise the
                                    # UI is stuck showing "X / 0.0B" forever, even
                                    # after a fully successful download.
                                    self.task.total_bytes = self.task.downloaded_bytes
                            self.events.emit("progress", self.task)

                            if seg.done:
                                break
                        else:
                            if (
                                not self.task.supports_ranges
                                and self.task.total_bytes <= 0
                            ):
                                seg.end = seg.start + seg.downloaded - 1
                                self.task.total_bytes = self.task.downloaded_bytes
                except requests.RequestException as exc:
                    if isinstance(exc, requests.HTTPError) and exc.response is not None:
                        if exc.response.status_code in (401, 403):
                            self.task.error_message = f"Access Denied / Expired URL (HTTP {exc.response.status_code})"
                            self._cancel_event.set()
                            self._pause_event.set()
                            self.task.status = DownloadStatus.ERROR
                            self.events.emit("status", self.task)
                            return
                        elif exc.response.status_code == 429:
                            self.task.error_message = "Rate Limited (HTTP 429)"
                            self._cancel_event.set()
                            self._pause_event.set()
                            self.task.status = DownloadStatus.ERROR
                            self.events.emit("status", self.task)
                            return
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_SEGMENT_FAILURES * len(
                        sources
                    ):
                        # A host that keeps rejecting/resetting the connection
                        # would otherwise retry silently forever -- the task
                        # just sits at "downloading" with 0 progress with no
                        # way to tell it's actually failing. Give up loudly
                        # instead so the person isn't left staring at a stuck
                        # progress bar with no explanation.
                        self.task.error_message = f"gave up after {consecutive_failures} failed attempts: {exc}"
                        self._cancel_event.set()
                        self._pause_event.set()
                        self.task.status = DownloadStatus.ERROR
                        self.events.emit("status", self.task)
                        return
                    # Transient network error: brief backoff, retry the
                    # remainder of this segment from where it left off, potentially on next mirror.
                    self.task.error_message = f"segment retry after: {exc}"
                    current_source_idx = (current_source_idx + 1) % len(sources)
                    time.sleep(1.5)
                    continue

    def _speed_monitor(self) -> None:
        while not self._cancel_event.is_set() and self.task.status in (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.CONNECTING,
            DownloadStatus.PAUSED,
        ):
            now = time.time()
            self._speed_samples.append((now, self.task.downloaded_bytes))
            while (
                self._speed_samples
                and now - self._speed_samples[0][0] > SPEED_WINDOW_SECONDS
            ):
                self._speed_samples.popleft()
            if len(self._speed_samples) >= 2:
                t0, b0 = self._speed_samples[0]
                dt = now - t0
                self.task.speed_bps = (
                    (self.task.downloaded_bytes - b0) / dt if dt > 0 else 0.0
                )
            if self.task.status == DownloadStatus.COMPLETED:
                break
            time.sleep(0.5)

    def _tune_segments(self) -> None:
        if not self.task.supports_ranges or self.task.total_bytes <= 0:
            return

        with self._lock:
            active_threads = sum(1 for t in self._threads if t.is_alive())
            if active_threads >= self.num_connections:
                return

            # Find the segment with the largest remaining bytes
            largest_seg = None
            max_remaining = 0

            for seg in self._segments:
                if not seg.done:
                    rem = seg.end - seg.remaining_start
                    if rem > max_remaining:
                        max_remaining = rem
                        largest_seg = seg

            # If the largest remaining is > 2MB, split it
            MIN_SPLIT_SIZE = 1024 * 1024
            if largest_seg and max_remaining > MIN_SPLIT_SIZE * 2:
                midpoint = largest_seg.remaining_start + (max_remaining // 2)
                new_seg = _Segment(start=midpoint, end=largest_seg.end)

                # Update old segment
                largest_seg.end = midpoint - 1

                self._segments.append(new_seg)

                # Start a new thread
                t = threading.Thread(
                    target=self._download_segment, args=(new_seg,), daemon=True
                )
                self._threads.append(t)
                t.start()

    def _save_state(self) -> None:
        state = {
            "source": self.task.source,
            "total_bytes": self.task.total_bytes,
            "supports_ranges": self.task.supports_ranges,
            "etag": self._etag,
            "last_modified": self._last_modified,
            "segments": [
                {"start": s.start, "end": s.end, "downloaded": s.downloaded}
                for s in self._segments
            ],
        }
        with open(self._state_path, "w") as f:
            json.dump(state, f)

    def _cleanup_state_file(self) -> None:
        if os.path.exists(self._state_path):
            os.remove(self._state_path)
