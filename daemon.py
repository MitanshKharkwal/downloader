import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log_path = os.path.join(os.path.expanduser("~"), ".download_manager", "daemon.log")
sys.stdout = open(log_path, "a", encoding="utf-8")
sys.stderr = sys.stdout


from core.ipc_server import IpcServer, load_or_create_token
from core.manager import DownloadManager

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
DOWNLOAD_DIR = os.path.join(APP_DATA_DIR, "downloads")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")


def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    manager = DownloadManager(download_dir=DOWNLOAD_DIR, max_concurrent_downloads=3)

    token = load_or_create_token(TOKEN_PATH)
    ipc = IpcServer(manager, token)

    try:
        ipc.start()

        def clipboard_monitor():
            import threading

            import pyperclip
            from win11toast import toast

            last_clipboard = pyperclip.paste().strip()
            active_toast_thread = None
            while True:
                try:
                    time.sleep(1)
                    current_clipboard = pyperclip.paste().strip()
                    if current_clipboard != last_clipboard:
                        last_clipboard = current_clipboard
                        if current_clipboard.startswith(
                            ("http://", "https://", "magnet:?")
                        ):
                            if active_toast_thread and active_toast_thread.is_alive():
                                continue

                            def handle_toast(link):
                                try:
                                    res = toast(
                                        "Download Manager",
                                        f"Link copied:\n{link[:60]}...",
                                        button="Download",
                                    )
                                    if res == "Download":
                                        manager.add(link)
                                except Exception:
                                    pass

                            active_toast_thread = threading.Thread(
                                target=handle_toast,
                                args=(current_clipboard,),
                                daemon=True,
                            )
                            active_toast_thread.start()
                except Exception:
                    pass

        import threading

        threading.Thread(target=clipboard_monitor, daemon=True).start()

        # Keep the daemon running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop()


if __name__ == "__main__":
    main()
