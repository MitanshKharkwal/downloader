import http.server
import json
import os
import threading
import time

from playwright.sync_api import sync_playwright

EXT_PATH = "/home/claude/download_manager/browser_extension"
PAGE_DIR = "/tmp/test_page"
USER_DATA_DIR = "/tmp/pw-profile"

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
        headless=False,  # MV3 extension service workers need this (running under Xvfb)
        args=[
            f"--disable-extensions-except={EXT_PATH}",
            f"--load-extension={EXT_PATH}",
            "--no-sandbox",
        ],
    )

    # Give the service worker a moment to register, then find its ID.
    time.sleep(1.5)
    sw = None
    for _ in range(10):
        workers = context.service_workers
        if workers:
            sw = workers[0]
            break
        time.sleep(0.5)

    assert sw is not None, "extension service worker never registered -- manifest/background.js problem"
    ext_id = sw.url.split("/")[2]
    print("extension loaded, id:", ext_id)

    # --- Test content script: magnet link click should be intercepted ---
    page = context.new_page()
    page.goto("http://127.0.0.1:8899/")
    url_before = page.url
    page.click("#magnet-link")
    time.sleep(0.5)
    print("URL before click:", url_before)
    print("URL after click: ", page.url)
    assert page.url == url_before, "clicking the magnet link should NOT navigate the page"

    # Background should have received the message and attempted (and failed,
    # since no native host is registered in this throwaway profile) to reach
    # the native host -- confirms the full content -> background -> native
    # messaging call chain runs without throwing.
    last_result = sw.evaluate("() => chrome.storage.local.get('lastResult')")
    print("lastResult after magnet click:", json.dumps(last_result))
    assert last_result.get("lastResult", {}).get("source", "").startswith("magnet:")
    assert last_result["lastResult"]["ok"] is False  # expected: no native host in this test profile

    # --- Test popup: should reflect the same "not connected" state ---
    popup = context.new_page()
    popup.goto(f"chrome-extension://{ext_id}/popup.html")
    time.sleep(1.0)
    status_text = popup.inner_text("#status-text")
    print("popup status text:", status_text)
    assert "not reachable" in status_text.lower() or "never" in status_text.lower()

    print("\nextension end-to-end test passed (content script + background + popup wiring all correct;")
    print("native messaging itself correctly reports 'not connected' since no host is registered in this test profile)")

    context.close()

server.shutdown()
