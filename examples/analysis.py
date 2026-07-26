"""
DataFeed + RSI/MACD/BB + signal generation.

Usage:
    python examples/analysis.py
"""
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator

config = DataFeedConfig(source="binance", timeframe="1h", lookback_periods=200)
feed = DataFeed(config)
data = feed.fetch("BTC")

print(f"Fetched {len(data)} candles\n")

indicators = IndicatorCalculator(data)

rsi = indicators.rsi(14)
macd = indicators.macd(12, 26, 9)
bb = indicators.bollinger_bands(20, 2.0)

print(f"RSI(14): {indicators.get_latest_value(rsi):.2f}")
print(f"MACD: {indicators.get_latest_value(macd['macd']):.4f}")
print(f"Signal: {indicators.get_latest_value(macd['signal']):.4f}")
print(f"Histogram: {indicators.get_latest_value(macd['histogram']):.4f}")
print(f"BB Upper: {indicators.get_latest_value(bb['upper']):.4f}")
print(f"BB Mid:   {indicators.get_latest_value(bb['mid']):.4f}")
print(f"BB Lower: {indicators.get_latest_value(bb['lower']):.4f}")

signals = SignalGenerator(indicators)

entry = all([
    signals.rsi_above(30),
    signals.price_above_sma(20),
    signals.macd_bullish_crossover(),
])

exit_signal = all([
    signals.rsi_below(70) is False,
    signals.price_below_bb_lower(),
])

signal_str = "BUY" if entry else "SELL" if exit_signal else "HOLD"
print(f"\nComposite signal: {signal_str}")
