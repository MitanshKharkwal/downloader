"""Post-download integrity and optional Windows Defender checks."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .updater import authenticode_status

EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".msi",
    ".msix",
    ".bat",
    ".cmd",
    ".com",
    ".ps1",
    ".scr",
    ".vbs",
    ".js",
    ".jar",
    ".apk",
}
DECOY_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt", ".zip"}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _warnings(path: str) -> list[str]:
    name = Path(path).name.lower()
    suffixes = Path(name).suffixes
    warnings: list[str] = []
    if suffixes and suffixes[-1] in EXECUTABLE_EXTENSIONS:
        warnings.append("This file can run code on your device.")
    if (
        len(suffixes) > 1
        and suffixes[-2] in DECOY_EXTENSIONS
        and suffixes[-1] in EXECUTABLE_EXTENSIONS
    ):
        warnings.append("The filename uses a misleading double extension.")
    return warnings


def _defender_path() -> str | None:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Windows Defender", "MpCmdRun.exe"),
        os.path.join(
            os.environ.get("ProgramData", ""),
            "Microsoft",
            "Windows Defender",
            "Platform",
        ),
    ]
    if os.path.isfile(candidates[0]):
        return candidates[0]
    platform_dir = candidates[1]
    if os.path.isdir(platform_dir):
        versions = sorted(Path(platform_dir).glob("*/MpCmdRun.exe"), reverse=True)
        if versions:
            return str(versions[0])
    return None


def inspect_download(path: str, defender_enabled: bool = True) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {
            "status": "unavailable",
            "sha256": "",
            "warnings": ["Safety scanning currently supports single-file downloads."],
            "defender": "not_scanned",
        }
    warnings = _warnings(path)
    result: dict[str, Any] = {
        "status": "checking",
        "sha256": _sha256(path),
        "warnings": warnings,
        "defender": "disabled" if not defender_enabled else "unavailable",
        "signature": {"status": "not_applicable", "signer": ""},
    }
    if Path(path).suffix.lower() in {".exe", ".msi", ".msix"}:
        result["signature"] = authenticode_status(path)
        if result["signature"]["status"].lower() != "valid":
            warnings.append("The executable does not have a trusted Windows signature.")
    scanner = _defender_path() if defender_enabled and sys.platform == "win32" else None
    if scanner:
        try:
            scan = subprocess.run(
                [scanner, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            result["defender"] = "clear" if scan.returncode == 0 else "attention"
            if scan.returncode != 0:
                warnings.append("Windows Defender reported that this file needs attention.")
        except (OSError, subprocess.TimeoutExpired):
            result["defender"] = "error"
            warnings.append("Windows Defender could not finish the scan.")
    result["status"] = "attention" if warnings else "safe"
    return result
