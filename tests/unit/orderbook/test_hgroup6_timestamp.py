"""
Orderbook hgroup6 finding #33 — malformed ISO timestamp must not silently
become "now".

Run with: pytest tests/unit/orderbook/test_hgroup6_timestamp.py
"""

from datetime import datetime, timezone

import pytest

from polyalpha.orderbook.models import OrderBookSnapshot


def _response(timestamp):
    return {
        "market": "0xcondition",
        "asset_id": "tok_up",
        "timestamp": timestamp,
        "bids": [{"price": "0.48", "size": "1000"}],
        "asks": [{"price": "0.52", "size": "800"}],
    }


@pytest.mark.unit
def test_valid_iso_timestamp_parsed():
    book = OrderBookSnapshot.from_clob_response(_response("2024-01-01T12:00:00Z"))
    assert book.timestamp == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_numeric_timestamp_parsed():
    book = OrderBookSnapshot.from_clob_response(_response(1704110400))
    assert book.timestamp == datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_missing_timestamp_falls_back_to_now():
    before = datetime.now(timezone.utc).timestamp()
    book = OrderBookSnapshot.from_clob_response(_response(None))
    after = datetime.now(timezone.utc).timestamp()
    assert before <= book.timestamp.timestamp() <= after


@pytest.mark.unit
def test_malformed_string_timestamp_raises():
    """hgroup6 #33 — a present-but-malformed timestamp must not silently be 'now'."""
    with pytest.raises(ValueError, match="invalid ISO timestamp"):
        OrderBookSnapshot.from_clob_response(_response("not-a-timestamp"))
