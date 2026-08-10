import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "android_app"
    ),
)

import intent_bridge

# Simulate "the OS launched us via a tapped magnet link" -- this must be
# patched before main.build() runs, since it's read at startup.
intent_bridge.get_startup_intent_uri = lambda: (
    "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=Cold+Start+Torrent"
)

from kivy.clock import Clock
from main import DownloadManagerApp

app = DownloadManagerApp()


def simulate_live_intent(_dt):
    # Simulates "app already running, user taps a second magnet link
    # elsewhere" -- goes through the exact same bind_new_intent_listener
    # wiring main.py installed, just triggered by the test hook instead
    # of a real onNewIntent callback from the JVM.
    intent_bridge._simulate_intent_for_test(
        "magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&dn=Live+Tapped+Torrent"
    )
    print("simulated a live intent (app already running)")

    # Also exercise the manual add bar, same as a user typing a URL.
    app.url_input.text = "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl"
    app._on_add()


def check_and_screenshot(_dt):
    tasks = app.manager.list_tasks()
    print(f"\ntasks in manager: {len(tasks)}")
    for t in tasks:
        print(
            f"  {t.id}  type={t.type.value}  status={t.status.value}  name={t.name!r}  source={t.source[:55]}"
        )

    sources = {t.source for t in tasks}
    assert any("aaaaaaaa" in s for s in sources), (
        "cold-start intent should have been captured"
    )
    assert any("bbbbbbbb" in s for s in sources), (
        "live (already-running) intent should have been captured"
    )
    assert any(s.startswith("https://") for s in sources), (
        "manual add-bar entry should have been captured"
    )
    assert len(app.rows) == len(tasks), "every task should have a UI row"
    print(
        "\nall three capture paths (cold-start intent, live intent, manual add) verified"
    )

    from kivy.core.window import Window

    shot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "screenshot.png"
    )
    Window.screenshot(name=shot_path)
    print("screenshot saved to", shot_path)

    app.stop()


Clock.schedule_once(simulate_live_intent, 1.0)
Clock.schedule_once(check_and_screenshot, 2.5)
app.run()
