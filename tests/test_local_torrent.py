"""Check real libtorrent metadata and file selection without external peers."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import unquote_to_bytes, urlsplit

import pytest

from core.events import EventEmitter
from core.models import DownloadTask, DownloadType
from core.torrent_engine import (
    LIBTORRENT_AVAILABLE,
    TorrentDownload,
    inspect_torrent_file,
)


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

    preview = inspect_torrent_file(str(metadata), scrape_timeout=0)
    assert preview["name"] == "collection"
    assert preview["total_size"] == 6
    assert [file["name"].replace("\\", "/") for file in preview["files"] if not file["pad"]] == [
        "collection/one.txt",
        "collection/two.txt",
    ]
    assert preview["seeds"] is None and preview["peers"] is None

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
    task.file_priorities = [
        0 if file["pad"] or file["name"].endswith("one.txt") else 4
        for file in preview["files"]
    ]
    engine = TorrentDownload(task, EventEmitter(), SimpleNamespace(raw=session))
    try:
        engine.start()
        deadline = time.monotonic() + 5
        while not engine.list_files() and time.monotonic() < deadline:
            time.sleep(0.05)
        listing = engine.list_files()
        visible = [file["name"].replace("\\", "/") for file in listing if not file["pad"]]
        assert visible == ["collection/one.txt", "collection/two.txt"]
        assert any(file["pad"] for file in listing)
        assert [file["priority"] for file in listing if not file["pad"]] == [0, 4]
        priorities = [
            4 if file["name"].endswith("one.txt") else 0 if not file["pad"] else file["priority"]
            for file in listing
        ]
        engine.set_file_priorities(priorities)
        deadline = time.monotonic() + 5
        while [file["priority"] for file in engine.list_files() if not file["pad"]] != [
            4,
            0,
        ] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert [file["priority"] for file in engine.list_files() if not file["pad"]] == [4, 0]
    finally:
        engine.stop_threads()
        session.pause()


@pytest.mark.skipif(not LIBTORRENT_AVAILABLE, reason="libtorrent unavailable")
def test_torrent_preview_reads_tracker_scrape_without_starting_download(tmp_path):
    import libtorrent as lt

    class Tracker(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            assert urlsplit(self.path).path == "/scrape"
            encoded = urlsplit(self.path).query.split("info_hash=", 1)[1]
            info_hash = unquote_to_bytes(encoded)
            body = lt.bencode(
                {b"files": {info_hash: {b"complete": 7, b"incomplete": 3}}}
            )
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Tracker)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = tmp_path / "sample.bin"
        source.write_bytes(b"fixture")
        files = lt.file_storage()
        files.add_file("sample.bin", 7)
        torrent = lt.create_torrent(files)
        torrent.add_tracker(f"http://127.0.0.1:{server.server_port}/announce")
        lt.set_piece_hashes(torrent, str(tmp_path))
        metadata = tmp_path / "sample.torrent"
        metadata.write_bytes(lt.bencode(torrent.generate()))
        preview = inspect_torrent_file(str(metadata), scrape_timeout=2)
        assert preview["seeds"] == 7
        assert preview["peers"] == 3
        assert preview["tracker_status"] == "Live tracker scrape"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
