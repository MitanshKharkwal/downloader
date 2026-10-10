"""Secure GitHub-release update discovery and installation for Windows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

from .version import APP_VERSION, REPOSITORY

API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
INSTALLER_NAME = "DownloaderSetup.exe"
CHECKSUM_NAME = "SHA256SUMS.txt"
MAX_INSTALLER_BYTES = 300 * 1024 * 1024


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value.lstrip("vV").split("-", 1)[0])
    return tuple(int(part) for part in numbers[:4]) or (0,)


def authenticode_status(path: str) -> dict[str, str]:
    """Return trusted Windows signature status without interpolating the path."""
    if sys.platform != "win32":
        return {"status": "unsupported", "signer": ""}
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
        "@{status=$s.Status.ToString();signer=if($s.SignerCertificate){"
        "$s.SignerCertificate.Subject}else{''}}|ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        data = json.loads(result.stdout.strip() or "{}")
        return {
            "status": str(data.get("status", "Unknown")),
            "signer": str(data.get("signer", "")),
        }
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"status": "Unknown", "signer": ""}


def check_for_update(session: Any = requests) -> dict[str, Any]:
    response = session.get(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Fetchly-Updater"},
        timeout=15,
    )
    if response.status_code == 404:
        return {"current_version": APP_VERSION, "available": False, "reason": "no_release"}
    response.raise_for_status()
    release = response.json()
    if release.get("draft") or release.get("prerelease"):
        return {"current_version": APP_VERSION, "available": False, "reason": "no_stable_release"}
    version = str(release.get("tag_name", "")).lstrip("vV")
    assets = {item.get("name"): item for item in release.get("assets", [])}
    installer = assets.get(INSTALLER_NAME)
    checksums = assets.get(CHECKSUM_NAME)
    available = _version_tuple(version) > _version_tuple(APP_VERSION)
    ready = bool(installer and checksums)
    return {
        "current_version": APP_VERSION,
        "version": version,
        "available": available,
        "ready": ready,
        "published_at": release.get("published_at", ""),
        "notes_url": release.get("html_url", ""),
        "notes": str(release.get("body", ""))[:4000],
        "installer_url": installer.get("browser_download_url", "") if installer else "",
        "checksum_url": checksums.get("browser_download_url", "") if checksums else "",
    }


def _expected_checksum(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^([a-fA-F0-9]{64})\s+\*?(.+)$", line.strip())
        if match and os.path.basename(match.group(2).strip()) == INSTALLER_NAME:
            return match.group(1).lower()
    raise ValueError(f"{CHECKSUM_NAME} does not contain {INSTALLER_NAME}")


def download_update(info: dict[str, Any], session: Any = requests) -> dict[str, Any]:
    if not info.get("available") or not info.get("ready"):
        raise ValueError("No installable update is available")
    checksum_response = session.get(info["checksum_url"], timeout=15)
    checksum_response.raise_for_status()
    expected = _expected_checksum(checksum_response.text)
    update_dir = Path(tempfile.gettempdir()) / "FetchlyUpdate" / str(info["version"])
    update_dir.mkdir(parents=True, exist_ok=True)
    destination = update_dir / INSTALLER_NAME
    temporary = destination.with_suffix(".download")
    digest = hashlib.sha256()
    size = 0
    try:
        with session.get(info["installer_url"], stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            advertised = int(response.headers.get("Content-Length", "0") or 0)
            if advertised > MAX_INSTALLER_BYTES:
                raise ValueError("Update package is unexpectedly large")
            with open(temporary, "wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_INSTALLER_BYTES:
                        raise ValueError("Update package exceeded the size limit")
                    digest.update(chunk)
                    output.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError("Update checksum verification failed")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    signature = authenticode_status(str(destination))
    if signature["status"].lower() != "valid":
        destination.unlink(missing_ok=True)
        raise ValueError("Update is not signed by a trusted Windows publisher")
    return {
        "path": str(destination),
        "version": info["version"],
        "sha256": expected,
        "signature": signature,
    }


def install_update(path: str) -> None:
    resolved = Path(path).resolve()
    root = (Path(tempfile.gettempdir()) / "FetchlyUpdate").resolve()
    if root not in resolved.parents or resolved.name != INSTALLER_NAME or not resolved.is_file():
        raise ValueError("Invalid update package path")
    if authenticode_status(str(resolved))["status"].lower() != "valid":
        raise ValueError("Update signature is no longer valid")
    subprocess.Popen([str(resolved), "/SILENT", "/CLOSEAPPLICATIONS"])
