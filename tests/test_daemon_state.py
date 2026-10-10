"""Verify the real daemon IPC contract without touching user state."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def test_daemon_migrates_state_and_restarts_after_directory_change(tmp_path):
    data_dir = tmp_path / "app"
    original = tmp_path / "original"
    new = tmp_path / "new"
    data_dir.mkdir()
    original.mkdir()
    (data_dir / "config.json").write_text(json.dumps({"download_dir": str(original)}))
    (original / ".dm_state.json").write_text(
        json.dumps(
            {
                "config": {"download_dir": str(original), "auto_extract": False},
                "tasks": [
                    {
                        "id": "fixture",
                        "source": "https://example.invalid/file",
                        "dest_path": str(original / "file"),
                        "type": "http",
                        "status": "paused",
                    }
                ],
            }
        )
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "DOWNLOAD_MANAGER_DATA_DIR": str(data_dir),
        "DOWNLOAD_MANAGER_IPC_PORT": str(port),
        "DOWNLOAD_MANAGER_CLIPBOARD": "0",
    }

    def rpc(method, args=None):
        token = (data_dir / "ipc_token.txt").read_text().strip()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/rpc",
            data=json.dumps({"method": method, "args": args or {}}).encode(),
            headers={"X-Auth-Token": token},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    for first_run in (True, False):
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "daemon.py")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    result = rpc("list_tasks")
                    break
                except (OSError, urllib.error.URLError):
                    assert process.poll() is None, (data_dir / "daemon.log").read_text()
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
            task = result["tasks"][0]
            assert task["id"] == "fixture"
            assert task["status"] == "PAUSED"
            assert type(task["priority"]) is int
            assert {
                "id",
                "source",
                "status",
                "priority",
                "downloaded_bytes",
                "total_bytes",
                "speed_bps",
                "file_path",
                "error",
                "category",
                "created_at",
                "description",
            } <= task.keys()
            if first_run:
                rpc(
                    "set_config",
                    {
                        "config": {
                            "download_dir": str(new),
                            "max_concurrent_downloads": 2,
                        }
                    },
                )
            else:
                config = rpc("get_config")["config"]
                assert config["download_dir"] == str(new)
                assert config["max_concurrent_downloads"] == 2
            rpc("shutdown")
            process.wait(timeout=15)
            assert process.returncode == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    assert (data_dir / "state.json").exists()
    assert (original / ".dm_state.json").exists()
