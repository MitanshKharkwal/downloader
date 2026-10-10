import json
import os
import threading
from typing import Any


class AppConfig:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self._lock = threading.Lock()
        self.settings: dict[str, Any] = {
            "download_dir": os.path.join(os.path.expanduser("~"), "Downloads"),
            "category_dirs": {},
            "max_concurrent": 3,
            "max_bandwidth_kbps": 0,
            "run_on_startup": False,
            "defender_scan_enabled": True,
        }
        self.load()

    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for k, v in data.items():
                            if k in self.settings:
                                self.settings[k] = v
                except Exception:
                    pass

    def save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4)
                os.replace(self.config_path + ".tmp", self.config_path)
            except Exception:
                pass

    def get(self, key: str) -> Any:
        with self._lock:
            return self.settings.get(key, "")

    def update(self, new_settings: dict) -> None:
        with self._lock:
            for k, v in new_settings.items():
                if k in self.settings or k == "category_dirs":
                    self.settings[k] = v
        self.save()

    def apply_run_on_startup(self) -> None:
        import sys

        if sys.platform != "win32":
            return

        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)

            run_on_startup = self.get("run_on_startup")
            app_name = "DownloadManager"

            if run_on_startup:
                # Path to executable
                import os

                if getattr(sys, "frozen", False):
                    exe_path = f'"{sys.executable}"'
                else:
                    daemon_path = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "daemon.py")
                    )
                    exe_path = f'"{sys.executable}" "{daemon_path}"'

                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Failed to apply run_on_startup: {e}")
