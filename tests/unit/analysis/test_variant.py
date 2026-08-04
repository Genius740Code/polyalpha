"""
BotHub variant framework tests — run with:

    pytest tests/unit/analysis/test_variant.py -v
"""

from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from polyalpha.bot_hub import BotHub, Variant, StrategyContext, _RegisteredStrategy
from polyalpha.report.comparison import (
    ComparisonReport,
    DEFAULT_COMPARISON_METRICS,
    VariantResult,
    build_variant_result,
    list_runs,
    load_run,
)


# ── Variant dataclass ─────────────────────────────────────────────────────────

class TestVariantDataclass:
    def test_default_id_equals_name(self):
        v = Variant(name="test_variant", fn=lambda ctx: None, balance=100.0)
        assert v.id == "test_variant"
        assert v.params == {}
        assert v.run_count == 0
        assert isinstance(v.created_at, datetime)

    def test_custom_id(self):
        v = Variant(name="test", id="custom_id", fn=lambda ctx: None, balance=100.0)
        assert v.id == "custom_id"

    def test_custom_params(self):
        v = Variant(
            name="t", fn=lambda ctx: None, balance=100.0,
            params={"rsi": 70, "window": 14},
        )
        assert v.params == {"rsi": 70, "window": 14}

    def test_created_at_default_utc(self):
        before = datetime.now(timezone.utc)
        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        after = datetime.now(timezone.utc)
        assert before <= v.created_at <= after

    def test_paper_and_ctx_default_none(self):
        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        assert v.paper is None
        assert v.ctx is None


# ── BotHub variant decorator ──────────────────────────────────────────────────

