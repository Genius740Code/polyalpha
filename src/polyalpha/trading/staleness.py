"""Shared staleness / price helpers for paper and real engines."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..core import FALLBACK_PRICE, PRICE_STALENESS_THRESHOLD

log = logging.getLogger(__name__)


def get_price_for_side(
    market,
    side: str,
    attached_streams: dict,
    log_prefix: str = "Real",
) -> tuple[float, str]:
    """
    Get best available price for a side, preferring live stream prices.

    Returns (price, source) where source is "stream"/"market"/"fallback".
    """
    stream = attached_streams.get(market.id)
    if stream is not None and getattr(stream, "running", False):
        price = stream.up if side == "UP" else stream.down
        if price and price > 0:
            log.debug("%s: using live stream price %.4f for %s %s", log_prefix, price, getattr(market, "slug", market.id), side)
            return price, "stream"
        log.warning("%s: stream attached but price is 0, falling back to market price", log_prefix)

    price = market.up_price if side == "UP" else market.down_price

    if hasattr(market, "end_time") and market.end_time:
        try:
            end_time = datetime.fromisoformat(str(market.end_time).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            time_until_close = (end_time - now).total_seconds()
            if time_until_close <= 0:
                log.warning("%s: market %s is closed, price may be stale", log_prefix, getattr(market, "slug", market.id))
            elif time_until_close < PRICE_STALENESS_THRESHOLD:
                log.warning(
                    "%s: market %s closes in %.1fs, using potentially stale price %.4f",
                    log_prefix, getattr(market, "slug", market.id), time_until_close, price,
                )
        except (ValueError, TypeError):
            pass

    if price is None or price <= 0:
        log.warning("%s: market price is invalid (%.4f), using fallback", log_prefix, price or 0)
        return FALLBACK_PRICE, "fallback"

    log.debug("%s: using market price %.4f for %s %s", log_prefix, price, getattr(market, "slug", market.id), side)
    return price, "market"
