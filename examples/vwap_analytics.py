"""
VWAP Analytics Example

This example demonstrates how to use VWAP (Volume Weighted Average Price) 
analytics for trading signals and analysis.
"""

from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator


def main():
    """Demonstrate VWAP analytics."""
    # Fetch data
    config = DataFeedConfig(source="binance", timeframe="5m")
    feed = DataFeed(config)
    data = feed.fetch("BTC")
    
    print(f"Fetched {len(data)} candles of BTC data")
    print(f"Data columns: {data.columns.tolist()}")
    print()
    
    # Calculate indicators
    indicators = IndicatorCalculator(data)
    
    # Calculate VWAP
    vwap = indicators.vwap()
    latest_vwap = indicators.get_latest_value(vwap)
    latest_price = data["close"].iloc[-1]
    
    print(f"Latest Price: ${latest_price:.2f}")
    print(f"Latest VWAP: ${latest_vwap:.2f}")
    print(f"Price vs VWAP: ${latest_price - latest_vwap:.2f}")
    print()
    
    # Generate signals
    signals = SignalGenerator(indicators)
    
    # Basic VWAP signals
    print("=== Basic VWAP Signals ===")
    print(f"Price above VWAP: {signals.price_above_vwap()}")
    print(f"Price below VWAP: {signals.price_below_vwap()}")
    print()
    
    # VWAP trend signals
    print("=== VWAP Trend Signals ===")
    print(f"VWAP rising (5 periods): {signals.vwap_rising(5)}")
    print(f"VWAP falling (5 periods): {signals.vwap_falling(5)}")
    print()
    
    # VWAP band signals
    print("=== VWAP Band Signals ===")
    print(f"Price above VWAP upper band (1 std): {signals.price_above_vwap_band(1.0)}")
    print(f"Price below VWAP lower band (1 std): {signals.price_below_vwap_band(1.0)}")
    print(f"Price within VWAP bands (1 std): {signals.price_within_vwap_bands(1.0)}")
    print()
    
    # VWAP distance
    print("=== VWAP Distance ===")
    vwap_distance = signals.vwap_distance_pct()
    print(f"Price distance from VWAP: {vwap_distance:.2f}%")
    print()
    
    # Combined strategy example
    print("=== Combined Strategy Example ===")
    # Strategy: Buy when price is above VWAP and VWAP is rising
    if signals.price_above_vwap() and signals.vwap_rising(5):
        print("BUY SIGNAL: Price above VWAP and VWAP rising")
    elif signals.price_below_vwap() and signals.vwap_falling(5):
        print("SELL SIGNAL: Price below VWAP and VWAP falling")
    else:
        print("HOLD: No clear VWAP signal")
    
    print()
    
    # Use summary for overview
    print("=== Signal Summary ===")
    summary = signals.summary()
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
