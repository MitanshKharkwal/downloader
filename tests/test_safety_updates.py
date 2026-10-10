"""Update, download-health, batch-capture, and safety coverage."""

import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.manager import DownloadManager
from core.safety import inspect_download
from core.updater import check_for_update, download_update


class FakeResponse:
    def __init__(self, *, status=200, data=None, text="", content=b""):
        self.status_code = status
        self._data = data
        self.text = text
        self.content = content
        self.headers = {"Content-Length": str(len(content))} if content else {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, _size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_update_discovery_requires_both_release_assets():
    release = {
        "tag_name": "v99.0.0",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": "DownloaderSetup.exe",
                "browser_download_url": "https://example.invalid/setup",
            },
            {
                "name": "SHA256SUMS.txt",
                "browser_download_url": "https://example.invalid/checksums",
            },
        ],
    }
    session = SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse(data=release))
    result = check_for_update(session)
    assert result["available"] is True
    assert result["ready"] is True


def test_update_download_checks_hash_and_trusted_signature(tmp_path, monkeypatch):
    payload = b"signed installer fixture"
    checksum = hashlib.sha256(payload).hexdigest()

    class Session:
        def get(self, url, **_kwargs):
            if url.endswith("checksums"):
                return FakeResponse(text=f"{checksum}  DownloaderSetup.exe\n")
            return FakeResponse(content=payload)

    monkeypatch.setattr("core.updater.tempfile.gettempdir", lambda: str(tmp_path))
    with patch(
        "core.updater.authenticode_status",
        return_value={"status": "Valid", "signer": "CN=Fixture"},
    ):
        package = download_update(
            {
                "available": True,
                "ready": True,
                "version": "99.0.0",
                "checksum_url": "https://example.invalid/checksums",
                "installer_url": "https://example.invalid/setup",
            },
            Session(),
        )
    assert package["sha256"] == checksum
    assert package["signature"]["signer"] == "CN=Fixture"
    assert (tmp_path / "FetchlyUpdate" / "99.0.0" / "DownloaderSetup.exe").read_bytes() == payload


def test_update_download_removes_an_untrusted_installer(tmp_path, monkeypatch):
    payload = b"unsigned"
    checksum = hashlib.sha256(payload).hexdigest()

    class Session:
        def get(self, url, **_kwargs):
            if url.endswith("checksums"):
                return FakeResponse(text=f"{checksum}  DownloaderSetup.exe\n")
            return FakeResponse(content=payload)

    monkeypatch.setattr("core.updater.tempfile.gettempdir", lambda: str(tmp_path))
    with (
        patch(
            "core.updater.authenticode_status",
            return_value={"status": "NotSigned", "signer": ""},
        ),
        pytest.raises(ValueError, match="trusted Windows publisher"),
    ):
        download_update(
            {
                "available": True,
                "ready": True,
                "version": "99.0.0",
                "checksum_url": "https://example.invalid/checksums",
                "installer_url": "https://example.invalid/setup",
            },
            Session(),
        )
    assert not (tmp_path / "FetchlyUpdate" / "99.0.0" / "DownloaderSetup.exe").exists()


def test_safety_report_hashes_and_flags_misleading_executable(tmp_path):
    target = tmp_path / "invoice.pdf.exe"
    target.write_bytes(b"fixture")
    with patch(
        "core.safety.authenticode_status",
        return_value={"status": "NotSigned", "signer": ""},
    ):
        report = inspect_download(str(target), defender_enabled=False)
    assert report["sha256"] == hashlib.sha256(b"fixture").hexdigest()
    assert report["status"] == "attention"
    assert any("double extension" in warning for warning in report["warnings"])


def test_batch_add_reports_duplicates_and_does_not_expose_header_values(tmp_path):
    with (
        patch("core.manager.TorrentSession"),
        patch.object(DownloadManager, "_run_scheduler"),
        patch.object(DownloadManager, "_maybe_start_next"),
    ):
        manager = DownloadManager(str(tmp_path), state_file=str(tmp_path / "state.json"))
        result = manager.add_batch(
            [
                {
                    "source": "https://example.invalid/file.zip",
                    "headers": {"Cookie": "secret", "Referer": "https://example.invalid"},
                },
                {"source": "https://example.invalid/file.zip"},
                {"source": "not a URL"},
            ]
        )
        task = manager.list_tasks()[0]
        assert result == {"added": 1, "skipped": 1, "failed": 1}
        assert task.health["cookies_forwarded"] is True
        assert task.health["referrer_forwarded"] is True
        assert "secret" not in str(task.health)
        manager.shutdown()
