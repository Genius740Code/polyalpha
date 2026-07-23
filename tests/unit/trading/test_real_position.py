"""
Real trading position tests — run with: pytest tests/unit/trading/test_real_position.py
"""

import pytest
from polyalpha.trading.real_orders import RealPosition


@pytest.mark.unit
def test_real_position_pnl():
    """Test position P&L calculations."""
    position = RealPosition(
        market_id="test-id",
        slug="test-market",
        question="Test question",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.60,
        cost_basis=5.0,
        current_value=6.0,
    )

    assert position.pnl == 1.0
    assert position.pnl_pct == 20.0


@pytest.mark.unit
def test_real_position_dump():
    """Test position dump functionality."""
    position = RealPosition(
        market_id="test-id",
        slug="test-market",
        question="Test question",
        side="UP",
        shares=10.0,
        avg_price=0.50,
        current_price=0.60,
        cost_basis=5.0,
        current_value=6.0,
    )

    dump = position.dump()
    assert dump["market"] == "test-market"
    assert dump["side"] == "UP"
    assert dump["pnl"] == 1.0
    assert dump["pnl_pct"] == 20.0
