"""Native-host tests never read or remove the user's real token."""

import io
import json
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.ipc_server import IpcServer
from core.models import DownloadTask, DownloadType
from native_host import host


@pytest.fixture
def app(tmp_path, monkeypatch):
    token = tmp_path / "token.txt"
    token.write_text("test-token")
    monkeypatch.setattr(host, "TOKEN_PATH", str(token))
    received = []

    def add(source, **kwargs):
        received.append(source)
        return DownloadTask(source, str(tmp_path / "output"), DownloadType.HTTP)

    server = IpcServer(SimpleNamespace(add=add), "test-token", port=0)
    monkeypatch.setattr(host, "IPC_PORT", server._server.server_port)
    server.start()
    yield received
    server.stop()


def test_ping_checks_daemon(app):
    assert host.handle({"action": "ping"}) == {
        "ok": True,
        "pong": True,
        "app_token_found": True,
    }


def test_native_add_round_trip(app):
    result = host.handle({"action": "add", "source": "https://example.invalid/file"})
    assert result["ok"]
    assert app == ["https://example.invalid/file"]


def test_ping_without_daemon_does_not_report_connected(tmp_path, monkeypatch):
    token = tmp_path / "token.txt"
    token.write_text("test-token")
    monkeypatch.setattr(host, "TOKEN_PATH", str(token))
    with patch.object(host, "_app_running", return_value=False):
        assert not host.handle({"action": "ping"})["ok"]


@pytest.mark.parametrize(
    "payload", [b"a", struct.pack("=I", 2**22), struct.pack("=I", 10) + b"{}"]
)
def test_malformed_native_frame(payload):
    with patch.object(host.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(payload))):
        with pytest.raises(ValueError):
            host.read_message()


def test_native_frame_round_trip():
    data = json.dumps({"action": "ping"}).encode()
    with patch.object(
        host.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(struct.pack("=I", len(data)) + data)),
    ):
        assert host.read_message() == {"action": "ping"}
