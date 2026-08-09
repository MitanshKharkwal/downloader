import os
import sys
import time
import tempfile
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manager import DownloadManager
from core.models import DownloadStatus
from local_range_server import start_server
import random

random.seed(3)
DATA = bytes(random.getrandbits(8) for _ in range(3 * 1024 * 1024))  # 3MB, big enough to catch mid-flight
start_server(DATA, port=8988)
time.sleep(0.2)
URL = "http://127.0.0.1:8988/file.bin"

import shutil
test_dir = os.path.join(tempfile.gettempdir(), "persist_test")
shutil.rmtree(test_dir, ignore_errors=True)
os.makedirs(test_dir, exist_ok=True)

# --- Test 1: deterministic filename -------------------------------------
m1 = DownloadManager(download_dir=test_dir, max_concurrent_downloads=1)
name1 = m1._filename_from_url("http://example.com/weird?query=only&no=path")
name2 = m1._filename_from_url("http://example.com/weird?query=only&no=path")
print(f"same URL -> same fallback name: {name1 == name2} ({name1})")
assert name1 == name2

# --- Test 2: state persists across a manager restart ----------------------
m1 = DownloadManager(download_dir=test_dir, max_concurrent_downloads=1)
t1 = m1.add(URL, filename="download1.bin")  # will actually start downloading
t2 = m1.add(URL + "?v=2", filename="download2.bin")  # stays QUEUED (max_concurrent=1)

start_wait = time.time()
while m1.get(t1.id).downloaded_bytes == 0 and time.time() - start_wait < 5.0:
    time.sleep(0.1)
time.sleep(0.2)


print(f"\nbefore restart: t1={m1.get(t1.id).status.value}  t2={m1.get(t2.id).status.value}")
assert m1.get(t1.id).status == DownloadStatus.DOWNLOADING
assert m1.get(t2.id).status == DownloadStatus.QUEUED

m1.shutdown()  # simulates closing the app -- writes final state

# Fresh manager instance, same download_dir -- simulates reopening the app
m2 = DownloadManager(download_dir=test_dir, max_concurrent_downloads=1)
reloaded = {t.id: t for t in m2.list_tasks()}
print(f"tasks reloaded: {len(reloaded)}")
assert len(reloaded) == 2

r1, r2 = reloaded[t1.id], reloaded[t2.id]
print(f"after restart: t1={r1.status.value} ({r1.downloaded_bytes} bytes)  t2={r2.status.value}")
# t1 was DOWNLOADING when saved -- should come back PAUSED (safe default), not lost
assert r1.status == DownloadStatus.PAUSED
assert r1.downloaded_bytes > 0, "progress should have been preserved, not reset to 0"
assert r2.status == DownloadStatus.QUEUED

# And resuming it should actually pick up from where it left off, not restart from 0
m2.resume(t1.id)
time.sleep(1.0)
final = m2.get(t1.id)
print(f"after resume: status={final.status.value}  {final.downloaded_bytes}/{final.total_bytes}")
assert final.downloaded_bytes >= r1.downloaded_bytes, "resume should not lose already-downloaded bytes"

m2.shutdown()

# --- Test 3: cancel deletes the partial file -------------------------------
cancel_dir = os.path.join(test_dir, "cancel_test")
shutil.rmtree(cancel_dir, ignore_errors=True)
os.makedirs(cancel_dir, exist_ok=True)
m3 = DownloadManager(download_dir=cancel_dir, max_concurrent_downloads=1)
t3 = m3.add(URL, filename="to_cancel.bin")
print(f"\nt3 status right after add: {m3.get(t3.id).status.value}, error: {m3.get(t3.id).error_message!r}")
time.sleep(0.3)
t3_now = m3.get(t3.id)
print(f"t3 status after 0.3s: {t3_now.status.value}, downloaded: {t3_now.downloaded_bytes}, error: {t3_now.error_message!r}")
part_path = os.path.join(cancel_dir, "Other", "to_cancel.bin.part")
print(f"dir contents: {os.listdir(cancel_dir)}")
print(f"part file exists before cancel: {os.path.exists(part_path)}")
assert os.path.exists(part_path)

m3.cancel(t3.id)

for _ in range(30):
    if not os.path.exists(part_path):
        break
    time.sleep(0.1)
    
print(f"part file exists after cancel: {os.path.exists(part_path)}")
assert not os.path.exists(part_path), "canceling should clean up the partial file"

m3.shutdown()
print("\nall persistence/determinism/cleanup tests passed")
