"""Registers the native messaging host with Chrome on Windows.

Run this once after installing the app, e.g.:

    python register_native_host.py --extension-id abcdefghijklmnopabcdefghijklmnop

What it does:
1. Writes a run_host.bat wrapper next to host.py (Chrome's native
   messaging manifest must point at something the OS can execute
   directly -- a bare .py file doesn't qualify).
2. Writes native_host_manifest.json with absolute paths and the
   extension's ID filled in.
3. Adds a registry key under
   HKEY_CURRENT_USER\\Software\\Google\\Chrome\\NativeMessagingHosts
   pointing Chrome at that manifest.

This only runs on Windows (the registry step is meaningless anywhere
else). On Mac/Linux, Chrome instead looks for the manifest json in a
fixed directory -- see the README for those paths.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HOST_NAME = "com.downloadmanager.native_host"
THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def write_wrapper_bat() -> str:
    bat_path = os.path.join(THIS_DIR, "run_host.bat")
    host_py = os.path.join(THIS_DIR, "host.py")
    # pythonw avoids flashing a console window every time a magnet link
    # is clicked; falls back to python.exe if pythonw isn't on PATH.
    content = (
        "@echo off\r\n"
        f'where pythonw >nul 2>nul && (pythonw "{host_py}") || (python "{host_py}")\r\n'
    )
    with open(bat_path, "w") as f:
        f.write(content)
    return bat_path


def write_manifest(bat_path: str, extension_id: str) -> str:
    manifest = {
        "name": HOST_NAME,
        "description": "Native messaging host for the Download Manager browser extension",
        "path": bat_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    manifest_path = os.path.join(THIS_DIR, "native_host_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


def register_in_registry(manifest_path: str) -> None:
    if sys.platform != "win32":
        print(
            f"Not on Windows -- skipping registry step.\n"
            f"Manifest written to {manifest_path}.\n"
            f"On macOS/Linux, copy it to Chrome's NativeMessagingHosts directory instead "
            f"(see README.md for the exact path)."
        )
        return

    import winreg  # noqa: PLC0415 -- only exists on Windows, imported lazily on purpose

    key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
    print(f"Registered {HOST_NAME} -> {manifest_path} under HKCU\\{key_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extension-id",
        required=True,
        help="The extension's ID from chrome://extensions (developer mode 'Load unpacked' assigns one)",
    )
    args = parser.parse_args()

    bat_path = write_wrapper_bat()
    manifest_path = write_manifest(bat_path, args.extension_id)
    register_in_registry(manifest_path)
    print(f"\nWrapper: {bat_path}\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
