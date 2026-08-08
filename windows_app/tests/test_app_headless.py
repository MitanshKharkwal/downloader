import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kivy.clock import Clock

from ipc_server import load_or_create_token
from main import DOWNLOAD_DIR, TOKEN_PATH, DownloadManagerApp

app = DownloadManagerApp()


def inject_download(_dt):
    token = load_or_create_token(TOKEN_PATH)
    payload = json.dumps({"source": "magnet:?xt=urn:btih:deadbeefcafebabedeadbeefcafebabedeadbeef&dn=Test+Torrent"}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{app.ipc.port}/add",
        data=payload,
        headers={"X-Auth-Token": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print("injected via IPC:", json.loads(resp.read()))

    # also exercise the plain UI add path
    app.url_input.text = "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl"
    app._on_add()


def check_and_screenshot(_dt):
    tasks = app.manager.list_tasks()
    print(f"\ntasks in manager: {len(tasks)}")
    for t in tasks:
        print(f"  {t.id}  type={t.type.value}  status={t.status.value}  name={t.name!r}  source={t.source[:60]}")
    print(f"rows rendered in UI: {len(app.rows)}")
    assert len(tasks) == 2, "expected both the magnet and the http task"
    assert len(app.rows) == 2, "expected a UI row created for each task"

    from kivy.core.window import Window
    shot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot.png")
    Window.screenshot(name=shot_path)
    print("screenshot saved (or similarly-named variant) to", shot_path)

    app.stop()


Clock.schedule_once(inject_download, 1.0)
Clock.schedule_once(check_and_screenshot, 2.5)
app.run()
