import json
import os
import tempfile
import time
import urllib.request

from core.manager import DownloadManager
from core.ipc_server import IpcServer

def test_shutdown():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "state.json")
        manager = DownloadManager(download_dir=tmpdir, state_file=state_file)
        
        token_path = os.path.join(tmpdir, "token.txt")
        with open(token_path, "w") as f:
            f.write("test_token")
        
        ipc = IpcServer(manager, "test_token", port=47823)
        ipc.start()
        time.sleep(0.1)
        
        # Call shutdown
        req = urllib.request.Request(
            "http://127.0.0.1:47823/rpc",
            data=json.dumps({"method": "shutdown"}).encode(),
            headers={"X-Auth-Token": "test_token", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            assert data["ok"] is True
            
        time.sleep(1) # wait for shutdown to complete
        
        assert os.path.exists(state_file)
        print("Fix 5 test passed!")

if __name__ == '__main__':
    test_shutdown()
