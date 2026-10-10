"""Check real libtorrent metadata and file selection without external peers."""

import time
from types import SimpleNamespace

import pytest

from core.events import EventEmitter
from core.models import DownloadTask, DownloadType
from core.torrent_engine import LIBTORRENT_AVAILABLE, TorrentDownload


@pytest.mark.skipif(not LIBTORRENT_AVAILABLE, reason="libtorrent unavailable")
def test_local_torrent_file_selection(tmp_path):
    import libtorrent as lt

    source = tmp_path / "source" / "collection"
    source.mkdir(parents=True)
    (source / "one.txt").write_text("one")
    (source / "two.txt").write_text("two")
    files = lt.file_storage()
    files.add_file("collection/one.txt", 3)
    files.add_file("collection/two.txt", 3)
    torrent = lt.create_torrent(files)
    lt.set_piece_hashes(torrent, str(tmp_path / "source"))
    metadata = tmp_path / "fixture.torrent"
    metadata.write_bytes(lt.bencode(torrent.generate()))

    session = lt.session(
        {
            "listen_interfaces": "127.0.0.1:0",
            "enable_dht": False,
            "enable_lsd": False,
            "enable_upnp": False,
            "enable_natpmp": False,
        }
    )
    task = DownloadTask(str(metadata), str(tmp_path / "download"), DownloadType.TORRENT)
    engine = TorrentDownload(task, EventEmitter(), SimpleNamespace(raw=session))
    try:
        engine.start()
        deadline = time.monotonic() + 5
        while not engine.list_files() and time.monotonic() < deadline:
            time.sleep(0.05)
        listing = engine.list_files()
        visible = [
            file["name"].replace("\\", "/") for file in listing if not file["pad"]
        ]
        assert visible == ["collection/one.txt", "collection/two.txt"]
        assert any(file["pad"] for file in listing)
        priorities = [
            4
            if file["name"].endswith("one.txt")
            else 0
            if not file["pad"]
            else file["priority"]
            for file in listing
        ]
        engine.set_file_priorities(priorities)
        deadline = time.monotonic() + 5
        while [file["priority"] for file in engine.list_files() if not file["pad"]] != [
            4,
            0,
        ] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert [
            file["priority"] for file in engine.list_files() if not file["pad"]
        ] == [4, 0]
    finally:
        engine.stop_threads()
        session.pause()
