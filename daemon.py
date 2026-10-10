import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_DATA_DIR = os.environ.get("DOWNLOAD_MANAGER_DATA_DIR") or os.path.join(
    os.path.expanduser("~"), ".download_manager"
)
log_path = os.path.join(APP_DATA_DIR, "daemon.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
if sys.stdout is None or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
    sys.stdout = open(log_path, "a", encoding="utf-8")
    sys.stderr = sys.stdout


from core.ipc_server import IpcServer, load_or_create_token
from core.manager import DownloadManager

TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")


def main(stop_event=None):
    from core.config import AppConfig

    CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")
    TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")
    app_config = AppConfig(CONFIG_PATH)

    DOWNLOAD_DIR = str(app_config.get("download_dir"))
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    import shutil

    state_path = os.path.join(APP_DATA_DIR, "state.json")
    if not os.path.exists(state_path):
        legacy = os.path.join(DOWNLOAD_DIR, ".dm_state.json")
        if os.path.isfile(legacy):
            shutil.copy2(legacy, state_path)
    manager = DownloadManager(
        download_dir=DOWNLOAD_DIR,
        state_file=state_path,
        max_concurrent_downloads=int(app_config.get("max_concurrent")),
    )
    manager.app_config = app_config  # type: ignore
    if not os.path.exists(state_path):
        manager.apply_config()
        manager.set_config({"category_dirs": app_config.get("category_dirs")})

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
                    os.path.join(os.path.dirname(sys.executable), "flutter_ui.exe"),
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
    ipc = IpcServer(
        manager, token, port=int(os.environ.get("DOWNLOAD_MANAGER_IPC_PORT", "47821"))
    )

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
            while stop_event is None or not stop_event.is_set():
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

        if (
            sys.platform == "win32"
            and os.environ.get("DOWNLOAD_MANAGER_CLIPBOARD", "1") != "0"
        ):
            threading.Thread(target=clipboard_monitor, daemon=True).start()

        # Keep the daemon running
        while stop_event is None or not stop_event.wait(1):
            if stop_event is None:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop()
        manager.shutdown()


if __name__ == "__main__":
    main()
