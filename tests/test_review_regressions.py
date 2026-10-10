"""Local-only regression coverage for the repository review fixes."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest

from core.events import EventEmitter
from core.http_downloader import HttpDownload
from core.manager import DownloadManager, TokenBucket, _cleanup_offline_task
from core.models import DownloadStatus, DownloadTask, DownloadType
from core.paths import safe_filename


@pytest.fixture
def manager(tmp_path):
    with (
        patch("core.manager.TorrentSession"),
        patch.object(DownloadManager, "_run_scheduler"),
    ):
        dm = DownloadManager(str(tmp_path), max_concurrent_downloads=1)
        dm._config["auto_extract"] = False
        yield dm
        dm.shutdown()


def test_legacy_torrent_cleanup_preserves_shared_files(tmp_path):
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("keep")
    task = DownloadTask("magnet:?x", str(tmp_path), DownloadType.TORRENT)
    _cleanup_offline_task(task)
    assert unrelated.read_text() == "keep"


def test_new_torrent_has_private_directory(manager):
    with patch.object(manager, "_maybe_start_next"):
        task = manager.add("magnet:?xt=urn:btih:123")
    assert task.owns_dest_dir
    assert task.dest_path.endswith(task.id)


def test_destinations_reserved_for_queue_and_server_renames(manager):
    with patch.object(manager, "_maybe_start_next"):
        a = manager.add("https://a.invalid/file.bin")
        b = manager.add("https://b.invalid/file.bin")
    assert a.dest_path != b.dest_path
    manager.reserve_filename(a, "same.bin")
    manager.reserve_filename(b, "same.bin")
    assert a.dest_path != b.dest_path


def test_resume_obeys_limit_and_queued_pause(manager):
    with patch.object(manager, "_maybe_start_next"):
        a = manager.add("https://a.invalid/a")
        b = manager.add("https://a.invalid/b")
        manager.pause(a.id)
        assert a.status == DownloadStatus.PAUSED
    with patch("core.manager.HttpDownload.start"):
        manager.resume(a.id)
        manager.resume(b.id)
    assert manager._active_count() == 1
    assert b.status == DownloadStatus.QUEUED


def test_remove_stops_engine(manager):
    with patch.object(manager, "_maybe_start_next"):
        task = manager.add("https://a.invalid/file")
    engine = Mock()
    manager._engines[task.id] = engine
    manager.remove_task(task.id)
    engine.cancel.assert_called_once_with(delete_files=False)
    assert manager.get(task.id) is None
    assert task.id not in manager._engines


def test_export_omits_credentials(manager, tmp_path):
    with patch.object(manager, "_maybe_start_next"):
        manager.add(
            "https://a.invalid/file",
            headers={"Cookie": "secret", "Authorization": "secret"},
        )
    destination = tmp_path / "export.json"
    manager.export_queue(str(destination))
    assert "secret" not in destination.read_text()
    assert "headers" not in json.loads(destination.read_text())[0]


def test_video_filename_and_category(manager):
    with patch.object(manager, "_maybe_start_next"):
        a = manager.add_video("https://a.invalid/watch", filename="../../video.mp4")
        b = manager.add_video("https://b.invalid/watch", filename="video.mp4")
    assert a.category == "Video"
    assert a.dest_path != b.dest_path
    assert ".." not in a.dest_path
    assert safe_filename("CON.txt") == "_CON.txt"


def test_bandwidth_switch_to_unlimited():
    bucket = TokenBucket(1)
    bucket._tokens = 0
    with patch(
        "core.manager.time.sleep", side_effect=lambda _: setattr(bucket, "rate", 0)
    ):
        bucket.consume(100)


def test_config_invalid_change_is_atomic(manager):
    original = manager.get_config()
    with pytest.raises(ValueError):
        manager.set_config({"max_concurrent_downloads": 2, "scheduler_start_hour": 25})
    assert manager.get_config() == original


def test_history_survives_directory_change(tmp_path):
    state = str(tmp_path / "state.json")
    with (
        patch("core.manager.TorrentSession"),
        patch.object(DownloadManager, "_run_scheduler"),
    ):
        first = DownloadManager(str(tmp_path / "original"), state_file=state)
        with patch.object(first, "_maybe_start_next"):
            task = first.add("https://example.invalid/file.bin")
            first.set_config(
                {"download_dir": str(tmp_path / "new"), "max_concurrent_downloads": 2}
            )
        first.shutdown()
        second = DownloadManager(str(tmp_path / "new"), state_file=state)
        try:
            assert second.get(task.id) is not None
            assert second.max_concurrent_downloads == 2
        finally:
            second.shutdown()


def test_manual_pause_is_not_resumed_by_policy(manager):
    with patch.object(manager, "_maybe_start_next"):
        task = manager.add("https://a.invalid/file")
        manager.pause(task.id, policy=True)
        assert task.id in manager._policy_paused
        manager.pause(task.id)
        assert task.id not in manager._policy_paused


def test_pause_all_does_not_start_queued_work(manager):
    with patch.object(manager, "_maybe_start_next"):
        a = manager.add("https://a.invalid/a")
        b = manager.add("https://a.invalid/b")
    with patch("core.manager.HttpDownload.start") as start:
        manager.pause_all()
    start.assert_not_called()
    assert a.status == b.status == DownloadStatus.PAUSED


def test_retry_active_task_does_not_stop_engine(manager):
    with patch.object(manager, "_maybe_start_next"):
        task = manager.add("https://a.invalid/file")
    task.status = DownloadStatus.DOWNLOADING
    engine = Mock()
    manager._engines[task.id] = engine
    manager.retry(task.id)
    engine.stop_threads.assert_not_called()


def test_ipc_contract_and_validation(manager):
    import urllib.error
    import urllib.request
    from core.ipc_server import IpcServer

    with patch.object(manager, "_maybe_start_next"):
        manager.add("https://a.invalid/file")
    server = IpcServer(manager, "test-token", port=0)
    server.start()
    try:

        def rpc(payload):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server._server.server_port}/rpc",
                data=json.dumps(payload).encode(),
                headers={"X-Auth-Token": "test-token"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)

        result = rpc({"method": "list_tasks"})["tasks"][0]
        assert result["status"] == "QUEUED"
        assert type(result["priority"]) is int
        for field in (
            "id",
            "source",
            "status",
            "file_path",
            "error",
            "category",
            "description",
        ):
            assert isinstance(result[field], str)
        for field in ("downloaded_bytes", "total_bytes"):
            assert type(result[field]) is int
        assert isinstance(result["speed_bps"], (float, int))
        assert isinstance(result["created_at"], (float, int))
        for payload in (
            [],
            {"method": "list_tasks", "args": []},
            {
                "method": "set_config",
                "args": {"config": {"max_concurrent_downloads": 0}},
            },
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                rpc(payload)
            assert error.value.code == 400
    finally:
        server.stop()


@pytest.fixture
def http_server():
    servers = []

    def start(mode):
        data = b"abcdefgh" * 65536
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("ETag", '"fixture"')
                self.end_headers()

            def do_GET(self):
                requested = self.headers.get("Range")
                calls.append(requested)
                start, end = 0, len(data) - 1
                ranged = requested and mode not in ("unknown", "nonrange")
                if ranged:
                    start, end = map(int, requested.removeprefix("bytes=").split("-"))
                if mode == "ignore" and requested != "bytes=0-0":
                    ranged = False
                    start, end = 0, len(data) - 1
                self.send_response(206 if ranged else 200)
                if ranged:
                    self.send_header(
                        "Content-Range", f"bytes {start}-{end}/{len(data)}"
                    )
                if mode != "unknown":
                    self.send_header("Content-Length", str(end - start + 1))
                self.send_header("ETag", '"fixture"')
                self.end_headers()
                payload = data[start : end + 1]
                # First full stream fails after some actual bytes were written.
                if mode == "nonrange" and len(calls) == 2:
                    payload = payload[:300000]
                try:
                    for offset in range(0, len(payload), 8192):
                        self.wfile.write(payload[offset : offset + 8192])
                        self.wfile.flush()
                        if mode == "slow":
                            time.sleep(0.005)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/file.bin", data, calls

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("mode", ["range", "unknown", "nonrange"])
def test_download_content_is_exact(mode, http_server, tmp_path):
    url, expected, calls = http_server(mode)
    task = DownloadTask(url, str(tmp_path / "output.bin"), DownloadType.HTTP)
    engine = HttpDownload(task, EventEmitter(), num_connections=2)
    engine.start()
    engine._controller_thread.join(15)
    assert not engine._controller_thread.is_alive()
    assert task.status == DownloadStatus.COMPLETED, task.error_message
    assert (tmp_path / "output.bin").read_bytes() == expected
    if mode == "unknown":
        assert len(calls) == 2


def test_range_ignored_fails_without_publishing(http_server, tmp_path):
    url, _, _ = http_server("ignore")
    task = DownloadTask(url, str(tmp_path / "output.bin"), DownloadType.HTTP)
    engine = HttpDownload(task, EventEmitter(), num_connections=2)
    engine.start()
    engine._controller_thread.join(15)
    assert task.status == DownloadStatus.ERROR
    assert "range response" in task.error_message
    assert not (tmp_path / "output.bin").exists()


def test_pause_resume_has_one_controller_and_exact_content(http_server, tmp_path):
    url, expected, _ = http_server("slow")
    task = DownloadTask(url, str(tmp_path / "output.bin"), DownloadType.HTTP)
    engine = HttpDownload(task, EventEmitter(), num_connections=1, chunk_size=8192)
    engine.start()
    deadline = time.monotonic() + 5
    while task.downloaded_bytes == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    previous = engine._controller_thread
    engine.pause()
    assert not previous.is_alive()
    assert task.status == DownloadStatus.PAUSED
    engine.resume()
    engine._controller_thread.join(15)
    assert task.status == DownloadStatus.COMPLETED, task.error_message
    assert (tmp_path / "output.bin").read_bytes() == expected
