import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import time

from core.manager import DownloadManager
from core.models import DownloadStatus
from local_range_server import start_server

import shutil
shutil.rmtree("queue_out", ignore_errors=True)

random.seed(1)
DATA = bytes(random.getrandbits(8) for _ in range(3 * 1024 * 1024))
start_server(DATA, port=8766)
time.sleep(0.2)
URL = "http://127.0.0.1:8766/{}"

manager = DownloadManager(download_dir="./queue_out", max_concurrent_downloads=1)
t1 = manager.add(URL.format("a.bin"), filename="a.bin")
t2 = manager.add(URL.format("b.bin"), filename="b.bin")

time.sleep(0.3)
print("right after adding both:")
print(" t1:", manager.get(t1.id).status.value)
print(" t2:", manager.get(t2.id).status.value)
assert manager.get(t1.id).status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING)
assert manager.get(t2.id).status == DownloadStatus.QUEUED, "t2 should wait -- max_concurrent_downloads=1"

start = time.time()
while manager.get(t1.id).status != DownloadStatus.COMPLETED:
    time.sleep(0.1)
    if time.time() - start > 20:
        print("TIMEOUT waiting on t1")
        break

time.sleep(0.3)
print("\nafter t1 completes:")
print(" t1:", manager.get(t1.id).status.value)
print(" t2:", manager.get(t2.id).status.value)
assert manager.get(t2.id).status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONNECTING), "t2 should auto-start"

manager.shutdown()
print("\nqueueing behavior correct")
