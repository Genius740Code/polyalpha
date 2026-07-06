"""
Test script for advanced database querying features.

Tests the new load_trades() and aggregate_trades() methods
to ensure they work correctly and efficiently.
"""

from datetime import datetime, timezone
import polyalpha
from polyalpha.database import TradeDatabase

def test_advanced_queries():
    print("=" * 60)
    print("TESTING ADVANCED DATABASE QUERYING")
    print("=" * 60)
    
    # Create a fresh database
    db = TradeDatabase("test_advanced.db")
    db.clear_all_trades()
    
    # Insert test data
    print("\n1. Inserting test trades...")
    test_trades = [
        ("btc-updown-5m-001", "BTC", "UP", 0.92, 10.0, 10.5, 0.2, "WON", 5.0),
        ("btc-updown-5m-002", "BTC", "DOWN", 0.88, 15.0, 16.5, 0.3, "LOST", -3.0),
        ("eth-updown-15m-001", "ETH", "UP", 0.95, 20.0, 20.8, 0.4, "WON", 8.0),
        ("eth-updown-15m-002", "ETH", "DOWN", 0.85, 25.0, 27.5, 0.5, "WON", 10.0),
        ("sol-updown-1h-001", "SOL", "UP", 0.90, 30.0, 32.0, 0.6, "LOST", -5.0),
        ("btc-updown-5m-003", "BTC", "UP", 0.93, 12.0, 12.5, 0.24, "WON", 6.0),
        ("eth-updown-15m-003", "ETH", "DOWN", 0.87, 18.0, 19.5, 0.36, "LOST", -2.0),
    ]
    
    for slug, asset, side, price, amount, shares, fee, outcome, pnl in test_trades:
        db.save_trade(
            market_slug=slug,
            market_id=f"market-{slug}",
            side=side,
            entry_price=price,
            exit_price=None,
            amount=amount,
            shares=shares,
            fee=fee,
            outcome=outcome,
            pnl=pnl,
            timestamp=datetime.now(timezone.utc),
        )
    
    print(f"   Inserted {len(test_trades)} test trades")
    
    # Test 2: Complex filters
    print("\n2. Testing complex filters...")
    
    # Filter by asset
    btc_trades = db.load_trades(filters={"asset": "BTC"})
    print(f"   BTC trades: {len(btc_trades)}")
    assert len(btc_trades) == 3, f"Expected 3 BTC trades, got {len(btc_trades)}"
    
    # Filter by asset and side
    btc_up_trades = db.load_trades(filters={"asset": "BTC", "side": "UP"})
    print(f"   BTC UP trades: {len(btc_up_trades)}")
    assert len(btc_up_trades) == 2, f"Expected 2 BTC UP trades, got {len(btc_up_trades)}"
    
    # Filter by outcome
    won_trades = db.load_trades(filters={"outcome": "WON"})
    print(f"   Winning trades: {len(won_trades)}")
    assert len(won_trades) == 4, f"Expected 4 winning trades, got {len(won_trades)}"
    
    # Filter by P&L range
    profitable_trades = db.load_trades(filters={"min_pnl": 0.0})
    print(f"   Profitable trades (P&L >= 0): {len(profitable_trades)}")
    assert len(profitable_trades) == 4, f"Expected 4 profitable trades, got {len(profitable_trades)}"
    
    # Filter by amount range
    large_trades = db.load_trades(filters={"min_amount": 20.0})
    print(f"   Large trades (amount >= 20): {len(large_trades)}")
    assert len(large_trades) == 3, f"Expected 3 large trades, got {len(large_trades)}"
    
    # Complex filter: asset + outcome + P&L
    complex_filter = db.load_trades(filters={"asset": "BTC", "outcome": "WON", "min_pnl": 5.0})
    print(f"   BTC winning trades with P&L >= 5: {len(complex_filter)}")
    assert len(complex_filter) == 2, f"Expected 2 trades, got {len(complex_filter)}"
    
    print("   ✓ All filter tests passed")
    
    # Test 3: Sorting
    print("\n3. Testing sorting...")
    
    # Sort by P&L descending
    sorted_by_pnl = db.load_trades(sort_by="pnl", sort_order="desc")
    print(f"   Trades sorted by P&L (desc): {sorted_by_pnl[0].pnl:.2f} (highest)")
    assert sorted_by_pnl[0].pnl == 10.0, f"Expected highest P&L to be 10.0, got {sorted_by_pnl[0].pnl}"
    
    # Sort by amount ascending
    sorted_by_amount = db.load_trades(sort_by="amount", sort_order="asc")
    print(f"   Trades sorted by amount (asc): {sorted_by_amount[0].amount:.2f} (lowest)")
    assert sorted_by_amount[0].amount == 10.0, f"Expected lowest amount to be 10.0, got {sorted_by_amount[0].amount}"
    
    # Sort by timestamp (default)
    sorted_by_time = db.load_trades(sort_by="timestamp", sort_order="desc")
    print(f"   Trades sorted by timestamp (desc): {len(sorted_by_time)} trades")
    
    print("   ✓ All sorting tests passed")
    
    # Test 4: Pagination
    print("\n4. Testing pagination...")
    
    # Limit
    limited_trades = db.load_trades(limit=3)
    print(f"   First 3 trades: {len(limited_trades)}")
    assert len(limited_trades) == 3, f"Expected 3 trades, got {len(limited_trades)}"
    
    # Offset
    offset_trades = db.load_trades(limit=3, offset=2)
    print(f"   Trades 3-5 (offset=2, limit=3): {len(offset_trades)}")
    assert len(offset_trades) == 3, f"Expected 3 trades, got {len(offset_trades)}"
    
    # Combined with filters
    filtered_limited = db.load_trades(filters={"asset": "BTC"}, limit=2)
    print(f"   BTC trades (limit=2): {len(filtered_limited)}")
    assert len(filtered_limited) == 2, f"Expected 2 BTC trades, got {len(filtered_limited)}"
    
    print("   ✓ All pagination tests passed")
    
    # Test 5: Aggregation
    print("\n5. Testing aggregation...")
    
    # Group by asset
    by_asset = db.aggregate_trades(group_by="asset")
    print(f"   Groups by asset: {list(by_asset.keys())}")
    assert "BTC" in by_asset, "Expected BTC in asset groups"
    assert by_asset["BTC"]["count"] == 3, f"Expected 3 BTC trades, got {by_asset['BTC']['count']}"
    assert abs(by_asset["BTC"]["total_pnl"] - 8.0) < 0.01, f"Expected BTC total P&L 8.0, got {by_asset['BTC']['total_pnl']}"
    
    # Group by side
    by_side = db.aggregate_trades(group_by="side")
    print(f"   Groups by side: {list(by_side.keys())}")
    assert "UP" in by_side, "Expected UP in side groups"
    assert by_side["UP"]["count"] == 4, f"Expected 4 UP trades, got {by_side['UP']['count']}"
    
    # Group by outcome
    by_outcome = db.aggregate_trades(group_by="outcome")
    print(f"   Groups by outcome: {list(by_outcome.keys())}")
    assert "WON" in by_outcome, "Expected WON in outcome groups"
    assert by_outcome["WON"]["count"] == 4, f"Expected 4 winning trades, got {by_outcome['WON']['count']}"
    
    # Aggregation with filters
    by_asset_filtered = db.aggregate_trades(group_by="asset", filters={"outcome": "WON"})
    print(f"   Asset groups (winning only): {list(by_asset_filtered.keys())}")
    assert by_asset_filtered["BTC"]["count"] == 2, f"Expected 2 winning BTC trades, got {by_asset_filtered['BTC']['count']}"
    
    print("   ✓ All aggregation tests passed")
    
    # Test 6: Error handling
    print("\n6. Testing error handling...")
    
    # Invalid sort field
    try:
        db.load_trades(sort_by="invalid_field")
        assert False, "Should have raised ValueError for invalid sort field"
    except ValueError as e:
        print(f"   ✓ Invalid sort field error: {e}")
    
    # Invalid sort order
    try:
        db.load_trades(sort_order="invalid")
        assert False, "Should have raised ValueError for invalid sort order"
    except ValueError as e:
        print(f"   ✓ Invalid sort order error: {e}")
    
    # Invalid limit
    try:
        db.load_trades(limit=-1)
        assert False, "Should have raised ValueError for invalid limit"
    except ValueError as e:
        print(f"   ✓ Invalid limit error: {e}")
    
    # Invalid group_by
    try:
        db.aggregate_trades(group_by="invalid")
        assert False, "Should have raised ValueError for invalid group_by"
    except ValueError as e:
        print(f"   ✓ Invalid group_by error: {e}")
    
    print("   ✓ All error handling tests passed")
    
    # Test 7: Performance
    print("\n7. Testing performance...")
    import time
    
    # Bulk insert performance
    start = time.time()
    for i in range(100):
        db.save_trade(
            market_slug=f"test-market-{i}",
            market_id=f"test-id-{i}",
            side="UP" if i % 2 == 0 else "DOWN",
            entry_price=0.9 + (i % 10) * 0.01,
            exit_price=None,
            amount=10.0 + i,
            shares=10.5 + i,
            fee=0.2 + i * 0.01,
            outcome="WON" if i % 3 == 0 else "LOST",
            pnl=5.0 if i % 3 == 0 else -2.0,
            timestamp=datetime.now(timezone.utc),
        )
    insert_time = time.time() - start
    print(f"   Inserted 100 trades in {insert_time:.3f}s")
    
    # Query performance
    start = time.time()
    all_trades = db.load_all_trades()
    query_time = time.time() - start
    print(f"   Loaded {len(all_trades)} trades in {query_time:.3f}s")
    
    # Filtered query performance
    start = time.time()
    filtered = db.load_trades(filters={"asset": "test", "outcome": "WON"})
    filtered_time = time.time() - start
    print(f"   Filtered query returned {len(filtered)} trades in {filtered_time:.3f}s")
    
    # Aggregation performance
    start = time.time()
    aggregated = db.aggregate_trades(group_by="side")
    agg_time = time.time() - start
    print(f"   Aggregated trades in {agg_time:.3f}s")
    
    print("   ✓ Performance tests completed")
    
    # Cleanup
    print("\n8. Cleanup...")
    db.clear_all_trades()
    db.close()
    print("   Database cleared and closed")
    
    # Remove test file
    import os
    if os.path.exists("test_advanced.db"):
        os.remove("test_advanced.db")
        print("   Test database file removed")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY")
    print("=" * 60)

if __name__ == "__main__":
    test_advanced_queries()
