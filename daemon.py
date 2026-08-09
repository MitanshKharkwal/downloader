import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.manager import DownloadManager
from core.ipc_server import IpcServer, load_or_create_token

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
DOWNLOAD_DIR = os.path.join(APP_DATA_DIR, "downloads")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")

def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    manager = DownloadManager(
        download_dir=DOWNLOAD_DIR, max_concurrent_downloads=3
    )
    
    token = load_or_create_token(TOKEN_PATH)
    ipc = IpcServer(manager, token)
    
    try:
        ipc.start()
        # Keep the daemon running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop()

if __name__ == "__main__":
    main()
