import os
import struct
import subprocess
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))  # native_host/tests
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))  # download_manager/
sys.path.insert(0, _PROJECT_ROOT)

import json

from core.ipc_server import IpcServer, load_or_create_token

HOST_SCRIPT = os.path.join(_PROJECT_ROOT, "native_host", "host.py")
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")


def run_host_once(message: dict) -> dict:
    """Spawn host.py exactly like Chrome's sendNativeMessage does: write
    one framed message to stdin, read one framed response from stdout,
    let the process exit."""
    proc = subprocess.Popen(
        [sys.executable, HOST_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    encoded = json.dumps(message).encode("utf-8")
    proc.stdin.write(struct.pack("=I", len(encoded)))
    proc.stdin.write(encoded)
    proc.stdin.close()

    raw_length = proc.stdout.read(4)
    if len(raw_length) < 4:
        stderr = proc.stderr.read().decode(errors="replace")
        raise RuntimeError(f"host produced no valid response. stderr:\n{stderr}")
    length = struct.unpack("=I", raw_length)[0]
    data = proc.stdout.read(length)
    proc.wait(timeout=5)
    return json.loads(data.decode("utf-8"))


# --- Test 1: app not running yet (no token) -----------------------------
os.makedirs(APP_DATA_DIR, exist_ok=True)
if os.path.exists(TOKEN_PATH):
    os.remove(TOKEN_PATH)

result = run_host_once({"action": "ping"})
print("ping with no app running:", result)
assert result == {"ok": True, "pong": True, "app_token_found": False}

result = run_host_once({"action": "add", "source": "magnet:?xt=urn:btih:deadbeef"})
print("add with no app running:", result)
assert result["ok"] is False

# --- Test 2: app running, real IPC server --------------------------------
received = []


def add_callback(source: str) -> dict:
    received.append(source)
    return {"id": "abc123", "status": "queued"}


token = load_or_create_token(TOKEN_PATH)
server = IpcServer(add_callback, token, port=47821)
server.start()
time.sleep(0.2)

result = run_host_once({"action": "ping"})
print("\nping with app running:", result)
assert result == {"ok": True, "pong": True, "app_token_found": True}

result = run_host_once(
    {"action": "add", "source": "magnet:?xt=urn:btih:cafebabe", "filename": None}
)
print("add (magnet) with app running:", result)
assert result["ok"] is True and result["id"] == "abc123"
assert received == ["magnet:?xt=urn:btih:cafebabe"]

result = run_host_once({"action": "add", "source": "https://example.com/file.zip"})
print("add (http) with app running:", result)
assert result["ok"] is True
assert received == ["magnet:?xt=urn:btih:cafebabe", "https://example.com/file.zip"]

result = run_host_once({"action": "bogus"})
print("unknown action:", result)
assert result["ok"] is False

server.stop()
print("\nnative host <-> IPC server integration test passed")
