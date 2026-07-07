"""
Order book analytics — depth, imbalance, fill simulation, liquidity metrics.
"""

from __future__ import annotations

from typing import Any

from ..core.constants import PRICE_ROUNDING
from .models import BookLevel, BookSide, FillEstimate, OrderBookSnapshot


def cumulative_depth(
    levels: tuple[BookLevel, ...],
    side: BookSide,
) -> list[dict[str, float]]:
    """Return cumulative size and notional at each price level."""
    rows: list[dict[str, float]] = []
    cumulative_size = 0.0
    cumulative_notional = 0.0
    for level in levels:
        cumulative_size += level.size
        cumulative_notional += level.notional
        rows.append(
            {
                "price": level.price,
                "size": level.size,
                "cumulative_size": cumulative_size,
                "cumulative_notional": cumulative_notional,
            }
        )
    return rows


def estimate_fill(
    book: OrderBookSnapshot,
    side: BookSide,
    size: float,
) -> FillEstimate:
    """
    Walk the book to estimate average fill price for *size* shares.

    BUY orders consume asks; SELL orders consume bids.
    """
    if size <= 0:
        return FillEstimate(
            side=side,
            requested_size=size,
            filled_size=0.0,
            average_price=0.0,
            total_cost=0.0,
            levels_used=(),
            fully_filled=False,
        )

    levels = book.asks if side == BookSide.BUY else book.bids
    remaining = size
    total_cost = 0.0
    filled = 0.0
    used: list[tuple[float, float]] = []

    for level in levels:
        if remaining <= 0:
            break
        take = min(remaining, level.size)
        total_cost += take * level.price
        filled += take
        used.append((level.price, take))
        remaining -= take

    avg_price = total_cost / filled if filled > 0 else 0.0
    return FillEstimate(
        side=side,
        requested_size=size,
        filled_size=filled,
        average_price=round(avg_price, PRICE_ROUNDING),
        total_cost=round(total_cost, PRICE_ROUNDING),
        levels_used=tuple(used),
        fully_filled=remaining <= 0,
    )


def estimate_market_buy_usdc(book: OrderBookSnapshot, usdc_amount: float) -> FillEstimate:
    """Estimate shares received when spending *usdc_amount* buying at ask levels."""
    if usdc_amount <= 0:
        return FillEstimate(
            side=BookSide.BUY,
            requested_size=0.0,
            filled_size=0.0,
            average_price=0.0,
            total_cost=0.0,
            levels_used=(),
            fully_filled=False,
        )

    remaining_usdc = usdc_amount
    total_shares = 0.0
    used: list[tuple[float, float]] = []

    for level in book.asks:
        if remaining_usdc <= 0:
            break
        level_notional = level.price * level.size
        if remaining_usdc >= level_notional:
            total_shares += level.size
            used.append((level.price, level.size))
            remaining_usdc -= level_notional
        else:
            shares = remaining_usdc / level.price
            total_shares += shares
            used.append((level.price, shares))
            remaining_usdc = 0.0

    spent = usdc_amount - remaining_usdc
    avg_price = spent / total_shares if total_shares > 0 else 0.0
    return FillEstimate(
        side=BookSide.BUY,
        requested_size=usdc_amount,
        filled_size=round(total_shares, PRICE_ROUNDING),
        average_price=round(avg_price, PRICE_ROUNDING),
        total_cost=round(spent, PRICE_ROUNDING),
        levels_used=tuple(used),
        fully_filled=remaining_usdc <= 0,
    )


def liquidity_at_price(
    book: OrderBookSnapshot,
    price: float,
    side: BookSide,
    tolerance: float | None = None,
) -> float:
    """Return total size within *tolerance* of *price* on the given side."""
    tol = tolerance if tolerance is not None else book.tick_size
    levels = book.bids if side == BookSide.SELL else book.asks
    return sum(level.size for level in levels if abs(level.price - price) <= tol)


def support_resistance_levels(
    book: OrderBookSnapshot,
    levels: int = 5,
) -> dict[str, list[float]]:
    """Identify top liquidity clusters as crude support/resistance."""
    bid_prices = sorted(
        (level.price for level in book.bids[:levels]),
        reverse=True,
    )
    ask_prices = sorted(level.price for level in book.asks[:levels])
    return {"support": bid_prices, "resistance": ask_prices}


def volatility_from_spread(book: OrderBookSnapshot) -> float:
    """Simple volatility proxy: spread relative to mid price."""
    mid = book.mid_price
    if mid <= 0:
        return 0.0
    return book.spread / mid


def book_summary(book: OrderBookSnapshot) -> dict[str, Any]:
    """Compact analytics dict for logging or strategy input."""
    return {
        "token_id": book.token_id,
        "best_bid": book.best_bid,
        "best_ask": book.best_ask,
        "spread": book.spread,
        "mid_price": book.mid_price,
        "imbalance": book.order_book_imbalance,
        "bid_volume": book.total_bid_volume,
        "ask_volume": book.total_ask_volume,
        "levels": len(book.bids) + len(book.asks),
        "timestamp": book.timestamp.isoformat(),
    }
