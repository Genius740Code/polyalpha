"""
Example: Using Price Change Signals for Trading

This example demonstrates how to use the built-in price change detection
methods to filter trades based on minimum BTC price movements.

Usage:
------
    python examples/price_change_signals.py
"""

import polyalpha
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator

def main():
    # Initialize client
    client = polyalpha.Client(log_level="INFO")
    
    # Get market
    market = client.markets.latest("BTC", "5m")
    print(f"Market: {market.slug}")
    print(f"Current UP price: {market.up_price:.4f}")
    print(f"Current DOWN price: {market.down_price:.4f}")
    
    # Fetch historical data for technical analysis
    try:
        feed_config = DataFeedConfig(
            source="binance",
            timeframe="5m",
            lookback_periods=50,
        )
        feed = DataFeed(feed_config)
        data = feed.fetch("BTC")
        
        # Calculate indicators
        indicators = IndicatorCalculator(data)
        signals = SignalGenerator(indicators)
        
        print("\n" + "="*60)
        print("Price Change Signal Examples")
        print("="*60)
        
        # Example 1: Only trade if BTC changed by at least $30 from last candle
        if signals.price_change_above(30):
            print("✓ Price changed by at least $30 from last candle")
        else:
            print("✗ Price change less than $30 from last candle")
        
        # Example 2: Only trade if BTC is up from last candle
        if signals.price_up():
            print("✓ Price is up from last candle")
        else:
            print("✗ Price is down from last candle")
        
        # Example 3: Only trade if BTC is up by at least $30
        if signals.price_above_by(30):
            print("✓ Price is up by at least $30 from last candle")
        else:
            print("✗ Price is not up by $30 from last candle")
        
        # Example 4: Only trade if BTC is down by at least $30
        if signals.price_below_by(30):
            print("✓ Price is down by at least $30 from last candle")
        else:
            print("✗ Price is not down by $30 from last candle")
        
        # Example 5: Only trade if price changed by at least 0.5%
        if signals.price_change_percent_above(0.5):
            print("✓ Price changed by at least 0.5% from last candle")
        else:
            print("✗ Price change less than 0.5% from last candle")
        
        # Example 6: Check price change from 3 candles ago
        if signals.price_change_above(100, candles_back=3):
            print("✓ Price changed by at least $100 from 3 candles ago")
        else:
            print("✗ Price change less than $100 from 3 candles ago")
        
        # Example 7: Only trade if price is down (for DOWN side)
        if signals.price_down():
            print("✓ Price is down from last candle (good for DOWN trades)")
        else:
            print("✗ Price is up from last candle (not good for DOWN trades)")
        
        print("\n" + "="*60)
        print("Combined Strategy Example")
        print("="*60)
        
        # Example: Combined strategy for UP trades
        # Only buy UP if:
        # - Price is up from last candle
        # - Price changed by at least $30
        # - RSI is not overbought
        if (signals.price_up() and 
            signals.price_change_above(30) and 
            signals.rsi_below(70)):
            print("✓ STRONG BUY SIGNAL: Price up + significant move + RSI OK")
        else:
            print("✗ No buy signal - conditions not met")
        
        # Example: Combined strategy for DOWN trades
        # Only buy DOWN if:
        # - Price is down from last candle
        # - Price changed by at least $30
        # - RSI is not oversold
        if (signals.price_down() and 
            signals.price_change_above(30) and 
            signals.rsi_above(30)):
            print("✓ STRONG SELL SIGNAL: Price down + significant move + RSI OK")
        else:
            print("✗ No sell signal - conditions not met")
        
    except ImportError:
        print("\nNote: Technical analysis requires pandas-ta.")
        print("Install with: pip install pandas-ta")
    except Exception as e:
        print(f"\nError in technical analysis: {e}")
    
    client.close()

if __name__ == "__main__":
    main()
