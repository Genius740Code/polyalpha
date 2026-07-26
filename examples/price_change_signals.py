"""
Price change detection + RSI combo — alert on sharp moves with oversold/overbought RSI.

Usage:
    python examples/price_change_signals.py
"""
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator

config = DataFeedConfig(source="binance", timeframe="5m", lookback_periods=100)
feed = DataFeed(config)
data = feed.fetch("ETH")

indicators = IndicatorCalculator(data)
signals = SignalGenerator(indicators)

price_moved = signals.price_change_percent_above(2.0)
oversold = signals.rsi_below(30)
overbought = signals.rsi_above(70)

if price_moved and oversold:
    print("ALERT: ETH dropped >2% with RSI oversold — potential reversal up")
elif price_moved and overbought:
    print("ALERT: ETH jumped >2% with RSI overbought — potential reversal down")
else:
    print("No extreme price move detected")

rsi_val = indicators.get_latest_value(indicators.rsi(14))
close = data["close"].iloc[-1]
prev_close = data["close"].iloc[-2]
change_pct = ((close - prev_close) / prev_close) * 100
print(f"ETH close: {close:.4f} | Change: {change_pct:+.2f}% | RSI(14): {rsi_val:.2f}")
