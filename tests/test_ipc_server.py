import json
import os
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ipc_server import IpcServer
from core.manager import DownloadManager


def test_shutdown():
    import unittest.mock
    with unittest.mock.patch("os._exit") as mock_exit:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = os.path.join(tmpdir, "state.json")
            manager = DownloadManager(download_dir=tmpdir, state_file=state_file)

            token_path = os.path.join(tmpdir, "token.txt")
            with open(token_path, "w") as f:
                f.write("test_token")

            ipc = IpcServer(manager, "test_token", port=47823)
            ipc.start()
            time.sleep(0.1)

            try:
                # Call shutdown
                req = urllib.request.Request(
                    "http://127.0.0.1:47823/rpc",
                    data=json.dumps({"method": "shutdown"}).encode(),
                    headers={"X-Auth-Token": "test_token", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read())
                    assert data["ok"] is True

                time.sleep(1)  # wait for shutdown to complete

                assert os.path.exists(state_file)
                mock_exit.assert_called_once_with(0)
                print("Fix 5 test passed!")
            finally:
                ipc.stop()


def test_set_priority():
    import urllib.error
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "state.json")
        manager = DownloadManager(download_dir=tmpdir, state_file=state_file)
        task = manager.add("http://example.com/file.txt")

        ipc = IpcServer(manager, "test_token", port=47824)
        ipc.start()
        time.sleep(0.1)

        try:
            # Test valid priority
            req = urllib.request.Request(
                "http://127.0.0.1:47824/rpc",
                data=json.dumps({"method": "set_priority", "args": {"task_id": task.id, "priority": 2}}).encode(),
                headers={"X-Auth-Token": "test_token", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                assert data["ok"] is True
            assert manager.get(task.id).priority == 2

            # Test invalid priority string
            req = urllib.request.Request(
                "http://127.0.0.1:47824/rpc",
                data=json.dumps({"method": "set_priority", "args": {"task_id": task.id, "priority": "invalid"}}).encode(),
                headers={"X-Auth-Token": "test_token", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read())
                    assert data["ok"] is False
            except urllib.error.HTTPError as e:
                assert e.code == 400
                data = json.loads(e.read().decode())
                assert data["ok"] is False
                assert "Invalid priority" in data["error"]
        finally:
            ipc.stop()


if __name__ == "__main__":
    test_shutdown()
    test_set_priority()
