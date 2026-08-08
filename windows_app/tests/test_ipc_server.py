import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import urllib.error
import urllib.request

from ipc_server import IpcServer, load_or_create_token

TOKEN_PATH = "/tmp/dm_test_token.txt"
if os.path.exists(TOKEN_PATH):
    os.remove(TOKEN_PATH)

token = load_or_create_token(TOKEN_PATH)
token2 = load_or_create_token(TOKEN_PATH)
assert token == token2, "token should be stable across reloads"
print("token loaded/created ok, length:", len(token))

received = []


def add_callback(source: str) -> dict:
    received.append(source)
    return {"id": "task123", "status": "queued"}


server = IpcServer(add_callback, token, port=47822)
server.start()
time.sleep(0.2)

# ping
with urllib.request.urlopen("http://127.0.0.1:47822/ping") as resp:
    print("ping:", json.loads(resp.read()))

# unauthorized add
req = urllib.request.Request(
    "http://127.0.0.1:47822/add",
    data=json.dumps({"source": "magnet:?xt=urn:btih:deadbeef"}).encode(),
    method="POST",
)
try:
    urllib.request.urlopen(req)
    print("FAIL: unauthorized request should have been rejected")
except urllib.error.HTTPError as e:
    print("unauthorized correctly rejected:", e.code)

# authorized add
req = urllib.request.Request(
    "http://127.0.0.1:47822/add",
    data=json.dumps({"source": "magnet:?xt=urn:btih:deadbeef"}).encode(),
    headers={"X-Auth-Token": token, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())
    print("authorized add:", result)
    assert result["ok"] and result["id"] == "task123"

assert received == ["magnet:?xt=urn:btih:deadbeef"]
print("callback received source correctly")

server.stop()
print("\nIPC server test passed")
