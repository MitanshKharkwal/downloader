import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

from core.manager import DownloadManager
from core.models import DownloadStatus

# A well-known, legal public-domain test magnet (Big Buck Bunny sample, widely
# used as a BitTorrent protocol test fixture).
MAGNET = (
    "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c"
    "&dn=Big+Buck+Bunny&tr=udp://tracker.openbittorrent.com:80"
)

manager = DownloadManager(download_dir="./torrent_downloads", max_concurrent_downloads=2)
task = manager.add(MAGNET)
print("task created:", task.id, task.type.value, task.status.value)

for _ in range(5):
    time.sleep(1)
    t = manager.get(task.id)
    print(f"status={t.status.value} peers={t.num_peers} seeds={t.num_seeds} "
          f"downloaded={t.downloaded_bytes} name={t.name!r}")

manager.pause(task.id)
time.sleep(0.5)
print("after pause:", manager.get(task.id).status.value)

manager.cancel(task.id)
time.sleep(0.5)
print("after cancel:", manager.get(task.id).status.value)

manager.shutdown()
print("shutdown clean")
