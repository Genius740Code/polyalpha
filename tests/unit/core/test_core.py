"""
Core module tests — run with: pytest tests/unit/core/test_core.py
"""

import pytest
import polyalpha
from polyalpha.core.constants import build_slug, build_tweet_slug, TIMEFRAME_SECONDS, ASSETS
from polyalpha.core.market import Market


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_market(**overrides) -> Market:
    defaults = dict(
        id          = "test-id",
        question    = "Will BTC be higher in 5 minutes?",
        description = "",
        slug        = "btc-updown-5m-9999999",
        active      = True,
        closed      = False,
        archived    = False,
        start_time  = "2025-01-01T00:00:00Z",
        end_time    = "2025-01-01T00:05:00Z",
        volume      = 10_000.0,
        liquidity   = 5_000.0,
        outcomes    = ["UP", "DOWN"],
        prices      = [0.55, 0.45],
        tokens      = ["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)


# ── Public API surface ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_public_exports():
    assert hasattr(polyalpha, "Client")
    assert hasattr(polyalpha, "Market")
    assert hasattr(polyalpha, "Stream")
    assert hasattr(polyalpha, "PaperEngine")
    assert hasattr(polyalpha, "MarketNotFound")
    assert hasattr(polyalpha, "InsufficientBalance")


# ── Slug helpers ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_build_slug():
    assert build_slug("BTC", "5m", 1_751_234_700) == "btc-updown-5m-1751234700"
    
    # 1h format test
    assert build_slug("BTC", "1h", 1783191600) == "bitcoin-up-or-down-july-4-2026-3pm-et"
    
    # 24h format test
    import datetime
    import zoneinfo
    tz = zoneinfo.ZoneInfo("America/New_York")
    ts_daily = int(datetime.datetime(2026, 7, 4, 0, 0, tzinfo=tz).timestamp())
    assert build_slug("BTC", "24h", ts_daily) == "what-price-will-bitcoin-hit-on-july-4"

@pytest.mark.unit
def test_build_tweet_slug():
    import datetime
    import zoneinfo
    tz = zoneinfo.ZoneInfo("America/New_York")
    
    # elon-musk-of-tweets-june-30-july-7
    ts_start = int(datetime.datetime(2026, 6, 30, 0, 0, tzinfo=tz).timestamp())
    ts_end = int(datetime.datetime(2026, 7, 7, 0, 0, tzinfo=tz).timestamp())
    assert build_tweet_slug("elon-musk", ts_start, ts_end) == "elon-musk-of-tweets-june-30-july-7"
    
    # monthly: elon-musk-of-tweets-march-2026
    ts_monthly = int(datetime.datetime(2026, 3, 15, 0, 0, tzinfo=tz).timestamp())
    assert build_tweet_slug("elon-musk", ts_monthly, monthly=True) == "elon-musk-of-tweets-march-2026"

@pytest.mark.unit
def test_timeframe_seconds():
    assert TIMEFRAME_SECONDS["5m"]  == 300
    assert TIMEFRAME_SECONDS["24h"] == 86_400


@pytest.mark.unit
def test_assets_list():
    assert "BTC" in ASSETS
    assert "ETH" in ASSETS
    assert "SOL" in ASSETS
    assert "XRP" in ASSETS
    assert "DOGE" in ASSETS
    assert "HYPE" in ASSETS
    assert "BNB" in ASSETS
    assert len(ASSETS) == 7


@pytest.mark.unit
def test_timeframe_completeness():
    expected = ["5m", "15m", "1h", "4h", "24h"]
    for tf in expected:
        assert tf in TIMEFRAME_SECONDS
        assert TIMEFRAME_SECONDS[tf] > 0


# ── Market dataclass ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_market_properties():
    m = make_market()
    assert m.up_price    == 0.55
    assert m.down_price  == 0.45
    assert m.up_token    == "tok_up"
    assert m.down_token  == "tok_down"
    assert "polymarket.com" in m.url


@pytest.mark.unit
def test_market_no_legacy_aliases():
    """Verify legacy YES/NO aliases have been removed."""
    m = make_market()
    assert not hasattr(m, "yes_price")
    assert not hasattr(m, "no_price")
    assert not hasattr(m, "yes_token")
    assert not hasattr(m, "no_token")


@pytest.mark.unit
def test_market_dump_excludes_raw():
    m = make_market()
    m.raw = {"secret": "data"}
    d = m.dump()
    assert "raw" not in d
    assert "url" in d


@pytest.mark.unit
def test_market_json():
    import json
    m = make_market()
    j = m.json()
    parsed = json.loads(j)
    assert parsed["slug"] == "btc-updown-5m-9999999"


@pytest.mark.unit
def test_market_empty_prices():
    m = make_market(prices=[])
    assert m.up_price == 0.0
    assert m.down_price == 0.0


@pytest.mark.unit
def test_market_single_price():
    m = make_market(prices=[0.60])
    assert m.up_price == 0.60
    assert m.down_price == 0.0


@pytest.mark.unit
def test_market_empty_tokens():
    m = make_market(tokens=[])
    assert m.up_token == ""
    assert m.down_token == ""


@pytest.mark.unit
def test_market_single_token():
    m = make_market(tokens=["tok_up"])
    assert m.up_token == "tok_up"
    assert m.down_token == ""


# ── Client initialization ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_client_initialization():
    client = polyalpha.Client(balance=500.0, timeout=15, retries=5, log_level="INFO")
    assert client._timeout == 15
    assert client._retries == 5
    assert client.paper.balance == 500.0


@pytest.mark.unit
def test_client_default_initialization():
    client = polyalpha.Client()
    assert client._timeout == 10
    assert client._retries == 3
    assert client.paper.balance == 100.0


# ── Error handling ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_market_not_found_error():
    exc = polyalpha.MarketNotFound("test message")
    assert isinstance(exc, polyalpha.PolyalphaError)
    assert str(exc) == "test message"


@pytest.mark.unit
def test_market_closed_error():
    exc = polyalpha.MarketClosed("test message")
    assert isinstance(exc, polyalpha.PolyalphaError)


@pytest.mark.unit
def test_stream_disconnected_error():
    exc = polyalpha.StreamDisconnected("test message")
    assert isinstance(exc, polyalpha.PolyalphaError)


@pytest.mark.unit
def test_insufficient_balance_error():
    exc = polyalpha.InsufficientBalance("test message")
    assert isinstance(exc, polyalpha.PolyalphaError)


@pytest.mark.unit
def test_order_not_found_error():
    exc = polyalpha.OrderNotFound("test message")
    assert isinstance(exc, polyalpha.PolyalphaError)
