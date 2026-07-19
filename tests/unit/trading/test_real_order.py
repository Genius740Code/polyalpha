"""
Real trading order tests — run with: pytest tests/unit/trading/test_real_order.py
"""

import pytest
from datetime import datetime, timezone
from polyalpha.trading.real import RealOrder


@pytest.mark.unit
def test_real_order_dump():
    """Test order dump functionality."""
    order = RealOrder(
        id="test-id",
        market_id="market-1",
        slug="test-market",
        side="UP",
        price=0.55,
        amount=10.0,
        shares=18.0,
        fee=0.20,
        status="filled",
        is_limit=False,
        created_at=datetime.now(timezone.utc),
    )

    dump = order.dump()
    assert dump["id"] == "test-id"
    assert dump["side"] == "UP"
    assert dump["status"] == "filled"
    assert dump["is_limit"] == False
    assert "created_at" in dump
