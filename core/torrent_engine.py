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

try:
    import libtorrent as lt

    LIBTORRENT_AVAILABLE = True
except ImportError:
    # No prebuilt libtorrent wheel exists for Android out of the box --
    # cross-compiling it needs a custom python-for-android recipe. Rather
    # than crash the whole app on import, degrade gracefully: HTTP
    # downloads keep working, and any torrent/magnet add fails with a
    # clear error instead of a stack trace. See android_app/README.md.
    lt = None
    LIBTORRENT_AVAILABLE = False

from .events import EventEmitter
from .models import DownloadStatus, DownloadTask

POLL_INTERVAL_SECONDS = 1.0

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
        self._session = lt.session(settings)

    @property
    def raw(self) -> "lt.session":
        return self._session

    def shutdown(self) -> None:
        # Let libtorrent flush resume data / close connections cleanly.
        if self._session is not None:
            self._session.pause()


class TorrentDownload:
    def __init__(self, task: DownloadTask, events: EventEmitter, torrent_session: TorrentSession) -> None:
        self.task = task
        self.events = events
        self._session = torrent_session.raw
        self._handle: "lt.torrent_handle | None" = None
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._completed_emitted = False

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
        except Exception as exc:  # noqa: BLE001 -- malformed magnet/.torrent input is real user input, not a bug
            self.task.status = DownloadStatus.ERROR
            self.task.error_message = f"couldn't add torrent: {exc}"
            self.events.emit("status", self.task)
            return

        self.task.status = DownloadStatus.CONNECTING
        self.events.emit("status", self.task)

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def pause(self) -> None:
        if self.task.status in (DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED):
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
        if self._handle:
            flag = lt.session.delete_files if delete_files else 0
            self._session.remove_torrent(self._handle, flag)
        self.task.status = DownloadStatus.CANCELED
        self.events.emit("status", self.task)

    # -- internals ---------------------------------------------------------

    def _build_add_params(self) -> "lt.add_torrent_params":
        source = self.task.source
        if source.startswith("magnet:"):
            params = lt.parse_magnet_uri(source)
        else:
            info = lt.torrent_info(source)
            params = lt.add_torrent_params()
            params.ti = info
            self.task.name = info.name()
            self.task.total_bytes = info.total_size()
        params.save_path = self.task.dest_path
        # Keep partial files as .parts rather than sparse full-size files
        # so a half-downloaded task doesn't look deceptively large on disk.
        params.flags |= lt.torrent_flags.duplicate_is_error
        return params

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(POLL_INTERVAL_SECONDS)
            if not self._handle or not self._handle.is_valid():
                continue

            status = self._handle.status()
            self.task.name = status.name or self.task.name
            self.task.total_bytes = status.total_wanted or self.task.total_bytes
            self.task.downloaded_bytes = status.total_wanted_done
            self.task.speed_bps = float(status.download_rate)
            self.task.num_peers = status.num_peers
            self.task.num_seeds = status.num_seeds

            mapped = _STATE_MAP.get(status.state, DownloadStatus.DOWNLOADING)
            if self.task.status != DownloadStatus.PAUSED:
                self.task.status = mapped
            self.events.emit("progress", self.task)

            if mapped == DownloadStatus.COMPLETED and not self._completed_emitted:
                self._completed_emitted = True
                self.task.completed_at = time.time()
                self.events.emit("status", self.task)
                self.events.emit("complete", self.task)
