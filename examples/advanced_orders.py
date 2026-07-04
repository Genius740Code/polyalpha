"""
Advanced Order Management Examples

This example demonstrates the new advanced order management features:
- Stop-loss (SL) orders
- Take-profit (TP) orders  
- Trailing stop-loss
- Trailing take-profit
- One-Cancels-Other (OCO) orders
- Position selling/closing

Usage:
    python examples/advanced_orders.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import polyalpha
from polyalpha.trading.paper import PaperConfig


class MockMarket:
    """Mock market for demonstration purposes."""
    
    def __init__(self, market_id="btc-5m", slug="btc-updown-5m", question="Will BTC be higher in 5 minutes?"):
        self.id = market_id
        self.slug = slug
        self.question = question
        self.up_price = 0.50
        self.down_price = 0.50


def example_basic_stop_loss():
    """Example: Basic stop-loss order."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic Stop-Loss Order")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy with stop-loss
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        stop_loss=0.45
    )
    
    print(f"\n✅ Order filled:")
    print(f"   Side: {order.side}")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Shares: {order.shares:.2f}")
    print(f"   Stop-loss: ${order.stop_loss:.4f}")
    print(f"   Fee: ${order.fee:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Simulate price dropping to trigger SL
    print(f"\n📉 Price drops to $0.44 (below SL at ${order.stop_loss:.4f})")
    engine.check_limits(market.id, up_price=0.44, down_price=0.56)
    
    print(f"\n🛑 Stop-loss triggered!")
    print(f"   Triggered by: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_basic_take_profit():
    """Example: Basic take-profit order."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Basic Take-Profit Order")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy with take-profit
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        take_profit=0.55
    )
    
    print(f"\n✅ Order filled:")
    print(f"   Side: {order.side}")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Take-profit: ${order.take_profit:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Simulate price rising to trigger TP
    print(f"\n📈 Price rises to $0.56 (above TP at ${order.take_profit:.4f})")
    engine.check_limits(market.id, up_price=0.56, down_price=0.44)
    
    print(f"\n🎯 Take-profit triggered!")
    print(f"   Triggered by: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_both_tp_sl():
    """Example: Order with both TP and SL."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Order with Both TP and SL")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy with both TP and SL
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        stop_loss=0.45,
        take_profit=0.55
    )
    
    print(f"\n✅ Order filled:")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Stop-loss: ${order.stop_loss:.4f}")
    print(f"   Take-profit: ${order.take_profit:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Simulate price rising to trigger TP (before SL)
    print(f"\n📈 Price rises to $0.56")
    engine.check_limits(market.id, up_price=0.56, down_price=0.44)
    
    print(f"\n🎯 Take-profit triggered (SL cancelled automatically)")
    print(f"   Triggered by: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_trailing_stop_loss():
    """Example: Trailing stop-loss."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Trailing Stop-Loss")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy with trailing SL (5%)
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        trail_sl=0.05
    )
    
    print(f"\n✅ Order filled:")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Trailing SL distance: {order.trail_sl*100:.1f}%")
    print(f"   Initial SL price: ${order.trail_sl_price:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Price moves up - SL should trail up
    print(f"\n📈 Price moves up to $0.60")
    engine.check_limits(market.id, up_price=0.60, down_price=0.40)
    
    print(f"   New SL price: ${order.trail_sl_price:.4f} (moved up)")
    
    # Price moves back down but SL stays at high point
    print(f"\n📉 Price drops back to $0.50")
    engine.check_limits(market.id, up_price=0.50, down_price=0.50)
    
    print(f"   SL price: ${order.trail_sl_price:.4f} (stays at high point)")
    
    # Price drops to SL level
    print(f"\n📉 Price drops to $0.55 (at SL level)")
    engine.check_limits(market.id, up_price=0.55, down_price=0.45)
    
    print(f"   SL price: ${order.trail_sl_price:.4f}")
    print(f"   Triggered: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_trailing_take_profit():
    """Example: Trailing take-profit."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Trailing Take-Profit")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy with trailing TP (10%)
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        trail_tp=0.10
    )
    
    print(f"\n✅ Order filled:")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Trailing TP distance: {order.trail_tp*100:.1f}%")
    print(f"   Initial TP price: ${order.trail_tp_price:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Price moves up significantly - TP should trail up
    print(f"\n📈 Price moves up to $0.70")
    engine.check_limits(market.id, up_price=0.70, down_price=0.30)
    
    print(f"   New TP price: ${order.trail_tp_price:.4f} (moved up)")
    
    # Price continues up - TP continues trailing
    print(f"\n📈 Price continues to $0.80")
    engine.check_limits(market.id, up_price=0.80, down_price=0.20)
    
    print(f"   New TP price: ${order.trail_tp_price:.4f}")
    
    # Price drops to TP level
    print(f"\n📉 Price drops to $0.88 (at TP level)")
    engine.check_limits(market.id, up_price=0.88, down_price=0.12)
    
    print(f"   TP price: ${order.trail_tp_price:.4f}")
    print(f"   Triggered: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_oco_order():
    """Example: One-Cancels-Other (OCO) order."""
    print("\n" + "="*60)
    print("EXAMPLE 6: One-Cancels-Other (OCO) Order")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Create OCO order
    main_order, oco_order = engine.oco_order(
        market, side="UP", amount=100.0,
        stop_loss=0.45,
        take_profit=0.55
    )
    
    print(f"\n✅ OCO order created:")
    print(f"   Entry price: ${main_order.price:.4f}")
    print(f"   Stop-loss: ${main_order.stop_loss:.4f}")
    print(f"   Take-profit: ${main_order.take_profit:.4f}")
    print(f"   OCO linked: {main_order.oco_order_id[:8]}...")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Price rises to trigger TP
    print(f"\n📈 Price rises to $0.56 (triggers TP)")
    engine.check_limits(market.id, up_price=0.56, down_price=0.44)
    
    print(f"\n🎯 Take-profit triggered!")
    print(f"   Triggered by: {main_order.tp_sl_triggered_by}")
    print(f"   SL automatically cancelled")
    print(f"   Balance after: ${engine.balance:.2f}")


def example_sell_position():
    """Example: Selling/closing a position."""
    print("\n" + "="*60)
    print("EXAMPLE 7: Selling/Closing Position")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy a position
    buy_order = engine.buy(market, side="UP", amount=100.0)
    
    print(f"\n✅ Position opened:")
    print(f"   Entry price: ${buy_order.price:.4f}")
    print(f"   Shares: {buy_order.shares:.2f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Check positions
    positions = engine.positions()
    print(f"\n📊 Current positions: {len(positions)}")
    
    # Sell full position
    print(f"\n💰 Selling full position...")
    sell_order = engine.sell_position(market, side="UP")
    
    print(f"   Sell price: ${sell_order.price:.4f}")
    print(f"   Shares sold: {sell_order.shares:.2f}")
    print(f"   Fee: ${sell_order.fee:.4f}")
    print(f"   Balance after: ${engine.balance:.2f}")
    
    # Check positions again
    positions = engine.positions()
    print(f"\n📊 Current positions: {len(positions)} (should be 0)")


def example_partial_sell():
    """Example: Partial position sell."""
    print("\n" + "="*60)
    print("EXAMPLE 8: Partial Position Sell")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Buy a position
    buy_order = engine.buy(market, side="UP", amount=200.0)
    
    print(f"\n✅ Position opened:")
    print(f"   Entry price: ${buy_order.price:.4f}")
    print(f"   Shares: {buy_order.shares:.2f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Sell half the position
    print(f"\n💰 Selling half position ($100.00)...")
    sell_order = engine.sell_position(market, side="UP", amount=100.0)
    
    print(f"   Sell price: ${sell_order.price:.4f}")
    print(f"   Shares sold: {sell_order.shares:.2f}")
    print(f"   Balance after: ${engine.balance:.2f}")
    
    # Check remaining position
    positions = engine.positions()
    if positions:
        print(f"\n📊 Remaining position:")
        print(f"   Shares: {positions[0].shares:.2f}")


def example_set_trailing_after_fill():
    """Example: Setting trailing SL after order is filled."""
    print("\n" + "="*60)
    print("EXAMPLE 9: Set Trailing SL After Fill")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    # Regular buy first
    order = engine.buy(market, side="UP", amount=100.0)
    
    print(f"\n✅ Order filled:")
    print(f"   Entry price: ${order.price:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Add trailing SL later
    print(f"\n🔄 Adding 5% trailing SL...")
    updated = engine.set_trailing_sl(order.id, 0.05)
    
    print(f"   Trailing SL: {updated.trail_sl*100:.1f}%")
    print(f"   SL price: ${updated.trail_sl_price:.4f}")
    
    # Price moves up
    print(f"\n📈 Price moves to $0.60")
    engine.check_limits(market.id, up_price=0.60, down_price=0.40)
    
    print(f"   New SL price: ${updated.trail_sl_price:.4f}")


def example_complex_strategy():
    """Example: Complex strategy with multiple features."""
    print("\n" + "="*60)
    print("EXAMPLE 10: Complex Strategy")
    print("="*60)
    
    engine = polyalpha.PaperEngine(balance=1000.0)
    market = MockMarket()
    
    print(f"\n🎯 Strategy: Buy UP with TP, and add trailing SL if price moves favorably")
    
    # Initial buy with TP only
    order = engine.buy_with_tp_sl(
        market, side="UP", amount=100.0,
        take_profit=0.55
    )
    
    print(f"\n✅ Initial order:")
    print(f"   Entry: ${order.price:.4f}")
    print(f"   TP: ${order.take_profit:.4f}")
    print(f"   Balance: ${engine.balance:.2f}")
    
    # Price moves up - add trailing SL to lock in profits
    print(f"\n📈 Price moves to $0.53 - adding trailing SL")
    engine.check_limits(market.id, up_price=0.53, down_price=0.47)
    
    engine.set_trailing_sl(order.id, 0.03)
    print(f"   Trailing SL set at 3%: ${order.trail_sl_price:.4f}")
    
    # Price continues up - both TP and SL trail
    print(f"\n📈 Price continues to $0.58")
    engine.check_limits(market.id, up_price=0.58, down_price=0.42)
    
    tp_display = order.trail_tp_price if order.trail_tp_price else order.take_profit
    print(f"   TP price: ${tp_display:.4f}")
    print(f"   SL price: ${order.trail_sl_price:.4f}")
    
    # Price drops - trailing SL protects profits
    print(f"\n📉 Price drops to $0.55")
    engine.check_limits(market.id, up_price=0.55, down_price=0.45)
    
    print(f"   SL price: ${order.trail_sl_price:.4f}")
    print(f"   Triggered: {order.tp_sl_triggered_by}")
    print(f"   Balance after: ${engine.balance:.2f}")
    
    # Show summary
    print(f"\n📊 Final Summary:")
    engine.summary()


def main():
    """Run all examples."""
    print("="*60)
    print("ADVANCED ORDER MANAGEMENT EXAMPLES")
    print("="*60)
    
    examples = [
        example_basic_stop_loss,
        example_basic_take_profit,
        example_both_tp_sl,
        example_trailing_stop_loss,
        example_trailing_take_profit,
        example_oco_order,
        example_sell_position,
        example_partial_sell,
        example_set_trailing_after_fill,
        example_complex_strategy,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\n❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("ALL EXAMPLES COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main()
