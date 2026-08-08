import http.server
import json
import os
import threading
import time

from playwright.sync_api import sync_playwright

EXT_PATH = "/home/claude/download_manager/browser_extension"
PAGE_DIR = "/tmp/test_page"
USER_DATA_DIR = "/tmp/pw-profile-live"

os.makedirs(PAGE_DIR, exist_ok=True)
with open(os.path.join(PAGE_DIR, "index.html"), "w") as f:
    f.write(
        '<!DOCTYPE html><html><body><h1>Test page</h1>'
        '<a id="magnet-link" href="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Test+File">'
        "Download via magnet</a></body></html>"
    )


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PAGE_DIR, **kwargs)

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 8899), QuietHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=False,
        args=[
            f"--disable-extensions-except={EXT_PATH}",
            f"--load-extension={EXT_PATH}",
            "--no-sandbox",
        ],
    )

    time.sleep(1.5)
    sw = None
    for _ in range(10):
        if context.service_workers:
            sw = context.service_workers[0]
            break
        time.sleep(0.5)
    assert sw is not None
    ext_id = sw.url.split("/")[2]
    print("extension id this run:", ext_id)

    page = context.new_page()
    page.goto("http://127.0.0.1:8899/")
    page.click("#magnet-link")
    time.sleep(1.5)  # native host is a real subprocess + real HTTP round trip now

    last_result = sw.evaluate("() => chrome.storage.local.get('lastResult')")
    print("lastResult after real magnet click:", json.dumps(last_result, indent=2))

    popup = context.new_page()
    popup.goto(f"chrome-extension://{ext_id}/popup.html")
    time.sleep(1.0)
    status_text = popup.inner_text("#status-text")
    print("popup status text:", status_text)

    context.close()

server.shutdown()
