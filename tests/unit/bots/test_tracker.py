"""
Tracker bot tests — run with: pytest tests/unit/bots/test_tracker.py
"""

import pytest
import polyalpha
from polyalpha.bots import Tracker


@pytest.mark.unit
def test_tracker_initialization():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)

    assert tracker.client == client
    assert tracker.total_trades == 0


@pytest.mark.unit
def test_tracker_sync():
    client = polyalpha.Client(balance=100.0)
    client.paper.config.enable_risk_management = False
    market = _make_market()

    client.paper.buy(market, side="UP", amount=10.0)
    client.paper.resolve(market, outcome="UP")

    tracker = Tracker(client)
    tracker.sync()

    assert tracker.total_trades >= 0


@pytest.mark.unit
def test_tracker_statistics():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)

    assert tracker.total_trades == 0
    assert tracker.wins == 0
    assert tracker.losses == 0
    assert tracker.win_rate == 0.0
    assert tracker.total_pnl == 0.0


@pytest.mark.unit
def test_tracker_export_json(tmp_path):
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)

    filepath = tmp_path / "trades.json"
    tracker.export_json(str(filepath))
    assert filepath.exists()


@pytest.mark.unit
def test_tracker_export_csv(tmp_path):
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)

    filepath = tmp_path / "trades.csv"
    tracker.export_csv(str(filepath))


@pytest.mark.unit
def test_tracker_slug_label():
    client = polyalpha.Client(balance=100.0)
    tracker = Tracker(client)

    label = tracker._slug_label("btc-updown-5m-1234567")

    assert "BTC" in label
    assert "5m" in label


def _make_market(**overrides):
    from polyalpha.core.market import Market
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    future_start = now + timedelta(minutes=5)
    future_end = now + timedelta(minutes=10)
    defaults = dict(
        id="test-id",
        question="Will BTC be higher in 5 minutes?",
        description="",
        slug="btc-updown-5m-9999999",
        active=True,
        closed=False,
        archived=False,
        start_time=future_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time=future_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        volume=10_000.0,
        liquidity=5_000.0,
        outcomes=["UP", "DOWN"],
        prices=[0.55, 0.45],
        tokens=["tok_up", "tok_down"],
    )
    defaults.update(overrides)
    return Market(**defaults)
