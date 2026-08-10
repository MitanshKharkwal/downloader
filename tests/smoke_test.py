import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import os
import time

import requests

from core.events import EventEmitter
from core.http_downloader import HttpDownload
from core.models import DownloadStatus, DownloadTask, DownloadType

URL = "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl"

os.makedirs("smoke_out", exist_ok=True)
dest = "smoke_out/pip.whl"
if os.path.exists(dest):
    os.remove(dest)

task = DownloadTask(
    source=URL, dest_path=dest, type=DownloadType.HTTP, num_connections=6
)
events = EventEmitter()
progress_ticks = []
events.on("progress", lambda t: progress_ticks.append(t.downloaded_bytes))

dl = HttpDownload(task, events, num_connections=6)
dl.start()

start = time.time()
while task.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
    time.sleep(0.2)
    if time.time() - start > 60:
        print("TIMEOUT")
        break

assert task.status == DownloadStatus.COMPLETED, (
    f"task failed with status {task.status}, error: {task.error_message}"
)

print("status:", task.status, "error:", task.error_message)
print("downloaded_bytes:", task.downloaded_bytes, "total_bytes:", task.total_bytes)
print("progress events received:", len(progress_ticks))
print("peak speed sample (bytes/s):", task.speed_bps)

# Reference: plain single-shot download, compare hashes.
ref = requests.get(URL, timeout=30).content
seg_hash = hashlib.sha256(open(dest, "rb").read()).hexdigest()
ref_hash = hashlib.sha256(ref).hexdigest()
print("segmented sha256:", seg_hash)
print("reference sha256:", ref_hash)
print("MATCH:", seg_hash == ref_hash)

# Confirm the pause/resume machinery round-trips a state file correctly
# by re-running against a fresh dest with an artificial pause partway.
dest2 = "smoke_out/pip_resume_test.whl"
if os.path.exists(dest2):
    os.remove(dest2)
if os.path.exists(dest2 + ".dmpart.json"):
    os.remove(dest2 + ".dmpart.json")

task2 = DownloadTask(
    source=URL, dest_path=dest2, type=DownloadType.HTTP, num_connections=4
)
events2 = EventEmitter()
dl2 = HttpDownload(task2, events2, num_connections=4)
dl2.start()
time.sleep(0.4)
dl2.pause()
paused_bytes = task2.downloaded_bytes
time.sleep(0.5)
print(
    "\npaused at:",
    paused_bytes,
    "bytes; state file exists:",
    os.path.exists(dest2 + ".dmpart.json"),
)

dl3 = HttpDownload(task2, events2, num_connections=4)
dl3.start()
start = time.time()
while task2.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
    time.sleep(0.2)
    if time.time() - start > 60:
        print("TIMEOUT on resume")
        break

resumed_hash = hashlib.sha256(open(dest2, "rb").read()).hexdigest()
print("status after resume:", task2.status)
print("resumed sha256 matches reference:", resumed_hash == ref_hash)
