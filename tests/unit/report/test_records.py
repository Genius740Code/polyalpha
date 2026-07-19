"""
Report records tests — run with: pytest tests/unit/report/test_records.py
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from polyalpha.trading.paper import PaperEngine, PaperOrder, PaperPosition
from polyalpha.report.records import TradeRecord, extract_trades, build_equity_curve


@pytest.mark.unit
class TestExtractTrades:
    """Test trade extraction from PaperEngine."""

    def test_empty_engine(self):
        """Test extraction from empty engine."""
        engine = PaperEngine(balance=100.0)
        assert extract_trades(engine) == []

    def test_open_positions_excluded(self):
        """Test that open positions are excluded."""
        engine = PaperEngine(balance=100.0)
        # Add an unresolved position
        engine._positions["mkt_01:UP"] = PaperPosition(
            market_id="mkt_01", slug="btc-1", question="q", side="UP",
            shares=10.0, avg_price=0.7, current_price=0.72,
            resolved=False, outcome=None, order_ids=[],
        )
        assert extract_trades(engine) == []

    def test_resolved_positions_extracted(self):
        """Test that resolved positions are extracted."""
        engine = self._make_engine_with_resolved([3.0, -2.0, 5.0])
        trades = extract_trades(engine)
        assert len(trades) == 3

    def test_sorted_chronologically(self):
        """Test that trades are sorted chronologically."""
        engine = self._make_engine_with_resolved([1.0, -1.0, 2.0])
        trades = extract_trades(engine)
        times = [t.entry_time for t in trades]
        assert times == sorted(times)

    def test_pnl_sign_correct(self):
        """Test that P&L sign is correct."""
        engine = self._make_engine_with_resolved([5.0, -3.0])
        trades = extract_trades(engine)
        wins = [t for t in trades if t.outcome == "WON"]
        losses = [t for t in trades if t.outcome == "LOST"]
        assert all(t.pnl > 0 for t in wins)
        assert all(t.pnl < 0 for t in losses)

    def test_trade_id_unique(self):
        """Test that trade IDs are unique."""
        engine = self._make_engine_with_resolved([1.0, 1.0, -1.0])
        trades = extract_trades(engine)
        ids = [t.trade_id for t in trades]
        assert len(ids) == len(set(ids))

    def _make_engine_with_resolved(self, pnls, initial_balance=1000.0):
        """Build a PaperEngine with synthetic resolved positions."""
        engine = PaperEngine(balance=initial_balance)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)

        for i, pnl in enumerate(pnls):
            market_id = f"mkt_{i:04d}"
            slug = f"btc-updown-5m-{i:04d}"
            side = "UP"
            entry_price = 0.70
            amount_in = 10.0
            shares = (amount_in * 0.98) / entry_price  # 2% fee

            entry_time = base + timedelta(hours=i)
            exit_time = entry_time + timedelta(minutes=30)

            order_id = str(uuid.uuid4())
            order = PaperOrder(
                id=order_id,
                market_id=market_id,
                slug=slug,
                side=side,
                price=entry_price,
                amount=amount_in,
                shares=shares,
                fee=amount_in * 0.02,
                status="filled",
                is_limit=False,
                filled_at=entry_time,
            )
            engine._orders[order_id] = order

            outcome = "WON" if pnl > 0 else "LOST"
            engine._balance += pnl

            pos = PaperPosition(
                market_id=market_id,
                slug=slug,
                question=f"Will BTC rise? #{i}",
                side=side,
                shares=shares,
                avg_price=entry_price,
                current_price=1.0 if outcome == "WON" else 0.0,
                resolved=True,
                outcome=outcome,
                order_ids=[order_id],
            )
            engine._positions[f"{market_id}:{side}"] = pos

        return engine


@pytest.mark.unit
class TestBuildEquityCurve:
    """Test equity curve building."""

    def _make_trade(self, pnl, amount_in=10.0):
        """Helper to create a TradeRecord."""
        entry_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        exit_time = entry_time + timedelta(seconds=300)
        outcome = "WON" if pnl > 0 else "LOST"
        exit_price = 1.0 if outcome == "WON" else 0.0
        pnl_pct = (pnl / amount_in) * 100 if amount_in else 0.0
        return TradeRecord(
            trade_id=str(uuid.uuid4()),
            market_slug="btc-updown-5m-0001",
            market_id="mkt_001",
            side="UP",
            entry_price=0.70,
            exit_price=exit_price,
            shares=amount_in / 0.70,
            amount_in=amount_in,
            fee=0.0,
            pnl=pnl,
            pnl_pct=pnl_pct,
            entry_time=entry_time,
            exit_time=exit_time,
            holding_secs=300.0,
            outcome=outcome,
            fill_type="market",
            slippage=0.0,
            order_count=1,
        )

    def _make_trades_sequence(self, pnls):
        """Create a sequence of trades with timestamps 1 day apart."""
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        trades = []
        for i, p in enumerate(pnls):
            t = self._make_trade(pnl=p, amount_in=10.0)
            t.entry_time = base + timedelta(days=i)
            t.exit_time = t.entry_time + timedelta(minutes=30)
            trades.append(t)
        return trades

    def test_empty_trades(self):
        """Test equity curve with no trades."""
        trades = []
        ts, eq = build_equity_curve(trades, 100.0)
        assert len(ts) == 1
        assert eq[0] == 100.0

    def test_single_win(self):
        """Test equity curve with single win."""
        trades = [self._make_trade(10.0, amount_in=10.0)]
        ts, eq = build_equity_curve(trades, 100.0)
        assert eq[0] == 100.0
        assert eq[-1] == pytest.approx(110.0, abs=1e-6)

    def test_single_loss(self):
        """Test equity curve with single loss."""
        trades = [self._make_trade(-5.0, amount_in=10.0)]
        ts, eq = build_equity_curve(trades, 100.0)
        assert eq[-1] == pytest.approx(95.0, abs=1e-6)

    def test_length_correct(self):
        """Test that equity curve length is correct."""
        trades = self._make_trades_sequence([1, -1, 2, -2, 3])
        ts, eq = build_equity_curve(trades, 100.0)
        assert len(ts) == len(trades) + 1
        assert len(eq) == len(trades) + 1

    def test_monotone_wins(self):
        """Test equity curve with monotonic wins."""
        trades = self._make_trades_sequence([10, 10, 10])
        _, eq = build_equity_curve(trades, 100.0)
        for i in range(len(eq) - 1):
            assert eq[i + 1] > eq[i]
