"""Windows desktop app shell.

Kivy so the same UI code can eventually target Android too. Talks to
the core engine directly in-process, and also runs a small local IPC
server so the browser extension's native messaging host can hand off
magnet links / captured downloads to this already-running instance.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import DownloadManager, DownloadStatus
from ipc_server import IpcServer, load_or_create_token

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".download_manager")
DOWNLOAD_DIR = os.path.join(APP_DATA_DIR, "downloads")
TOKEN_PATH = os.path.join(APP_DATA_DIR, "ipc_token.txt")


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.1f}{unit}"
        n /= 1024
    return f"{n:,.1f}TB"


class DownloadRow(BoxLayout):
    """One row per task. Rebuilt fields are cheap enough to just update
    in place every tick rather than diffing -- these are plain labels,
    not anything expensive to redraw."""

    def __init__(self, manager: DownloadManager, task_id: str, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=72, padding=6, spacing=2, **kwargs)
        self.manager = manager
        self.task_id = task_id

        top = BoxLayout(size_hint_y=None, height=24, spacing=8)
        self.name_label = Label(text="", halign="left", valign="middle", size_hint_x=0.55)
        self.name_label.bind(size=self.name_label.setter("text_size"))
        self.status_label = Label(text="", size_hint_x=0.2)
        self.pause_btn = Button(text="Pause", size_hint_x=0.12, on_release=self._on_pause_resume)
        self.cancel_btn = Button(text="Cancel", size_hint_x=0.13, on_release=self._on_cancel)
        top.add_widget(self.name_label)
        top.add_widget(self.status_label)
        top.add_widget(self.pause_btn)
        top.add_widget(self.cancel_btn)

        self.progress = ProgressBar(max=1.0, value=0.0, size_hint_y=None, height=14)
        self.detail_label = Label(text="", size_hint_y=None, height=20, font_size=12)

        self.add_widget(top)
        self.add_widget(self.progress)
        self.add_widget(self.detail_label)

    def _on_pause_resume(self, *_args) -> None:
        task = self.manager.get(self.task_id)
        if task is None:
            return
        if task.status == DownloadStatus.PAUSED:
            self.manager.resume(self.task_id)
        else:
            self.manager.pause(self.task_id)

    def _on_cancel(self, *_args) -> None:
        self.manager.cancel(self.task_id)

    def refresh(self) -> None:
        task = self.manager.get(self.task_id)
        if task is None:
            return
        self.name_label.text = task.name or os.path.basename(task.dest_path) or task.source[:40]
        self.status_label.text = task.status.value
        self.progress.value = task.progress()
        extra = f"  peers:{task.num_peers}" if task.type.value == "torrent" else f"  conns:{task.num_connections}"
        if task.status == DownloadStatus.ERROR and task.error_message:
            self.detail_label.text = task.error_message
        else:
            self.detail_label.text = (
                f"{human_bytes(task.downloaded_bytes)} / {human_bytes(task.total_bytes)}"
                f"   {human_bytes(task.speed_bps)}/s{extra}"
            )
        self.pause_btn.text = "Resume" if task.status == DownloadStatus.PAUSED else "Pause"
        self.pause_btn.disabled = task.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.ERROR,
            DownloadStatus.CANCELED,
        )
        self.cancel_btn.disabled = self.pause_btn.disabled


class DownloadManagerApp(App):
    title = "Download Manager"

    def build(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        self.manager = DownloadManager(download_dir=DOWNLOAD_DIR, max_concurrent_downloads=3)

        token = load_or_create_token(TOKEN_PATH)
        self.ipc = IpcServer(self._ipc_add, token)
        self.ipc.start()

        self.rows: dict[str, DownloadRow] = {}

        root = BoxLayout(orientation="vertical", padding=8, spacing=8)

        add_bar = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.url_input = TextInput(hint_text="Paste a URL or magnet link...", multiline=False)
        self.url_input.bind(on_text_validate=self._on_add)
        add_btn = Button(text="Add", size_hint_x=0.15, on_release=self._on_add)
        add_bar.add_widget(self.url_input)
        add_bar.add_widget(add_btn)
        root.add_widget(add_bar)

        self.list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        self.status_bar = Label(text=self._status_text(), size_hint_y=None, height=24, font_size=12)
        root.add_widget(self.status_bar)

        Clock.schedule_interval(self._tick, 0.5)
        return root

    def _status_text(self) -> str:
        return f"Listening for browser-extension handoffs on 127.0.0.1:{self.ipc.port}"

    def _ipc_add(self, source: str) -> dict:
        """Called from the IPC server's background thread -- keep this
        cheap and thread-safe. DownloadManager.add() is safe to call
        from any thread; the actual widget creation happens on the next
        Kivy clock tick in _tick(), which always runs on the main thread."""
        task = self.manager.add(source)
        return {"id": task.id, "status": task.status.value}

    def _on_add(self, *_args) -> None:
        source = self.url_input.text.strip()
        if not source:
            return
        self.manager.add(source)
        self.url_input.text = ""

    def _tick(self, _dt) -> None:
        for task in self.manager.list_tasks():
            if task.id not in self.rows:
                row = DownloadRow(self.manager, task.id)
                self.rows[task.id] = row
                self.list_layout.add_widget(row)
            self.rows[task.id].refresh()

    def on_stop(self):
        self.ipc.stop()
        self.manager.shutdown()


if __name__ == "__main__":
    DownloadManagerApp().run()
