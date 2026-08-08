"""Android intent capture: this is the Android equivalent of the
Windows browser extension + native messaging host. There's no
"extension" concept on Android Chrome, so instead the app registers as
a handler for magnet: links and .torrent files via an intent filter
(see buildozer.spec / intent_filters.xml); Android then routes a
tapped link or downloaded file straight to this app.

On a real device (running under python-for-android), this talks to
the JVM via pyjnius. On desktop, none of that exists -- we fall back
to a harmless stub so android_app/main.py can be developed and tested
on a laptop before ever touching a device. Check ON_ANDROID if calling
code needs to branch on this itself.
"""

from __future__ import annotations

import os

try:
    from android import activity, mActivity  # noqa: F401 -- provided by python-for-android at runtime
    from jnius import autoclass

    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False


def get_startup_intent_uri() -> str | None:
    """The URI (magnet: link, or a content:// URI for a tapped .torrent
    file) that launched the app, if it was opened via intent-filter
    match rather than a normal icon tap. None otherwise, and None
    (harmlessly) on desktop."""
    if not ON_ANDROID:
        return None
    return _extract_uri(mActivity.getIntent())


def bind_new_intent_listener(callback) -> None:
    """Android delivers subsequent intents (e.g. the user taps a second
    magnet link while the app is already open) via onNewIntent rather
    than relaunching the app. callback(uri: str) fires for each one.

    Also records the callback for _simulate_intent_for_test() below, so
    this exact wiring is testable on desktop without pyjnius."""
    global _test_listener
    _test_listener = callback

    if not ON_ANDROID:
        return

    def _on_new_intent(intent):
        uri = _extract_uri(intent)
        if uri:
            callback(uri)

    activity.bind(on_new_intent=_on_new_intent)


def resolve_content_uri(uri_string: str, dest_dir: str) -> str:
    """A .torrent file handed to us by a browser or file manager
    typically arrives as a content:// URI, not a real file path --
    libtorrent needs actual bytes on disk, so copy it out of Android's
    content-resolver sandbox first. Returns the local path."""
    if not ON_ANDROID:
        raise RuntimeError("resolve_content_uri only works on-device")

    Uri = autoclass("android.net.Uri")
    uri = Uri.parse(uri_string)
    input_stream = mActivity.getContentResolver().openInputStream(uri)

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, "incoming.torrent")

    FileOutputStream = autoclass("java.io.FileOutputStream")
    out = FileOutputStream(dest_path)
    buf = bytearray(8192)
    while True:
        n = input_stream.read(buf)
        if n == -1:
            break
        out.write(buf, 0, n)
    out.close()
    input_stream.close()
    return dest_path


def _extract_uri(intent) -> str | None:
    if intent is None:
        return None
    data = intent.getData()
    if data is None:
        return None
    return data.toString()


# -- desktop-only testing hook -----------------------------------------
# Lets a headless test simulate "the OS delivered this intent" without
# needing pyjnius/android at all -- see android_app/tests/.
_test_listener = None


def _simulate_intent_for_test(uri: str) -> None:
    if _test_listener:
        _test_listener(uri)