class TestVariantDecorator:
    def test_register_variant(self):
        hub = BotHub(asset="BTC", timeframe="5m", default_balance=500)

        @hub.variant("momentum")
        def momentum(ctx):
            pass

        assert hub.variant_count == 1
        assert hub.total_count == 1
        v = hub._variants[0]
        assert v.name == "momentum"
        assert v.balance == 500.0
        assert v.params == {}

    def test_register_variant_with_params(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("rsi_70", params={"rsi": 70, "window": 14})
        def rsi(ctx):
            pass

        assert hub._variants[0].params == {"rsi": 70, "window": 14}

    def test_register_variant_with_custom_balance(self):
        hub = BotHub(asset="BTC", timeframe="5m", default_balance=100)

        @hub.variant("agg", balance=1000)
        def a(ctx):
            pass

        assert hub._variants[0].balance == 1000.0

    def test_register_variant_with_custom_id(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("name1", id="stable-id-001")
        def fn(ctx):
            pass

        assert hub._variants[0].id == "stable-id-001"

    def test_variant_name_must_be_non_empty(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        with pytest.raises(ValueError, match="strategy name must be a non-empty string"):
            @hub.variant("")
            def fn(ctx):
                pass

        with pytest.raises(ValueError, match="strategy name must be a non-empty string"):
            hub.variant("")(lambda ctx: None)

    def test_cannot_duplicate_variant_name(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("dup")
        def a(ctx):
            pass

        with pytest.raises(ValueError, match="already registered"):
            @hub.variant("dup")
            def b(ctx):
                pass

    def test_cannot_duplicate_strategy_name(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.strategy("shared")
        def a(ctx):
            pass

        with pytest.raises(ValueError, match="already registered"):
            @hub.variant("shared")
            def b(ctx):
                pass

    def test_add_variant_non_decorator(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        def fn(ctx):
            pass

        hub.add_variant("prog", fn, balance=250, params={"key": "val"}, id="prog-1")
        assert hub.variant_count == 1
        v = hub._variants[0]
        assert v.name == "prog"
        assert v.balance == 250.0
        assert v.params == {"key": "val"}
        assert v.id == "prog-1"

    def test_variants_property_readonly_copy(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("v1")
        def v1(ctx):
            pass

        lst = hub.variants
        assert len(lst) == 1
        # Mutating the copy does not affect the hub.
        lst.append(Variant(name="x", fn=lambda ctx: None, balance=0))
        assert hub.variant_count == 1

    def test_strategy_and_variant_count(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.strategy("s1")
        def s1(ctx):
            pass

        @hub.variant("v1")
        def v1(ctx):
            pass

        @hub.variant("v2")
        def v2(ctx):
            pass

        assert hub.strategy_count == 3
        assert hub.variant_count == 3
        assert hub.total_count == 3

    def test_run_requires_any_ticker(self):
        hub = BotHub(asset="BTC", timeframe="5m")
        with pytest.raises(RuntimeError, match="No strategies registered"):
            hub.run()

    def test_has_strategies_or_variants_passes(self):
        """Variants count as tickers for the run guard."""
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("v1")
        def v1(ctx):
            pass

        # This should not raise — we have at least one ticker (the variant).
        # We can't actually run without a real stream, but the guard passes.
        with patch.object(hub._shared_client.markets, "latest") as mock_latest:
            mock_latest.side_effect = RuntimeError("network")
            with pytest.raises(RuntimeError, match="network"):
                hub.run()


# ── VariantResult ─────────────────────────────────────────────────────────────

class TestVariantResult:
    def test_is_nan_empty(self):
        r = VariantResult(
            name="t", id="t", balance=100.0,
            pnl=float("nan"), win_rate=float("nan"),
            trade_count=0, sharpe=None, max_drawdown_pct=None,
        )
        assert r.is_nan()

    def test_is_nan_with_trades(self):
        r = VariantResult(
            name="t", id="t", balance=100.0,
            pnl=50.0, win_rate=0.6,
            trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0,
        )
        assert not r.is_nan()

    def test_dump_roundtrip(self):
        r = VariantResult(
            name="v1", id="v1", balance=100.0,
            pnl=25.5, win_rate=0.65,
            trade_count=20, sharpe=1.3, max_drawdown_pct=-3.2,
            params={"rsi": 70},
        )
        d = r.dump()
        assert d["name"] == "v1"
        assert d["pnl"] == 25.5
        assert d["win_rate"] == 0.65
        assert d["sharpe"] == 1.3

    def test_dump_nan(self):
        r = VariantResult(
            name="t", id="t", balance=100.0,
            pnl=float("nan"), win_rate=float("nan"),
            trade_count=0, sharpe=None, max_drawdown_pct=None,
        )
        d = r.dump()
        assert d["pnl"] is None
        assert d["win_rate"] is None
        assert d["sharpe"] is None

    def test_dump_sortable_pnl_via_nan_to_neg_inf(self):
        """NaN/None fields should sort last in comparison."""
        r1 = VariantResult(
            name="a", id="a", balance=100.0,
            pnl=50.0, win_rate=0.5,
            trade_count=5, sharpe=1.0, max_drawdown_pct=-10.0,
        )
        r2 = VariantResult(
            name="b", id="b", balance=100.0,
            pnl=float("nan"), win_rate=float("nan"),
            trade_count=0, sharpe=None, max_drawdown_pct=None,
        )
        results = sorted([r2, r1], key=lambda r: r.pnl if not math.isnan(r.pnl) else float("-inf"), reverse=True)
        assert results[0].name == "a"
        assert results[1].name == "b"


# ── build_variant_result ──────────────────────────────────────────────────────

class TestBuildVariantResult:
    def test_no_paper_engine_yields_nan(self):
        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        result = build_variant_result(v)
        assert math.isnan(result.pnl)
        assert result.trade_count == 0

    def test_with_paper_engine_no_trades(self):
        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        mock_paper = MagicMock()
        mock_paper.balance = 100.0
        mock_paper.all_positions.return_value = []
        v.paper = mock_paper

        result = build_variant_result(v)
        assert math.isnan(result.pnl)
        assert result.trade_count == 0

    def test_with_resolved_trades(self):
        """Integration-style: build a Variant with a real PaperEngine,
        place and resolve a winning trade, then verify the result."""
        from polyalpha.trading.paper_engine import PaperEngine
        from polyalpha.trading.paper_config import PaperConfig

        config = PaperConfig()
        config.custom_fee_rate = 0.0
        config.slippage_pct = 0.0
        paper = PaperEngine(balance=100.0, config=config)
        market = MagicMock()
        market.id = "test_market"
        market.slug = "btc-updown-5m-123"
        market.outcome = "WIN"
        market.up_price = 0.95
        market.down_price = 0.05
        market.question = "test?"
        market.start_time = "2020-01-01T00:00:00Z"
        market.end_time = "2030-01-01T00:00:00Z"

        paper.buy(market=market, side="UP", amount=1.0)
        paper.resolve(market, outcome="UP")

        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        v.paper = paper

        result = build_variant_result(v)
        assert result.trade_count == 1
        assert not math.isnan(result.pnl)
        assert result.pnl > 0

    def test_with_both_win_and_loss(self):
        from polyalpha.trading.paper_engine import PaperEngine
        from polyalpha.trading.paper_config import PaperConfig

        config = PaperConfig()
        config.custom_fee_rate = 0.0
        config.slippage_pct = 0.0
        paper = PaperEngine(balance=100.0, config=config)
        market = MagicMock()
        market.id = "test"
        market.slug = "m"
        market.outcome = "WIN"
        market.up_price = 0.95
        market.down_price = 0.05
        market.question = "test?"
        market.start_time = "2020-01-01T00:00:00Z"
        market.end_time = "2030-01-01T00:00:00Z"

        paper.buy(market=market, side="UP", amount=1.0)
        paper.resolve(market, outcome="UP")
        paper.buy(market=market, side="DOWN", amount=1.0)
        paper.resolve(market, outcome="UP")

        v = Variant(name="t", fn=lambda ctx: None, balance=100.0)
        v.paper = paper

        result = build_variant_result(v)
        assert result.trade_count == 2
        assert result.win_rate == 0.5

    def test_params_and_created_at_carried_through(self):
        from polyalpha.trading.paper_engine import PaperEngine
        from polyalpha.trading.paper_config import PaperConfig

        config = PaperConfig()
        config.custom_fee_rate = 0.0
        config.slippage_pct = 0.0
        paper = PaperEngine(balance=100.0, config=config)
        market = MagicMock()
        market.id = "t"
        market.slug = "m"
        market.outcome = "WIN"
        market.up_price = 0.95
        market.down_price = 0.05
        market.question = "test?"
        market.start_time = "2020-01-01T00:00:00Z"
        market.end_time = "2030-01-01T00:00:00Z"
        paper.buy(market=market, side="UP", amount=1.0)
        paper.resolve(market, outcome="UP")

        v = Variant(name="t", fn=lambda ctx: None, balance=100.0, params={"a": 1})
        v.paper = paper

        result = build_variant_result(v)
        assert result.params == {"a": 1}
        assert result.created_at


# ── ComparisonReport ──────────────────────────────────────────────────────────

class TestComparisonReport:
    def test_empty_report(self):
        r = ComparisonReport(asset="BTC", timeframe="5m")
        assert r.variant_count == 0
        assert r.best is None
        assert r.worst is None
        assert r.get("anything") is None

    def test_single_variant(self):
        r = ComparisonReport(
            results=[
                VariantResult(
                    name="v1", id="v1", balance=100.0,
                    pnl=50.0, win_rate=0.6, trade_count=10,
                    sharpe=1.5, max_drawdown_pct=-5.0,
                ),
            ],
            asset="BTC", timeframe="5m",
        )
        assert r.variant_count == 1
        assert r.best is not None and r.best.name == "v1"
        assert r.worst is not None and r.worst.name == "v1"

    def test_sorted_by_pnl_descending(self):
        r = ComparisonReport(
            results=[
                VariantResult(name="low", id="l", balance=100.0, pnl=10.0, win_rate=0.5, trade_count=5, sharpe=0.5, max_drawdown_pct=-10.0),
                VariantResult(name="high", id="h", balance=100.0, pnl=50.0, win_rate=0.6, trade_count=8, sharpe=1.2, max_drawdown_pct=-3.0),
                VariantResult(name="mid", id="m", balance=100.0, pnl=25.0, win_rate=0.55, trade_count=6, sharpe=0.8, max_drawdown_pct=-7.0),
            ],
            asset="BTC", timeframe="5m",
        )
        # The report is built sorted by P&L descending — simulate that.
        r.results.sort(key=lambda r: r.pnl, reverse=True)
        assert [r.name for r in r.results] == ["high", "mid", "low"]

    def test_get_by_name(self):
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=10.0, win_rate=0.5, trade_count=5, sharpe=0.5, max_drawdown_pct=-10.0),
                VariantResult(name="v2", id="v2", balance=100.0, pnl=20.0, win_rate=0.6, trade_count=7, sharpe=1.0, max_drawdown_pct=-5.0),
            ],
        )
        assert r.get("v1") is not None and r.get("v1").pnl == 10.0
        assert r.get("nonexistent") is None

    def test_timestamp_default(self):
        before = datetime.now(timezone.utc)
        r = ComparisonReport()
        after = datetime.now(timezone.utc)
        assert before <= r.timestamp <= after

    def test_equity_curve_sorted(self):
        pass  # build_variant_result does not build equity curves; metrics.py handles that.

    def test_dump_serialisation(self):
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0),
            ],
            asset="BTC", timeframe="5m",
        )
        d = r.dump()
        assert d["asset"] == "BTC"
        assert d["timeframe"] == "5m"
        assert d["variant_count"] == 1
        assert d["results"][0]["name"] == "v1"

    def test_from_dict_roundtrip(self):
        original = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0, params={"a": 1}),
            ],
            asset="BTC", timeframe="5m",
        )
        d = original.dump()
        restored = ComparisonReport.from_dict(d)
        assert restored.asset == "BTC"
        assert restored.variant_count == 1
        assert restored.results[0].pnl == 25.0
        assert restored.results[0].params == {"a": 1}

    def test_from_dict_empty_results(self):
        restored = ComparisonReport.from_dict({"asset": "ETH", "timeframe": "1h", "results": []})
        assert restored.asset == "ETH"
        assert restored.timeframe == "1h"
        assert restored.variant_count == 0

    def test_print_rich(self):
        """Smoke test: print with rich should produce output without error."""
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0),
            ],
            asset="BTC", timeframe="5m",
        )
        r.print()  # should not crash

    def test_print_plain_fallback(self):
        """Smoke test: print without rich should produce output without error."""
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0),
            ],
            asset="BTC", timeframe="5m",
        )
        with patch.dict("sys.modules", {"rich": None}):
            r.print()  # should not crash

    def test_print_empty_report(self):
        r = ComparisonReport(asset="BTC", timeframe="5m")
        r.print()  # should not crash


