"""Torrent/magnet engine built on libtorrent (the same library qBittorrent
and Deluge use under the hood).

We don't reimplement the BitTorrent wire protocol, DHT, or piece
selection -- that's a multi-month project on its own and libtorrent
already does it well. This module is the glue: one shared session,
one wrapper per active torrent, polled on a background thread and
reported through the same DownloadTask/EventEmitter shape the HTTP
downloader uses, so the rest of the app (UI, queue, persistence)
doesn't need to care which engine is behind a given task.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, cast
from urllib.parse import quote_from_bytes, urlsplit, urlunsplit

import requests

try:
    import libtorrent as lt

    LIBTORRENT_AVAILABLE = True
except ImportError:
    # No prebuilt libtorrent wheel exists for Android out of the box --
    # cross-compiling it needs a custom python-for-android recipe. Rather
    # than crash the whole app on import, degrade gracefully: HTTP
    # downloads keep working, and any torrent/magnet add fails with a
    # clear error instead of a stack trace. See android_app/README.md.
    lt = None  # type: ignore
    LIBTORRENT_AVAILABLE = False

from .events import EventEmitter
from .models import DownloadStatus, DownloadTask, Priority

LOW_PRIORITY_RATE_BPS = 1024 * 1024

POLL_INTERVAL_SECONDS = 1.0


def _tracker_counts(info, timeout: float) -> tuple[int | None, int | None, str]:
    """Ask HTTP trackers for estimates; many trackers do not offer scrape."""
    if not info.info_hashes().has_v1():
        return None, None, "Tracker counts are unavailable for this torrent."
    info_hash = info.info_hashes().v1.to_bytes()
    for tracker in list(info.trackers())[:3]:
        parsed = urlsplit(tracker.url)
        if parsed.scheme not in ("http", "https"):
            continue
        last = parsed.path.rsplit("/", 1)[-1]
        if not last.startswith("announce"):
            continue
        path = parsed.path[: -len(last)] + "scrape" + last[len("announce") :]
        query = parsed.query + ("&" if parsed.query else "") + "info_hash=" + quote_from_bytes(
            info_hash, safe=""
        )
        scrape_url = urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))
        try:
            with requests.get(scrape_url, timeout=timeout, stream=True) as response:
                response.raise_for_status()
                payload = response.raw.read(64 * 1024 + 1)
            if len(payload) > 64 * 1024:
                continue
            decoded = lt.bdecode(payload)
            if not isinstance(decoded, dict):
                continue
            decoded = cast(dict[bytes, Any], decoded)
            entries = decoded.get(b"files")
            if not isinstance(entries, dict):
                continue
            entries = cast(dict[bytes, Any], entries)
            counts = entries.get(info_hash)
            if not isinstance(counts, dict):
                continue
            counts = cast(dict[bytes, Any], counts)
            complete = counts.get(b"complete")
            incomplete = counts.get(b"incomplete")
            if type(complete) is not int or type(incomplete) is not int:
                continue
            return (
                max(complete, 0),
                max(incomplete, 0),
                "Live tracker scrape",
            )
        except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
            continue
    return None, None, "The tracker did not provide seed and peer counts."


def inspect_torrent_file(path: str, scrape_timeout: float = 6.0) -> dict:
    """Read torrent contents and best-effort tracker counts without downloading."""
    if not LIBTORRENT_AVAILABLE:
        raise RuntimeError("Torrent support is unavailable in this build")
    if not isinstance(path, str) or not os.path.isfile(path):
        raise ValueError("Choose an existing .torrent file")
    if not path.lower().endswith(".torrent"):
        raise ValueError("The selected file must use the .torrent extension")
    if os.path.getsize(path) > 20 * 1024 * 1024:
        raise ValueError("Torrent metadata is unexpectedly large")

    info = lt.torrent_info(path)
    files = info.files()
    listing: list[dict[str, Any]] = [
        {
            "name": files.file_path(index),
            "size": files.file_size(index),
            "priority": 0 if files.file_flags(index) & lt.file_storage.flag_pad_file else 4,
            "pad": bool(files.file_flags(index) & lt.file_storage.flag_pad_file),
        }
        for index in range(files.num_files())
    ]
    result = {
        "name": info.name(),
        "total_size": sum(file["size"] for file in listing if not file["pad"]),
        "files": listing,
        "seeds": None,
        "peers": None,
        "tracker_status": "No tracker is included in this torrent.",
    }
    if not list(info.trackers()):
        return result
    if scrape_timeout <= 0:
        result["tracker_status"] = "Tracker counts were not requested."
        return result
    seeds, peers, status = _tracker_counts(info, min(max(scrape_timeout, 0.1), 10.0))
    result.update(seeds=seeds, peers=peers, tracker_status=status)
    return result


# libtorrent's internal state enum -> our DownloadStatus
_STATE_MAP = (
    {
        lt.torrent_status.states.checking_files: DownloadStatus.CONNECTING,
        lt.torrent_status.states.downloading_metadata: DownloadStatus.CONNECTING,
        lt.torrent_status.states.downloading: DownloadStatus.DOWNLOADING,
        lt.torrent_status.states.finished: DownloadStatus.COMPLETED,
        lt.torrent_status.states.seeding: DownloadStatus.COMPLETED,
        lt.torrent_status.states.checking_resume_data: DownloadStatus.CONNECTING,
    }
    if LIBTORRENT_AVAILABLE
    else {}
)


class TorrentSession:
    """One libtorrent session shared by every torrent task in the app.

    Creating a new lt.session per torrent would mean a separate DHT
    routing table, separate listen port, etc. per download -- wasteful
    and slower to find peers. Instantiate this once in the
    DownloadManager and hand it to every TorrentDownload.
    """

    def __init__(self, listen_port_range: tuple[int, int] = (6881, 6891)) -> None:
        if not LIBTORRENT_AVAILABLE:
            self._session = None
            return
        settings = {
            "listen_interfaces": f"0.0.0.0:{listen_port_range[0]},[::]:{listen_port_range[0]}",
            "enable_dht": True,
            "enable_lsd": True,  # local peer discovery
            "enable_upnp": True,
            "enable_natpmp": True,
            "alert_mask": lt.alert.category_t.status_notification
            | lt.alert.category_t.error_notification,
        }
        self._session = lt.session(settings)  # type: ignore

    @property
    def raw(self) -> lt.session:  # type: ignore
        return self._session  # type: ignore

    def shutdown(self) -> None:
        # Let libtorrent flush resume data / close connections cleanly.
        if self._session is not None:
            self._session.pause()

    def set_download_rate_limit(self, limit_bps: int) -> None:
        if self._session is not None:
            self._session.apply_settings({"download_rate_limit": limit_bps})


class TorrentDownload:
    def __init__(
        self, task: DownloadTask, events: EventEmitter, torrent_session: TorrentSession
    ) -> None:
        self.task = task
        self.events = events
        self._session = torrent_session.raw
        self._handle: lt.torrent_handle | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._completed_emitted = False
        self._files_prioritized = False

    # -- public API ------------------------------------------------------

    def start(self) -> None:
        if not LIBTORRENT_AVAILABLE:
            self.task.status = DownloadStatus.ERROR
            self.task.error_message = (
                "torrent support isn't available on this platform build "
                "(libtorrent failed to import) -- HTTP downloads still work"
            )
            self.events.emit("status", self.task)
            return

        try:
            os.makedirs(self.task.dest_path, exist_ok=True)
            params = self._build_add_params()
            self._handle = self._session.add_torrent(params)
            self.on_priority_changed()
        except Exception as exc:  # noqa: BLE001 -- malformed magnet/.torrent input is real user input, not a bug
            self.task.status = DownloadStatus.ERROR
            self.task.error_message = f"couldn't add torrent: {exc}"
            self.events.emit("status", self.task)
            return

        self.task.status = DownloadStatus.CONNECTING
        self.events.emit("status", self.task)

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_threads(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join()
        if self._handle and self._handle.is_valid():
            self._session.remove_torrent(self._handle)
            self._handle = None

    def pause(self) -> None:
        if self.task.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.ERROR,
            DownloadStatus.CANCELED,
        ):
            return  # nothing to pause -- handle may already be removed from the session
        if self._handle and self._handle.is_valid():
            self._handle.pause()
        self.task.status = DownloadStatus.PAUSED
        self.events.emit("status", self.task)

    def resume(self) -> None:
        if self.task.status != DownloadStatus.PAUSED:
            return
        if self._handle and self._handle.is_valid():
            self._handle.resume()
        self.task.status = DownloadStatus.DOWNLOADING
        self.events.emit("status", self.task)

    def cancel(self, delete_files: bool = False) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join()
        if self._handle:
            flag = lt.session.delete_files if delete_files else 0
            self._session.remove_torrent(self._handle, flag)
            self._handle = None
        elif delete_files:
            from .paths import cleanup_task_files

            cleanup_task_files(self.task)
        if self._poll_thread and self._poll_thread is not threading.current_thread():
            self._poll_thread.join()
        self.task.status = DownloadStatus.CANCELED
        self.events.emit("status", self.task)

    def on_priority_changed(self) -> None:
        if self._handle and self._handle.is_valid():
            limit = LOW_PRIORITY_RATE_BPS if self.task.priority == Priority.LOW else 0
            self._handle.set_download_limit(limit)
        self.task.speed_bps = 0

    # -- internals ---------------------------------------------------------

    def list_files(self) -> list[dict]:
        handle = self._handle
        if not handle or not handle.is_valid() or not handle.status().has_metadata:
            return []
        info = handle.torrent_file()
        if info is None:
            return []
        files = info.files()
        priorities = handle.get_file_priorities()
        return [
            {
                "name": files.file_path(i),
                "size": files.file_size(i),
                "priority": priorities[i],
                "pad": bool(files.file_flags(i) & lt.file_storage.flag_pad_file),
            }
            for i in range(files.num_files())
        ]

    def set_file_priorities(self, priorities: list[int]) -> None:
        files = self.list_files()
        handle = self._handle
        if handle is None or not files or len(files) != len(priorities):
            raise ValueError("Torrent file list changed or metadata is unavailable")
        handle.prioritize_files(priorities)
        self._files_prioritized = True

    def _build_add_params(self) -> lt.add_torrent_params:
        source = self.task.source
        if source.startswith("magnet:"):
            params = lt.parse_magnet_uri(source)
        else:
            info = lt.torrent_info(source)
            params = lt.add_torrent_params()
            params.ti = info
            self.task.name = info.name()
            self.task.total_bytes = info.total_size()
            if self.task.file_priorities:
                params.file_priorities = self.task.file_priorities
                self._files_prioritized = True
        params.save_path = self.task.dest_path
        # Reject duplicate torrents with the same info-hash as errors,
        # and allocate storage using sparse files on disk.
        params.flags |= lt.torrent_flags.duplicate_is_error
        params.storage_mode = lt.storage_mode_t.storage_mode_sparse
        return params

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._stop_event.wait(POLL_INTERVAL_SECONDS):
                break
            if not self._handle or not self._handle.is_valid():
                continue

            try:
                status = self._handle.status()
            except RuntimeError:
                if self._stop_event.is_set():
                    return
                raise
            if status.errc.value():
                self.task.status = DownloadStatus.ERROR
                self.task.error_message = status.errc.message()
                self.task.speed_bps = 0
                self.events.emit("status", self.task)
                return
            self.task.name = status.name or self.task.name
            self.task.total_bytes = status.total_wanted or self.task.total_bytes
            self.task.downloaded_bytes = status.total_wanted_done
            self.task.speed_bps = float(status.download_rate)
            self.task.num_peers = status.num_peers
            self.task.num_seeds = status.num_seeds

            if (
                not self._files_prioritized
                and status.has_metadata
                and getattr(self.task, "file_priorities", None)
            ):
                try:
                    self._handle.prioritize_files(self.task.file_priorities)
                except Exception:
                    pass
                self._files_prioritized = True

            mapped = _STATE_MAP.get(status.state, DownloadStatus.DOWNLOADING)
            if self.task.status != DownloadStatus.PAUSED:
                self.task.status = mapped
            self.events.emit("progress", self.task)

            if mapped == DownloadStatus.COMPLETED and not self._completed_emitted:
                self._handle.pause()
                self.task.speed_bps = 0
                self._completed_emitted = True
                self.task.completed_at = time.time()
                self.events.emit("status", self.task)
                self.events.emit("complete", self.task)
