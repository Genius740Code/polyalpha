"""
TimeSync NTP robustness tests — hgroup4 finding #30.
"""

import socket
import time

import pytest

from polyalpha.core.time_sync import _query_server, TimeSync


class _FakeSock:
    def __init__(self, response: bytes):
        self._response = response

    def settimeout(self, timeout):
        pass

    def sendto(self, packet, addr):
        pass

    def recvfrom(self, size):
        return self._response, ("1.2.3.4", 123)

    def close(self):
        pass


@pytest.mark.unit
def test_query_server_accepts_oversized_packet(monkeypatch):
    """A >48-byte NTP response must not crash (servers pad with extensions)."""
    oversized = bytes(48) + b"\x00" * 16

    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSock(oversized))
    monkeypatch.setattr(time, "time", lambda: 1000.0)

    result = _query_server("ntp.example")

    assert "offset" in result
    assert "delay" in result


@pytest.mark.unit
def test_query_server_rejects_short_packet(monkeypatch):
    """An undersized NTP response must raise a controlled error."""
    short = b"\x00" * 40

    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSock(short))

    with pytest.raises(ValueError, match="Short NTP response"):
        _query_server("ntp.example")


@pytest.mark.unit
def test_sync_falls_through_malformed_server(monkeypatch):
    """A malformed packet on one server must not defeat the whole failover."""
    calls = []

    def fake_query(host, port=123, timeout=5.0):
        calls.append(host)
        if host == "bad.example":
            raise ValueError("Short NTP response from bad.example (40 bytes)")
        return {
            "server": host, "offset": 0.05, "offset_ms": 50.0,
            "delay": 0.01, "delay_ms": 10.0,
            "t1": 1.0, "t3": 1.05, "t4": 1.01,
        }

    monkeypatch.setattr("polyalpha.core.time_sync._query_server", fake_query)

    ts = TimeSync(servers=["bad.example", "good.example"], retries=1)
    report = ts.sync(force=True)

    assert calls == ["bad.example", "good.example"]
    assert report["server"] == "good.example"
    assert report["can_proceed"] is True


@pytest.mark.unit
def test_sync_all_servers_fail_returns_report(monkeypatch):
    """When every server is malformed, sync returns a report instead of raising."""
    def fake_query(host, port=123, timeout=5.0):
        raise ValueError("Short NTP response")

    monkeypatch.setattr("polyalpha.core.time_sync._query_server", fake_query)

    ts = TimeSync(servers=["a.example", "b.example"], retries=1)
    report = ts.sync(force=True)

    assert report["synced"] is False
    assert report["error"] is not None
    assert report["can_proceed"] is True  # offset stayed 0
