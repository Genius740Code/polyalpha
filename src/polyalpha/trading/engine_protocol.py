"""Trading engine protocol — unified interface for paper and real engines."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TradingEngineProtocol(Protocol):
    """Unified trading engine interface. Both PaperEngine and RealTradingEngine satisfy this."""

    @property
    def balance(self) -> float:  # pragma: no cover
        ...

    @property
    def config(self):  # pragma: no cover
        ...

    def buy(self, market, side: str, amount: float | None = None, **kwargs):  # pragma: no cover
        ...

    def limit(self, market, side: str, price: float, amount: float | None = None, **kwargs):  # pragma: no cover
        ...

    def cancel(self, order_id: str):  # pragma: no cover
        ...

    def get_order(self, order_id: str):  # pragma: no cover
        ...

    def open_orders(self) -> list:  # pragma: no cover
        ...

    def positions(self) -> list:  # pragma: no cover
        ...

    def all_positions(self) -> list:  # pragma: no cover
        ...

    def attach_stream(self, stream, market) -> None:  # pragma: no cover
        ...

    def pre_trade_checks(self, market, side: str, amount: float) -> dict:  # pragma: no cover
        ...

    def refresh_balance(self) -> None:  # pragma: no cover
        ...
