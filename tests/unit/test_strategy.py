from unittest.mock import MagicMock

import pytest

from polyalpha.strategy import (
    ConfigurableStrategy,
    Signal,
    SignalResult,
    Strategy,
    StrategySuite,
)


class FakeBinance:
    def vol_ratio(self, period=10):
        return 2.0


class FakeCLWindow:
    _value = 100.0
    _prices = [(100.0, 0), (101.0, 1)]

    @property
    def value(self):
        return self._value

    def change_pct(self, seconds=30):
        return 1.0

    @property
    def age_s(self):
        return 5.0


class FakeContext:
    def __init__(self, balance=100.0):
        self._balance = balance
        self.price = MagicMock()
        self.price.up = 0.75
        self.price.down = 0.25
        self.cl = FakeCLWindow()
        self.binance = FakeBinance()
        self._buy_result = MagicMock(status="filled")

    @property
    def balance(self):
        return self._balance

    def buy(self, side, amount):
        return self._buy_result


class TestSignal:
    def test_signal_creation(self):
        sig = Signal("UP")
        assert sig.side == "UP"

    def test_signal_result_defaults(self):
        res = SignalResult("UP")
        assert res.side == "UP"
        assert res.amount_pct is None
        assert res.limit_price is None

    def test_signal_result_full(self):
        res = SignalResult("UP", 50.0, 0.75)
        assert res.side == "UP"
        assert res.amount_pct == 50.0
        assert res.limit_price == 0.75


class TestStrategyBase:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            Strategy()

    def test_concrete_strategy(self):
        class MyStrat(Strategy):
            name = "test"
            cl_threshold_pct = 0.1
            order_size_pct = 20

            def signal(self, ctx):
                return Signal("UP")

        s = MyStrat()
        assert s.name == "test"
        assert s.cl_threshold_pct == 0.1
        assert s.order_size_pct == 20
        assert s.check_cooldown()

    def test_signal_returns_signal(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        ctx = FakeContext()
        result = MyStrat().signal(ctx)
        assert result is not None
        assert result.side == "UP"

    def test_signal_no_signal(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return None

        result = MyStrat().signal(FakeContext())
        assert result is None

    def test_lifecycle_hooks_defaults(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return None

        s = MyStrat()
        s.on_start()
        s.on_entry("UP", 0.75)
        s.on_resolve(MagicMock(side="UP", outcome="win", pnl=1.0))
        s.on_stop()

    def test_check_cooldown_blocks(self):
        class MyStrat(Strategy):
            name = "test"
            cooldown_s = 300

            def signal(self, ctx):
                return None

        s = MyStrat()
        s._last_trade_time = 0.0
        assert s.check_cooldown()

    def test_check_volume_disabled(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return None

        ctx = FakeContext()
        assert MyStrat().check_volume(ctx) is True

    def test_check_volume_enabled(self):
        class MyStrat(Strategy):
            name = "test"
            vol_multiplier = 1.0

            def signal(self, ctx):
                return None

        ctx = FakeContext()
        assert MyStrat().check_volume(ctx) is True

    def test_check_price_zone(self):
        class MyStrat(Strategy):
            name = "test"
            fav_min = 0.0
            fav_max = 1.0

            def signal(self, ctx):
                return None

        ctx = FakeContext()
        ctx.price.up = 0.65
        assert MyStrat().check_price_zone(ctx, "UP") is True

    def test_should_skip_guards(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return None

        s = MyStrat()
        assert s.should_skip(FakeContext()) is None

    def test_repr(self):
        class MyStrat(Strategy):
            name = "my_test"
            order_size_pct = 20

            def signal(self, ctx):
                return None

        r = repr(MyStrat())
        assert "my_test" in r
        assert "order_size=20%" in r


class TestConfigurableStrategy:
    def test_from_config(self):
        s = ConfigurableStrategy.from_config(
            "B1",
            side="UP",
            cl_threshold_pct=0.12,
            fav_min=0.5,
            fav_max=0.75,
        )
        assert s.name == "B1"
        assert s.side == "UP"
        assert s.cl_threshold_pct == 0.12
        assert s.fav_min == 0.5
        assert s.fav_max == 0.75

    def test_auto_signal_up(self):
        s = ConfigurableStrategy("B1", side="UP")
        ctx = FakeContext()
        ctx.cl = MagicMock()
        ctx.cl.change_pct.return_value = 0.15
        result = s.signal(ctx)
        assert result is not None
        assert result.side == "UP"

    def test_auto_signal_down(self):
        s = ConfigurableStrategy("B1", side="DOWN")
        ctx = FakeContext()
        ctx.cl = MagicMock()
        ctx.cl.change_pct.return_value = -0.15
        result = s.signal(ctx)
        assert result is not None
        assert result.side == "DOWN"

    def test_auto_signal_none_below_threshold(self):
        s = ConfigurableStrategy("B1", side="UP", cl_threshold_pct=0.1)
        ctx = FakeContext()
        ctx.cl = MagicMock()
        ctx.cl.change_pct.return_value = 0.05
        assert s.signal(ctx) is None

    def test_auto_signal_auto_side(self):
        s = ConfigurableStrategy("B1", side=None)
        ctx = FakeContext()
        ctx.cl = MagicMock()
        ctx.cl.change_pct.return_value = 0.15
        result = s.signal(ctx)
        assert result is not None
        assert result.side == "UP"
        ctx.cl.change_pct.return_value = -0.15
        result = s.signal(ctx)
        assert result is not None
        assert result.side == "DOWN"


class TestStrategySuite:
    def test_add_strategy(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m")
        suite.add(MyStrat())
        assert "test" in suite.strategies

    def test_add_duplicate_raises(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m")
        suite.add(MyStrat())
        with pytest.raises(ValueError):
            suite.add(MyStrat())

    def test_run_no_strategies_raises(self):
        suite = StrategySuite("BTC", "5m")
        with pytest.raises(RuntimeError, match="No strategies registered"):
            suite.run()

    def test_extract_params(self):
        class MyStrat(Strategy):
            name = "test"
            cl_window_s = 30
            cl_threshold_pct = 0.08
            fav_min = 0.5
            fav_max = 0.75
            vol_multiplier = 1.5
            order_size_pct = 25
            cooldown_s = 60
            side = "UP"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m")
        s = MyStrat()
        params = suite._extract_params(s)
        assert params == {
            "cl_window_s": 30,
            "cl_threshold_pct": 0.08,
            "fav_min": 0.5,
            "fav_max": 0.75,
            "vol_multiplier": 1.5,
            "order_size_pct": 25,
            "cooldown_s": 60,
            "side": "UP",
        }

    def test_make_tick_handler_executes_signal(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m", balance=1000.0)
        s = MyStrat()
        handler = suite._make_tick_handler(s)
        handler(FakeContext())
        assert s._total_trades == 1

    def test_make_tick_handler_no_signal(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return None

        suite = StrategySuite("BTC", "5m")
        s = MyStrat()
        handler = suite._make_tick_handler(s)
        handler(FakeContext())
        assert s._total_trades == 0

    def test_add_returns_strategy(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m")
        s = MyStrat()
        result = suite.add(s)
        assert result is s

    def test_stats_structure(self):
        class MyStrat(Strategy):
            name = "test"

            def signal(self, ctx):
                return Signal("UP")

        suite = StrategySuite("BTC", "5m", balance=500)
        suite.add(MyStrat())
        stats = suite.stats
        assert "strategies" in stats
        assert "test" in stats["strategies"]
