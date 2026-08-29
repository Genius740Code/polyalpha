"""
HubFeed tests — the Stream-compatible adapter that lets the Sniper consume
the shared hub feed instead of opening its own WebSocket (issue #2).
"""

import pytest

from polyalpha.bots import HubFeed


@pytest.mark.unit
def test_hub_feed_push_updates_prices():
    feed = HubFeed(up=0.5, down=0.5)
    feed.push(0.95, 0.45)
    assert feed.up == 0.95
    assert feed.down == 0.45


@pytest.mark.unit
def test_hub_feed_push_emits_price_event():
    feed = HubFeed(up=0.5, down=0.5)
    seen = []
    feed.on("price")(lambda up, down: seen.append((up, down)))
    feed.push(0.9, 0.1)
    assert seen == [(0.9, 0.1)]


@pytest.mark.unit
def test_hub_feed_price_age_seconds_resets_on_push():
    feed = HubFeed(up=0.5, down=0.5)
    feed._last_price_time = 0.0
    assert feed.price_age_seconds() > 0
    feed.push(0.8, 0.2)
    assert feed.price_age_seconds() < 1.0


@pytest.mark.unit
def test_hub_feed_push_book_up_uses_best_level():
    feed = HubFeed(up=0.5, down=0.5)
    feed.push_book("UP", [{"price": "0.94"}], [{"price": "0.96"}])
    assert feed.up == pytest.approx(0.95)
    assert feed.down == 0.5


@pytest.mark.unit
def test_hub_feed_push_book_down_preserves_orientation():
    feed = HubFeed(up=0.5, down=0.5)
    feed.push_book("down", [{"price": "0.04"}], [{"price": "0.06"}])
    assert feed.down == pytest.approx(0.05)
    assert feed.up == 0.5


@pytest.mark.unit
def test_hub_feed_push_book_last_trade_fallback():
    feed = HubFeed(up=0.5, down=0.5)
    feed.push_book("UP", [], [], last_trade_price=0.91)
    assert feed.up == pytest.approx(0.91)


@pytest.mark.unit
def test_hub_feed_push_book_ignores_empty_book():
    feed = HubFeed(up=0.5, down=0.5)
    feed.push_book("UP", [], [])
    assert feed.up == 0.5


@pytest.mark.unit
def test_hub_feed_close_emits_close_and_stops():
    feed = HubFeed(up=0.5, down=0.5)
    feed.start()
    closed = []
    feed.on("close")(lambda: closed.append(True))
    feed.close()
    assert closed == [True]
    assert feed.running is False


@pytest.mark.unit
def test_hub_feed_unknown_event_rejected():
    feed = HubFeed()
    with pytest.raises(ValueError, match="Unknown event"):
        feed.add_handler("bogus", lambda: None)


@pytest.mark.unit
def test_hub_feed_add_handler_and_emit():
    feed = HubFeed(up=0.5, down=0.5)
    calls = []
    feed.add_handler("price", lambda up, down: calls.append(up + down))
    feed.emit("price", 0.3, 0.7)
    assert calls == [1.0]


# ── Book-level parity: best vs worst (issue #3) ─────────────────────────────

@pytest.mark.unit
def test_hub_feed_book_uses_best_level_not_worst():
    """Best bid/ask (index 0) must be used — not the worst level (index -1)."""
    feed = HubFeed(up=0.5, down=0.5)
    # Two levels: best bid 0.60/ask 0.62 → mid 0.61; worst would be (0.40+0.90)/2=0.65
    feed.push_book("UP", [{"price": "0.60"}, {"price": "0.40"}], [{"price": "0.62"}, {"price": "0.90"}])
    assert feed.up == pytest.approx(0.61)
    # Ensure worst is not used
    assert feed.up != pytest.approx(0.65)


@pytest.mark.unit
def test_hub_feed_best_mid_helper_is_best():
    """Direct helper also uses best level."""
    from polyalpha.bots.hub_feed import _best_mid
    best = _best_mid([{"price": "0.60"}, {"price": "0.40"}], [{"price": "0.62"}, {"price": "0.90"}])
    assert best == pytest.approx(0.61)
    worst = (0.40 + 0.90) / 2
    assert best != pytest.approx(worst)


# ── Market provider for hub-aligned discovery (issue #5) ────────────────────

@pytest.mark.unit
def test_hub_feed_market_provider_get_set():
    feed = HubFeed(up=0.5, down=0.5)
    assert feed.get_market() is None
    fake_market = type("M", (), {"slug": "btc-updown-5m-123"})()
    feed.set_market(fake_market)
    assert feed.get_market() is fake_market
    assert feed.market is fake_market


@pytest.mark.unit
def test_hub_feed_push_market_alias():
    feed = HubFeed()
    m = type("M", (), {"slug": "eth-updown-5m-456"})()
    feed.push_market(m)
    assert feed.get_market() is m
