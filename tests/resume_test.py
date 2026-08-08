import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import os
import random
import time

from core.events import EventEmitter
from core.http_downloader import HttpDownload
from core.models import DownloadStatus, DownloadTask, DownloadType
from local_range_server import start_server

random.seed(42)
DATA = bytes(random.getrandbits(8) for _ in range(600 * 1024))  # 600KB synthetic file
REF_HASH = hashlib.sha256(DATA).hexdigest()

start_server(DATA, port=8765)
time.sleep(0.2)
URL = "http://127.0.0.1:8765/file.bin"

os.makedirs("resume_out", exist_ok=True)
dest = "resume_out/file.bin"
for p in (dest, dest + ".part", dest + ".dmpart.json"):
    if os.path.exists(p):
        os.remove(p)

task = DownloadTask(source=URL, dest_path=dest, type=DownloadType.HTTP, num_connections=4)
events = EventEmitter()
dl = HttpDownload(task, events, num_connections=4)
dl.start()

time.sleep(1.0)  # let it get partway through (~600KB at ~2MB/s across 4 conns, throttled)
assert task.status == DownloadStatus.DOWNLOADING, f"expected still downloading, got {task.status}"
mid_bytes = task.downloaded_bytes
print(f"mid-flight: {mid_bytes}/{task.total_bytes} bytes ({task.progress()*100:.1f}%)")
assert 0 < mid_bytes < task.total_bytes, "test timing didn't land mid-flight -- adjust DELAY/sleep"

dl.pause()
time.sleep(0.3)
print("paused at:", task.downloaded_bytes, "status:", task.status)
assert os.path.exists(dest + ".dmpart.json")

# Simulate an app restart: brand new HttpDownload instance, same task/dest.
dl2 = HttpDownload(task, events, num_connections=4)
dl2.start()
task.status = DownloadStatus.DOWNLOADING  # dl2.start() will set this itself; just being explicit
start = time.time()
while task.status not in (DownloadStatus.COMPLETED, DownloadStatus.ERROR):
    time.sleep(0.1)
    if time.time() - start > 30:
        print("TIMEOUT")
        break

final_hash = hashlib.sha256(open(dest, "rb").read()).hexdigest()
print("final status:", task.status)
print("final bytes:", task.downloaded_bytes, "/", task.total_bytes)
print("hash matches original:", final_hash == REF_HASH)
print("state file cleaned up:", not os.path.exists(dest + ".dmpart.json"))
