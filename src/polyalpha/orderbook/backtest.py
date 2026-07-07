"""
Backtesting engine for order book strategies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .analytics import estimate_fill
from .models import BookSide, MarketOrderBook, Order, OrderBookSnapshot, OrderType, Trade
from .strategy import Strategy


class BacktestEngine:
    """Replay historical order book snapshots against a strategy."""

    def __init__(self, strategy: Strategy, initial_capital: float = 100_000.0):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions: dict[str, float] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = []
        self.order_book_history: list[MarketOrderBook] = []

    async def load_snapshots(self, snapshots: list[MarketOrderBook]) -> None:
        self.order_book_history = list(snapshots)

    async def run_backtest(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        await self.strategy.start()

        for snapshot in self.order_book_history:
            ts = snapshot.up.timestamp if snapshot.up else None
            if ts is None and snapshot.down:
                ts = snapshot.down.timestamp
            if ts is None:
                continue
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date:
                continue

            signals = await self.strategy.on_order_book_update(snapshot)
            for signal in signals or []:
                await self._execute_order(signal, snapshot)
            self._update_equity(snapshot)

        await self.strategy.stop()
        return self._generate_report()

    async def _execute_order(self, order: Order, book: MarketOrderBook) -> None:
        side = getattr(self.strategy, "side", "UP")
        target = book.up if str(side).upper() == "UP" else book.down
        if target is None:
            target = book.up or book.down
        if target is None:
            return

        if order.order_type == OrderType.MARKET:
            fill = estimate_fill(target, order.side, order.quantity)
            execution_price = fill.average_price
            quantity = fill.filled_size
        else:
            execution_price = order.price
            quantity = order.quantity

        if quantity <= 0 or execution_price <= 0:
            return

        symbol = book.market_slug
        cost = execution_price * quantity

        if order.side == BookSide.BUY:
            self.positions[symbol] = self.positions.get(symbol, 0.0) + quantity
            self.current_capital -= cost
        else:
            self.positions[symbol] = self.positions.get(symbol, 0.0) - quantity
            self.current_capital += cost

        trade = Trade(
            id=f"backtest_{len(self.trades)}",
            order_id=order.id,
            price=execution_price,
            quantity=quantity,
            timestamp=target.timestamp,
            taker_order_id=order.id,
            maker_order_id="backtest",
        )
        self.trades.append(trade)
        await self.strategy.on_trade(trade)

    def _mid_for_book(self, book: MarketOrderBook) -> float:
        if book.up and book.up.mid_price > 0:
            return book.up.mid_price
        if book.down and book.down.mid_price > 0:
            return book.down.mid_price
        return 0.0

    def _update_equity(self, book: MarketOrderBook) -> None:
        mid = self._mid_for_book(book)
        position_value = sum(pos * mid for pos in self.positions.values())
        self.equity_curve.append(self.current_capital + position_value)

    def _generate_report(self) -> dict[str, Any]:
        if not self.equity_curve:
            return {}

        final_equity = self.equity_curve[-1]
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        returns: list[float] = []
        for index in range(1, len(self.equity_curve)):
            prev = self.equity_curve[index - 1]
            if prev > 0:
                returns.append((self.equity_curve[index] - prev) / prev)

        mean_return = sum(returns) / len(returns) if returns else 0.0
        if len(returns) > 1:
            variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
            std = variance ** 0.5
        else:
            std = 0.0

        sharpe = (mean_return / std * (252 ** 0.5)) if std > 0 else 0.0
        peak = self.equity_curve[0]
        max_drawdown = 0.0
        for value in self.equity_curve:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, peak - value)
        max_drawdown_pct = max_drawdown / self.initial_capital if self.initial_capital else 0.0

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown_pct,
            "total_trades": len(self.trades),
            "final_equity": final_equity,
            "equity_curve": list(self.equity_curve),
        }
