import os
import subprocess
import sys
import threading
import time


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def start_daemon(stop_event):
    # Import daemon to run it
    import daemon

    # We want daemon to just run in this background thread.
    # daemon.main() has an infinite loop at the end, so it will block here.
    try:
        daemon.main(stop_event)
    except Exception as e:
        print(f"Daemon exception: {e}")


def main():
    # Start the daemon in a background thread
    stop_event = threading.Event()
    daemon_thread = threading.Thread(
        target=start_daemon, args=(stop_event,), daemon=True
    )
    daemon_thread.start()

    # Give the daemon a moment to initialize the IPC server
    time.sleep(1)

    # Launch Flutter UI
    ui_exe = resource_path(os.path.join("flutter_ui_bundle", "flutter_ui.exe"))
    if os.path.exists(ui_exe):
        print(f"Launching {ui_exe}...")
        try:
            subprocess.run([ui_exe], check=False)
        finally:
            stop_event.set()
            daemon_thread.join()
    else:
        print(f"Error: Could not find UI executable at {ui_exe}")
        # Keep running so user can see the error, or at least sleep
        stop_event.set()
        daemon_thread.join()


if __name__ == "__main__":
    main()
