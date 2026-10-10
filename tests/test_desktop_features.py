"""Desktop feature bridge coverage, with no public-network downloads."""

import json
import urllib.request
from unittest.mock import Mock, patch

import pytest

from core.ipc_server import IpcServer
from core.manager import DownloadManager
from core.models import DownloadStatus
from core.torrent_engine import TorrentDownload


@pytest.fixture
def bridge(tmp_path):
    with (
        patch("core.manager.TorrentSession"),
        patch.object(DownloadManager, "_run_scheduler"),
        patch.object(DownloadManager, "_maybe_start_next"),
    ):
        manager = DownloadManager(
            str(tmp_path), state_file=str(tmp_path / "state.json")
        )
        server = IpcServer(manager, "test", port=0)
        server.start()

        def rpc(method, args):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server._server.server_port}/rpc",
                data=json.dumps({"method": method, "args": args}).encode(),
                headers={"X-Auth-Token": "test"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)

        yield manager, rpc
        server.stop()
        manager.shutdown()


def test_advanced_download_details_and_queue_roundtrip(bridge, tmp_path):
    manager, rpc = bridge
    assert rpc("get_capabilities", {})["protocol"] == 2
    result = rpc(
        "add_download",
        {
            "source": "https://example.invalid/a.zip",
            "headers": {"Authorization": "private"},
            "mirrors": ["https://mirror.invalid/a.zip"],
        },
    )
    task = manager.get(result["id"])
    assert task.mirrors == ["https://mirror.invalid/a.zip"]
    details = rpc("task_details", {"task_id": task.id})["task"]
    assert "headers" not in details
    assert details["type"] == "http"
    rpc(
        "add_video_task",
        {"url": "https://example.invalid/video", "format_id": "bestaudio"},
    )
    queue = str(tmp_path / "queue.json")
    rpc("export_queue", {"file_path": queue})
    assert "private" not in (tmp_path / "queue.json").read_text()
    result = rpc("import_queue", {"file_path": queue})
    assert result["imported"] == 2 and result["failed"] == 0


def test_bad_mirrors_and_queue_are_rejected(bridge, tmp_path):
    manager, _ = bridge
    with pytest.raises(ValueError, match="Mirrors"):
        manager.add("https://example.invalid/file", mirrors=["file:///private"])
    queue = tmp_path / "bad.json"
    queue.write_text("{}")
    with pytest.raises(ValueError, match="Queue"):
        manager.import_queue(str(queue))
    assert not manager.list_tasks()


def test_torrent_selection_validation_and_persistence(bridge):
    manager, rpc = bridge
    task = manager.add("magnet:?xt=urn:btih:123")
    engine = Mock(spec=TorrentDownload)
    engine.list_files.return_value = [{"pad": False}, {"pad": False}]
    manager._engines[task.id] = engine
    rpc("set_file_priorities", {"task_id": task.id, "priorities": [4, 0]})
    engine.set_file_priorities.assert_called_once_with([4, 0])
    assert task.file_priorities == [4, 0]
    with pytest.raises(ValueError):
        manager.set_file_priorities(task.id, [0, 0])


def test_explicit_destination_overrides_category_folder(bridge, tmp_path):
    manager, _ = bridge
    manager._config["category_dirs"] = {"Documents": str(tmp_path / "category")}
    task = manager.add(
        "https://example.invalid/file.pdf", dest_dir=str(tmp_path / "chosen")
    )
    assert task.dest_path == str(tmp_path / "chosen" / "file.pdf")
    manager._config["category_dirs"]["Torrents"] = str(tmp_path / "torrents")
    torrent = manager.add("magnet:?xt=urn:btih:123", dest_dir=str(tmp_path / "chosen"))
    duplicate = manager.add(
        "magnet:?xt=urn:btih:123", dest_dir=str(tmp_path / "chosen")
    )
    assert torrent.id == duplicate.id


def test_urgent_pauses_other_downloads_and_pause_releases_them(bridge):
    manager, rpc = bridge
    a = manager.add("https://example.invalid/a")
    b = manager.add("https://example.invalid/b")
    a.status = DownloadStatus.DOWNLOADING
    rpc("set_urgent", {"task_id": b.id})
    assert a.status == DownloadStatus.PAUSED
    assert a.id in manager._paused_for_urgent_task_ids
    manager.pause(b.id)
    assert manager._urgent_task_id is None
    assert a.id in manager._policy_paused
