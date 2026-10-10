import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log_path = os.path.join(os.path.expanduser("~"), ".download_manager", "daemon.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
if sys.stdout is None or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
    sys.stdout = open(log_path, "a", encoding="utf-8")
    sys.stderr = sys.stdout


from core.ipc_server import IpcServer, load_or_create_token
from core.manager import DownloadManager

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")


def main():
    from core.config import AppConfig

    CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")
    TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")
    app_config = AppConfig(CONFIG_PATH)

    DOWNLOAD_DIR = str(app_config.get("download_dir"))
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    manager = DownloadManager(
        download_dir=DOWNLOAD_DIR,
        max_concurrent_downloads=int(app_config.get("max_concurrent")),
    )
    manager.app_config = app_config  # type: ignore

    def _on_download_added(task):
        try:
            import ctypes

            hwnd = ctypes.windll.user32.FindWindowW("FLUTTER_RUNNER_WIN32_WINDOW", None)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            else:
                import os
                import subprocess
                import sys

                base_dir = getattr(
                    sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))
                )
                ui_paths = [
                    os.path.join(base_dir, "flutter_ui.exe"),
                    os.path.join(base_dir, "flutter_ui_bundle", "flutter_ui.exe"),
                ]
                for path in ui_paths:
                    if os.path.exists(path):
                        subprocess.Popen([path])
                        break
        except Exception as e:
            print(f"Error launching UI: {e}")

    manager.events.on("added", _on_download_added)

    token = load_or_create_token(TOKEN_PATH)
    ipc = IpcServer(manager, token)

    try:
        ipc.start()

        def clipboard_monitor():
            import threading

            import pyperclip  # type: ignore
            from win11toast import toast  # type: ignore

            last_clipboard = pyperclip.paste().strip()
            last_offered_link = None
            last_offer_time = 0
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
                            if current_clipboard == last_offered_link:
                                continue
                            if time.time() - last_offer_time < 2.0:
                                continue

                            if active_toast_thread and active_toast_thread.is_alive():
                                continue

                            last_offered_link = current_clipboard
                            last_offer_time = time.time()

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
