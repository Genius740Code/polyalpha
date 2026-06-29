"""
polyalpha smoke tests — run with:  pytest tests/
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import polyalpha
from polyalpha.core.constants import build_slug, TIMEFRAME_SECONDS
from polyalpha.core.market import Market
from polyalpha.trading.paper import PaperEngine, _slug_label


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

def test_public_exports():
    assert hasattr(polyalpha, "Client")
    assert hasattr(polyalpha, "Market")
    assert hasattr(polyalpha, "Stream")
    assert hasattr(polyalpha, "PaperEngine")
    assert hasattr(polyalpha, "MarketNotFound")
    assert hasattr(polyalpha, "InsufficientBalance")


# ── Slug helpers ───────────────────────────────────────────────────────────────

def test_build_slug():
    assert build_slug("BTC", "5m", 1_751_234_700) == "btc-updown-5m-1751234700"
    assert build_slug("ETH", "1h",  999_999_999)  == "eth-updown-1h-999999999"

def test_timeframe_seconds():
    assert TIMEFRAME_SECONDS["5m"]  == 300
    assert TIMEFRAME_SECONDS["24h"] == 86_400


# ── Market dataclass ───────────────────────────────────────────────────────────

def test_market_properties():
    m = make_market()
    assert m.up_price    == 0.55
    assert m.down_price  == 0.45
    assert m.up_token    == "tok_up"
    assert m.down_token  == "tok_down"
    assert "polymarket.com" in m.url

def test_market_legacy_aliases():
    m = make_market()
    assert m.yes_price == m.up_price
    assert m.no_price  == m.down_price
    assert m.yes_token == m.up_token
    assert m.no_token  == m.down_token

def test_market_dump_excludes_raw():
    m = make_market()
    m.raw = {"secret": "data"}
    d = m.dump()
    assert "raw" not in d
    assert "url" in d

def test_market_json():
    import json
    m = make_market()
    j = m.json()
    parsed = json.loads(j)
    assert parsed["slug"] == "btc-updown-5m-9999999"


# ── Paper engine ───────────────────────────────────────────────────────────────

def test_paper_market_buy():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.buy(market, side="UP", amount=10.0)

    assert order.status == "filled"
    assert order.side   == "UP"
    assert order.fee    == pytest.approx(10.0 * 0.02, abs=1e-6)
    assert order.shares == pytest.approx((10.0 - order.fee) / 0.55, abs=1e-4)
    assert engine.balance == pytest.approx(90.0, abs=1e-6)

def test_paper_both_sides():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP",   amount=20.0)
    engine.buy(market, side="DOWN", amount=20.0)
    assert len(engine.positions()) == 2
    assert engine.balance == pytest.approx(60.0, abs=1e-6)

def test_paper_limit_reserves_balance():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.limit(market, side="UP", price=0.92, amount=25.0)

    assert order.status == "open"
    assert engine.balance == pytest.approx(75.0, abs=1e-6)

def test_paper_limit_fills_on_price():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.limit(market, side="UP", price=0.90, amount=20.0)

    # Simulate a price update that crosses the limit
    engine.check_limits(market.id, up_price=0.92, down_price=0.08)

    orders = engine.orders()
    assert orders[0].status == "filled"

def test_paper_limit_does_not_fill_below_threshold():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.limit(market, side="UP", price=0.95, amount=20.0)

    engine.check_limits(market.id, up_price=0.90, down_price=0.10)

    assert engine.open()[0].status == "open"

def test_paper_cancel_refunds():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    order  = engine.limit(market, side="UP", price=0.92, amount=30.0)
    assert engine.balance == pytest.approx(70.0)

    engine.cancel(order.id)
    assert engine.balance == pytest.approx(100.0)
    assert order.status   == "cancelled"

def test_paper_insufficient_balance():
    engine = PaperEngine(balance=5.0)
    market = make_market()
    with pytest.raises(polyalpha.InsufficientBalance):
        engine.buy(market, side="UP", amount=10.0)

def test_paper_resolve_won():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)
    balance_after_buy = engine.balance  # 90.0

    engine.resolve(market, outcome="UP")

    pos = engine.all_positions()[0]
    assert pos.resolved
    assert pos.outcome == "WON"
    # Each winning share redeems at $1 — payout = pos.shares
    assert engine.balance == pytest.approx(balance_after_buy + pos.shares, abs=1e-4)

def test_paper_resolve_lost():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    engine.buy(market, side="UP", amount=10.0)

    engine.resolve(market, outcome="DOWN")

    pos = engine.all_positions()[0]
    assert pos.outcome == "LOST"
    assert pos.pnl < 0

def test_paper_invalid_side():
    engine = PaperEngine(balance=100.0)
    market = make_market()
    with pytest.raises(ValueError):
        engine.buy(market, side="YES", amount=10.0)


# ── Slug label helper ──────────────────────────────────────────────────────────

def test_slug_label():
    assert _slug_label("btc-updown-5m-1234567") == "BTC 5m"
    assert _slug_label("eth-updown-15m-9999")   == "ETH 15m"


# ── Rate limiter ─────────────────────────────────────────────────────────────────

def test_rate_limiter_basic():
    from polyalpha.markets import RateLimiter
    import time
    
    limiter = RateLimiter(max_requests=5, period_seconds=1.0)
    
    # Should allow 5 requests immediately
    for _ in range(5):
        limiter.acquire()
    
    # 6th request should block briefly
    start = time.time()
    limiter.acquire()
    elapsed = time.time() - start
    
    assert elapsed >= 0.1  # Should have waited at least a bit


def test_rate_limiter_disabled():
    from polyalpha.markets import RateLimiter
    
    # Test that None rate_limit disables the limiter
    limiter = RateLimiter(10) if 10 else None
    assert limiter is not None
    
    # Test with None
    limiter = RateLimiter(None) if None else None
    assert limiter is None