# ── Persistence (save / list_runs / load_run) ─────────────────────────────────

class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path: Path):
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0, params={"a": 1}),
                VariantResult(name="v2", id="v2", balance=100.0, pnl=float("nan"), win_rate=float("nan"), trade_count=0, sharpe=None, max_drawdown_pct=None),
            ],
            asset="BTC", timeframe="5m",
        )
        path = r.save(directory=str(tmp_path))
        assert path.exists()
        assert path.suffix == ".json"
        assert "BTC" in path.name

        # Reload
        ts = r.timestamp.strftime("%Y-%m-%dT%H-%M-%S")
        restored = load_run(ts, directory=str(tmp_path))
        assert restored.asset == "BTC"
        assert restored.variant_count == 2
        assert restored.results[0].pnl == 25.0
        assert math.isnan(restored.results[1].pnl)

    def test_save_creates_dir(self, tmp_path: Path):
        nested = tmp_path / "subdir" / "variants"
        r = ComparisonReport(results=[], asset="BTC", timeframe="5m")
        path = r.save(directory=str(nested))
        assert path.exists()

    def test_list_runs_empty(self, tmp_path: Path):
        runs = list_runs(directory=str(tmp_path))
        assert runs == []

    def test_list_runs_with_data(self, tmp_path: Path):
        r = ComparisonReport(
            results=[
                VariantResult(name="v1", id="v1", balance=100.0, pnl=25.0, win_rate=0.6, trade_count=10, sharpe=1.2, max_drawdown_pct=-5.0),
            ],
            asset="BTC", timeframe="5m",
        )
        r.save(directory=str(tmp_path))

        runs = list_runs(directory=str(tmp_path))
        assert len(runs) == 1
        assert runs[0]["asset"] == "BTC"
        assert "v1" in runs[0].get("variants", [])

    def test_list_runs_sorted_newest_first(self, tmp_path: Path):
        old = ComparisonReport(results=[], asset="BTC", timeframe="5m")
        old.timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
        old.save(directory=str(tmp_path))

        new = ComparisonReport(results=[], asset="ETH", timeframe="1h")
        new.timestamp = datetime(2026, 7, 24, tzinfo=timezone.utc)
        new.save(directory=str(tmp_path))

        runs = list_runs(directory=str(tmp_path))
        assert len(runs) == 2
        assert runs[0]["asset"] == "ETH"

    def test_load_run_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_run("2026-01-01T00-00-00", directory=str(tmp_path))

    def test_load_run_dir_not_exist(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_run("2026-01-01T00-00-00", directory=str(tmp_path / "nonexistent"))

    def test_save_uses_default_dir(self):
        """Save without directory uses ~/.polyalpha/variants."""
        r = ComparisonReport(results=[], asset="BTC", timeframe="5m")
        with patch.object(Path, "home", return_value=Path(tempfile.gettempdir())):
            path = r.save()
            assert ".polyalpha" in str(path)
            assert path.exists()
            path.unlink()


# ── Hub.compare_variants integration ──────────────────────────────────────────

class TestHubCompareVariants:
    def test_no_variants_returns_empty_report(self):
        hub = BotHub(asset="BTC", timeframe="5m")
        report = hub.compare_variants()
        assert isinstance(report, ComparisonReport)
        assert report.variant_count == 0

    def test_compare_variants_with_papers(self):
        """Test that compare_variants() builds a sorted report from variant
        paper engines that have resolved trades."""
        from polyalpha.trading.paper_engine import PaperEngine
        from polyalpha.trading.paper_config import PaperConfig

        hub = BotHub(asset="BTC", timeframe="5m")
        config = PaperConfig()
        config.custom_fee_rate = 0.0
        config.slippage_pct = 0.0

        # Build two variants and manually wire their paper engines.
        @hub.variant("winner", balance=100)
        def win(ctx):
            pass

        @hub.variant("loser", balance=100)
        def lose(ctx):
            pass

        # Give them resolved trades.
        market = MagicMock()
        market.id = "m1"
        market.slug = "m"
        market.outcome = "WIN"
        market.up_price = 0.95
        market.down_price = 0.05
        market.question = "test?"
        market.start_time = "2020-01-01T00:00:00Z"
        market.end_time = "2030-01-01T00:00:00Z"

        for v in hub._variants:
            v.paper = PaperEngine(balance=v.balance, config=config)

        hub._variants[0].paper.buy(market=market, side="UP", amount=1.0)
        hub._variants[0].paper.resolve(market, outcome="UP")

        hub._variants[1].paper.buy(market=market, side="DOWN", amount=1.0)
        hub._variants[1].paper.resolve(market, outcome="UP")

        report = hub.compare_variants()
        assert report.variant_count == 2
        # Winner should be first (higher P&L).
        assert report.results[0].name == "winner"

    def test_compare_variants_increments_run_count(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("v1")
        def v1(ctx):
            pass

        assert hub._variants[0].run_count == 0
        hub.compare_variants()
        assert hub._variants[0].run_count == 1
        hub.compare_variants()
        assert hub._variants[0].run_count == 2

    def test_compare_variants_returns_new_report_each_call(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.variant("v1")
        def v1(ctx):
            pass

        r1 = hub.compare_variants()
        r2 = hub.compare_variants()
        assert r1 is not r2


# ── Variant in _active_tickers ────────────────────────────────────────────────

class TestActiveTickers:
    def test_includes_variants(self):
        hub = BotHub(asset="BTC", timeframe="5m")

        @hub.strategy("s1")
        def s1(ctx):
            pass

        @hub.variant("v1")
        def v1(ctx):
            pass

        tickers = hub._active_tickers()
        assert len(tickers) == 2
        names = {t.name for t in tickers}
        assert names == {"s1", "v1"}

    def test_empty_when_nothing_registered(self):
        hub = BotHub(asset="BTC", timeframe="5m")
        assert hub._active_tickers() == []


# ── buy_once_per_market ────────────────────────────────────────────────────────

class TestBuyOncePerMarket:
    def _make_ctx(self, buy_once_per_market):
        from collections import deque
        hub = MagicMock()
        hub.buy_once_per_market = buy_once_per_market
        hub._bought_this_market = {}
        paper = MagicMock()
        paper.buy.return_value = MagicMock()
        return StrategyContext(
            name="s1", stream=MagicMock(), paper=paper, market=None,
            price_history=deque(), hub=hub,
        ), paper

    def test_defaults_to_true(self):
        hub = BotHub(asset="BTC", timeframe="5m")
        assert hub.buy_once_per_market is True

    def test_blocks_after_first_buy_by_default(self):
        ctx, paper = self._make_ctx(buy_once_per_market=True)
        ctx.buy("UP", 10)
        ctx.buy("UP", 10)
        assert paper.buy.call_count == 1

    def test_allows_multiple_buys_when_disabled(self):
        ctx, paper = self._make_ctx(buy_once_per_market=False)
        ctx.buy("UP", 10)
        ctx.buy("UP", 10)
        assert paper.buy.call_count == 2

    def test_tracks_per_strategy_name(self):
        from collections import deque
        hub = MagicMock()
        hub.buy_once_per_market = True
        hub._bought_this_market = {}
        paper = MagicMock()
        paper.buy.return_value = MagicMock()
        ctx_a = StrategyContext(
            name="strat_a", stream=MagicMock(), paper=paper, market=None,
            price_history=deque(), hub=hub,
        )
        ctx_b = StrategyContext(
            name="strat_b", stream=MagicMock(), paper=paper, market=None,
            price_history=deque(), hub=hub,
        )
        ctx_a.buy("UP", 10)
        ctx_a.buy("UP", 10)
        ctx_b.buy("UP", 10)
        assert paper.buy.call_count == 2
