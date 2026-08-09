"""Shared data models for the download manager core."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class DownloadType(str, Enum):
    HTTP = "http"
    TORRENT = "torrent"
    VIDEO = "video"


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    CONNECTING = "connecting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELED = "canceled"


class Priority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2


@dataclass
class DownloadTask:
    """A single download job tracked by the DownloadManager.

    Works for both HTTP downloads and torrents/magnets -- the fields that
    don't apply to a given type (e.g. num_peers for HTTP) just stay at
    their default.
    """

    source: str  # URL, magnet URI, or path to a .torrent file
    dest_path: str  # where the final file(s) land
    type: DownloadType
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: DownloadStatus = DownloadStatus.QUEUED
    priority: Priority = Priority.NORMAL

    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed_bps: float = 0.0  # bytes/sec, rolling estimate

    # HTTP-specific
    num_connections: int = 8
    supports_ranges: bool = False

    # Torrent-specific
    num_peers: int = 0
    num_seeds: int = 0
    name: str = ""

    error_message: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def progress(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.downloaded_bytes / self.total_bytes)

    def eta_seconds(self) -> float | None:
        if self.speed_bps <= 0 or self.total_bytes <= 0:
            return None
        remaining = self.total_bytes - self.downloaded_bytes
        if remaining <= 0:
            return 0
        return remaining / self.speed_bps

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["type"] = self.type.value
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        d["progress"] = round(self.progress(), 4)
        d["eta_seconds"] = self.eta_seconds()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DownloadTask":
        # progress/eta_seconds are computed display fields added by
        # to_dict(), not real constructor args -- drop them before
        # rebuilding, and convert the enum fields back from their
        # plain string form.
        d = {k: v for k, v in d.items() if k not in ("progress", "eta_seconds")}
        d["type"] = DownloadType(d["type"])
        d["status"] = DownloadStatus(d["status"])
        if "priority" in d:
            d["priority"] = Priority(d["priority"])
        return cls(**d)
