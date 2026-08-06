"""
MarketClient time-sync wiring tests — hgroup4 findings #27, #28.
"""

import datetime
import time
import zoneinfo

import pytest

from polyalpha.markets import MarketClient
from polyalpha.core.errors import MarketNotFound


class _FixedTimeSync:
    """TimeSync stand-in with a configurable clock offset (seconds)."""

    def __init__(self, offset: float = 0.0):
        self._offset = offset

    def now_int(self) -> int:
        return int(time.time() + self._offset)


# ── #27 slug generation uses TimeSync correction ──────────────────────────────

@pytest.mark.unit
def test_latest_uses_time_sync_offset(monkeypatch):
    """Slug candidates must be computed from the NTP-corrected clock."""
    monkeypatch.setattr(time, "time", lambda: 1_750_000_000.0)

    client = MarketClient(time_sync=_FixedTimeSync(offset=300.0))
    tried = []

    def fake_fetch(slug):
        tried.append(slug)
        raise MarketNotFound(slug)

    monkeypatch.setattr(client, "_fetch_by_slug", fake_fetch)

    with pytest.raises(MarketNotFound):
        client.latest("BTC", "5m")

    # Corrected now = 1_750_000_300 → first 5m window start = 1_750_000_200
    assert tried[0] == "btc-updown-5m-1750000200"


@pytest.mark.unit
def test_latest_uses_wall_clock_without_offset(monkeypatch):
    """Without an injected sync, behaviour is identical to before (offset 0)."""
    monkeypatch.setattr(time, "time", lambda: 1_750_000_000.0)

    client = MarketClient(time_sync=_FixedTimeSync(offset=0.0))
    tried = []

    def fake_fetch(slug):
        tried.append(slug)
        raise MarketNotFound(slug)

    monkeypatch.setattr(client, "_fetch_by_slug", fake_fetch)

    with pytest.raises(MarketNotFound):
        client.latest("BTC", "5m")

    assert tried[0] == "btc-updown-5m-1749999900"


@pytest.mark.unit
def test_client_wires_time_sync_into_markets():
    """polyalpha.Client must share its TimeSync with MarketClient."""
    from polyalpha.client import Client

    client = Client()

    assert client.markets._time_sync is client.time_sync

    client.close()


# ── #28 1mo tweet market probes multiple months ───────────────────────────────

@pytest.mark.unit
def test_latest_tweet_1mo_probes_current_and_prior_months(monkeypatch):
    """The 1mo probe must try more than a single offset month."""
    tz = zoneinfo.ZoneInfo("America/New_York")
    now = datetime.datetime(2026, 3, 15, tzinfo=tz).timestamp()
    monkeypatch.setattr(time, "time", lambda: now)

    client = MarketClient()
    tried = []

    def fake_fetch(slug):
        tried.append(slug)
        raise MarketNotFound(slug)

    monkeypatch.setattr(client, "_fetch_by_slug", fake_fetch)

    with pytest.raises(MarketNotFound):
        client.latest_tweet("elon-musk", "1mo")

    assert tried[0] == "elon-musk-of-tweets-march-2026"
    assert "elon-musk-of-tweets-february-2026" in tried
    assert "elon-musk-of-tweets-january-2026" in tried
    assert len(tried) == 3


@pytest.mark.unit
def test_latest_tweet_1mo_returns_first_match(monkeypatch):
    """A found monthly market must be returned without probing the rest."""
    tz = zoneinfo.ZoneInfo("America/New_York")
    now = datetime.datetime(2026, 3, 15, tzinfo=tz).timestamp()
    monkeypatch.setattr(time, "time", lambda: now)

    from polyalpha.core.market import Market

    client = MarketClient()
    tried = []

    def fake_fetch(slug):
        tried.append(slug)
        if slug.endswith("march-2026"):
            return Market(
                id="e1", question="q", description="",
                slug=slug, active=True, closed=False, archived=False,
                start_time="", end_time="", volume=0, liquidity=0,
                outcomes=["UP", "DOWN"], prices=[0.5, 0.5], tokens=["u", "d"],
            )
        raise MarketNotFound(slug)

    monkeypatch.setattr(client, "_fetch_by_slug", fake_fetch)

    market = client.latest_tweet("elon-musk", "1mo")

    assert market.slug == "elon-musk-of-tweets-march-2026"
    assert tried == ["elon-musk-of-tweets-march-2026"]
