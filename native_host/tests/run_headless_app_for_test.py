import os
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_ROOT)

from core.ipc_server import IpcServer, load_or_create_token
from core.manager import DownloadManager

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
DOWNLOAD_DIR = os.path.join(APP_DATA_DIR, "downloads")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
manager = DownloadManager(download_dir=DOWNLOAD_DIR, max_concurrent_downloads=3)
token = load_or_create_token(TOKEN_PATH)
ipc = IpcServer(
    manager.add
    if False
    else (lambda source: {"id": manager.add(source).id, "status": "queued"}),
    token,
)
ipc.start()
print(f"headless app running, IPC on 127.0.0.1:{ipc.port}, token file at {TOKEN_PATH}")

while True:
    time.sleep(1)
    for t in manager.list_tasks():
        print(f"  task {t.id}: {t.type.value} {t.status.value} {t.source[:60]}")
