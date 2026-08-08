"""Android app shell.

Same core engine as the Windows app -- the only real difference is how
downloads get *into* the queue. Windows has a browser extension +
native messaging; Android has no extension mechanism at all, so
instead the app registers as an intent-filter handler for magnet:
links and .torrent files (see buildozer.spec). Tapping either, in any
app, routes straight here via the OS.
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
from intent_bridge import ON_ANDROID, bind_new_intent_listener, get_startup_intent_uri, resolve_content_uri


def _default_download_dir() -> str:
    if ON_ANDROID:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        ctx = PythonActivity.mActivity
        # App-specific external storage -- no runtime permission needed
        # on modern Android, and it's cleaned up automatically if the
        # app is uninstalled.
        return ctx.getExternalFilesDir(None).getAbsolutePath() + "/downloads"
    return os.path.join(os.path.expanduser("~"), ".download_manager_mobile", "downloads")


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.1f}{unit}"
        n /= 1024
    return f"{n:,.1f}TB"


class DownloadRow(BoxLayout):
    """Touch-sized version of the Windows app's row: bigger tap targets,
    bigger text, same underlying refresh() logic."""

    def __init__(self, manager: DownloadManager, task_id: str, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=96, padding=8, spacing=4, **kwargs)
        self.manager = manager
        self.task_id = task_id

        top = BoxLayout(size_hint_y=None, height=32, spacing=8)
        self.name_label = Label(text="", halign="left", valign="middle", size_hint_x=0.5, font_size=15)
        self.name_label.bind(size=self.name_label.setter("text_size"))
        self.status_label = Label(text="", size_hint_x=0.25, font_size=13)
        top.add_widget(self.name_label)
        top.add_widget(self.status_label)

        controls = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.pause_btn = Button(text="Pause", on_release=self._on_pause_resume)
        self.cancel_btn = Button(text="Cancel", on_release=self._on_cancel)
        controls.add_widget(self.pause_btn)
        controls.add_widget(self.cancel_btn)

        self.progress = ProgressBar(max=1.0, value=0.0, size_hint_y=None, height=18)
        self.detail_label = Label(text="", size_hint_y=None, height=22, font_size=12)

        self.add_widget(top)
        self.add_widget(self.progress)
        self.add_widget(self.detail_label)
        self.add_widget(controls)

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
        self.name_label.text = task.name or os.path.basename(task.dest_path) or task.source[:30]
        self.status_label.text = task.status.value
        self.progress.value = task.progress()
        extra = f"  peers:{task.num_peers}" if task.type.value == "torrent" else f"  conns:{task.num_connections}"
        detail = f"{human_bytes(task.downloaded_bytes)} / {human_bytes(task.total_bytes)}  {human_bytes(task.speed_bps)}/s{extra}"
        if task.status == DownloadStatus.ERROR and task.error_message:
            detail = task.error_message
        self.detail_label.text = detail
        self.pause_btn.text = "Resume" if task.status == DownloadStatus.PAUSED else "Pause"
        done = task.status in (DownloadStatus.COMPLETED, DownloadStatus.ERROR, DownloadStatus.CANCELED)
        self.pause_btn.disabled = done
        self.cancel_btn.disabled = done


class DownloadManagerApp(App):
    title = "Download Manager"

    def build(self):
        download_dir = _default_download_dir()
        os.makedirs(download_dir, exist_ok=True)
        self.manager = DownloadManager(download_dir=download_dir, max_concurrent_downloads=3)
        self.rows: dict[str, DownloadRow] = {}

        root = BoxLayout(orientation="vertical", padding=8, spacing=8)

        add_bar = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.url_input = TextInput(hint_text="Paste a URL or magnet link...", multiline=False, font_size=15)
        self.url_input.bind(on_text_validate=self._on_add)
        add_btn = Button(text="Add", size_hint_x=0.22, on_release=self._on_add)
        add_bar.add_widget(self.url_input)
        add_bar.add_widget(add_btn)
        root.add_widget(add_bar)

        self.list_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        self.status_bar = Label(
            text="Handling magnet: links and .torrent files tapped elsewhere on this device",
            size_hint_y=None,
            height=28,
            font_size=12,
        )
        root.add_widget(self.status_bar)

        # Capture: launched via a tapped magnet/.torrent link (cold start).
        startup_uri = get_startup_intent_uri()
        if startup_uri:
            Clock.schedule_once(lambda _dt: self._handle_incoming_uri(startup_uri), 0)

        # Capture: app already running, user taps another link.
        bind_new_intent_listener(lambda uri: Clock.schedule_once(lambda _dt: self._handle_incoming_uri(uri)))

        Clock.schedule_interval(self._tick, 0.5)
        return root

    def _handle_incoming_uri(self, uri: str) -> None:
        """Runs on the main/UI thread (always scheduled via Clock, even
        though the intent callback itself may fire from another thread)."""
        if uri.startswith("content://"):
            try:
                uri = resolve_content_uri(uri, self.manager.download_dir)
            except Exception as exc:  # noqa: BLE001
                self.status_bar.text = f"Couldn't read the tapped file: {exc}"
                return
        self.manager.add(uri)

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
        self.manager.shutdown()


if __name__ == "__main__":
    DownloadManagerApp().run()
