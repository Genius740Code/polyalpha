"""
BotHub refactor smoke tests — verifies the split from monolithic
``src/polyalpha/bot_hub.py`` (2662 lines) into the ``src/polyalpha/bot_hub/``
package (7 modules) preserves backward compat and exposes new submodule paths.

Run with:

    pytest tests/unit/bots/test_bot_hub_refactor.py -v
"""

import importlib
import pathlib

import pytest


def test_package_is_directory_not_file():
    """bot_hub must be a package (directory with __init__.py) after refactor."""
    import polyalpha.bot_hub as m

    path = pathlib.Path(m.__file__)
    assert path.name == "__init__.py"
    assert path.parent.name == "bot_hub"
    assert (path.parent / "hub.py").exists()
    assert (path.parent / "context.py").exists()
    assert (path.parent / "binance.py").exists()
    assert (path.parent / "indicators.py").exists()
    assert (path.parent / "orderbook.py").exists()
    assert (path.parent / "models.py").exists()
    assert (path.parent / "history.py").exists()


def test_legacy_top_level_imports():
    """Existing code `from polyalpha.bot_hub import X` must still work."""
    from polyalpha.bot_hub import (
        BBResult,
        BinanceAccessor,
        BotHub,
        DonchianResult,
        IndicatorAccessor,
        MACDResult,
        OrderBookAccessor,
        PriceSnapshot,
        StrategyContext,
        Variant,
        _RegisteredStrategy,
    )

    # Basic sanity — classes are importable and distinct.
    assert BotHub is not None
    assert StrategyContext is not None
    assert IndicatorAccessor is not None
    assert BinanceAccessor is not None
    assert OrderBookAccessor is not None
    assert PriceSnapshot is not None
    assert MACDResult is not None
    assert BBResult is not None
    assert DonchianResult is not None
    assert Variant is _RegisteredStrategy


def test_polyalpha_top_level_reexports():
    """`import polyalpha; polyalpha.BotHub` must still work (`src/polyalpha/__init__.py:148`)."""
    import polyalpha

    assert hasattr(polyalpha, "BotHub")
    assert hasattr(polyalpha, "IndicatorAccessor")
    assert hasattr(polyalpha, "BinanceAccessor")
    assert hasattr(polyalpha, "MACDResult")
    from polyalpha.bot_hub import BotHub as Hub2

    assert polyalpha.BotHub is Hub2


def test_submodule_direct_imports():
    """New preferred imports via submodules must work."""
    from polyalpha.bot_hub.binance import BinanceAccessor as BA2
    from polyalpha.bot_hub.context import StrategyContext as SC2
    from polyalpha.bot_hub.history import _resolve_chainlink_history
    from polyalpha.bot_hub.hub import BotHub as Hub
    from polyalpha.bot_hub.indicators import IndicatorAccessor as IA2
    from polyalpha.bot_hub.models import (
        BBResult as B2,
        DonchianResult as D2,
        MACDResult as M2,
        PriceSnapshot as PS2,
        _RegisteredStrategy as RS2,
    )
    from polyalpha.bot_hub.orderbook import OrderBookAccessor as OBA2

    assert Hub is not None
    assert SC2 is not None
    assert IA2 is not None
    assert BA2 is not None
    assert OBA2 is not None
    assert PS2 is not None
    assert M2 is not None
    assert B2 is not None
    assert D2 is not None
    assert RS2 is not None
    assert callable(_resolve_chainlink_history)


def test_no_monolithic_file_remains():
    """The old ``src/polyalpha/bot_hub.py`` file must not exist on disk."""
    # Package path
    import polyalpha.bot_hub as m

    pkg_dir = pathlib.Path(m.__file__).parent
    # Old file would be sibling to package directory, not inside it
    old_file = pkg_dir.parent / "bot_hub.py"
    assert not old_file.exists(), f"Old monolithic file still exists at {old_file}"


def test_hub_file_size_reasonable():
    """Each split file should be < 1300 lines (hub was 2662)."""
    import polyalpha.bot_hub as m

    pkg_dir = pathlib.Path(m.__file__).parent
    for name in ("hub.py", "context.py", "binance.py", "indicators.py", "orderbook.py", "models.py", "history.py"):
        lines = (pkg_dir / name).read_text().count("\n")
        assert lines < 1300, f"{name} too large: {lines} lines"
    # Hub itself should be roughly half the original
    hub_lines = (pkg_dir / "hub.py").read_text().count("\n")
    assert 900 < hub_lines < 1300, f"hub.py expected ~1100 lines, got {hub_lines}"


def test_downstream_imports_still_work():
    """Files that imported from polyalpha.bot_hub must not break."""
    # bot.py
    import polyalpha.bot as bot_mod

    assert hasattr(bot_mod, "Bot")
    # strategy
    from polyalpha.strategy.base import Strategy
    from polyalpha.strategy.suite import StrategySuite

    assert Strategy is not None
    assert StrategySuite is not None
    # report
    from polyalpha.report.comparison import ComparisonReport

    assert ComparisonReport is not None
    # calculations lazy import path
    from polyalpha.calculations.binance_accessor import BinanceAccessor as CalcBA

    assert CalcBA is not None
    # Ensure MACDResult import inside calculations works at runtime
    ba = CalcBA(asset="BTC", timeframe="5m")
    # macd() should not crash due to import
    assert hasattr(ba, "macd")


def test_bot_hub_reexport_completeness():
    """`from polyalpha.bot_hub import *` equivalent via __all__."""
    import polyalpha.bot_hub as m

    for name in m.__all__:  # type: ignore[attr-defined]
        assert hasattr(m, name), f"__all__ lists {name} but not exported"
