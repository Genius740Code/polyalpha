"""
Technical analysis example — standalone usage.

This example demonstrates how to use the technical analysis module
independently of trading bots. It shows data fetching, indicator
calculation, and signal generation.

Usage
-----
    python examples/analysis.py
    python examples/analysis.py --asset ETH --timeframe 15m
    python examples/analysis.py --source binance
    python examples/analysis.py --source chainlink
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

parser = argparse.ArgumentParser(description="polyalpha Technical Analysis")
parser.add_argument("--asset", default="BTC", help="BTC | ETH | SOL | XRP | DOGE")
parser.add_argument("--timeframe", default="5m", help="1m | 5m | 15m | 1h | 4h | 1d")
parser.add_argument("--source", default="binance", help="binance | chainlink | custom")
parser.add_argument("--lookback", type=int, default=500, help="Number of candles to fetch")
parser.add_argument("--log-level", default="INFO", help="DEBUG | INFO | WARNING")
args = parser.parse_args()

print("="*70)
print("TECHNICAL ANALYSIS EXAMPLE")
print("="*70)
print(f"Asset: {args.asset}")
print(f"Timeframe: {args.timeframe}")
print(f"Data Source: {args.source}")
print(f"Lookback: {args.lookback} candles")
print("="*70)

# Data source notice
print("\n" + "!"*70)
print("DATA SOURCE NOTICE:")
print("!"*70)
print("Polymarket uses Chainlink oracles for price feeds.")
print("When using external data sources (Binance, custom APIs),")
print("price discrepancies may occur.")
print("For best accuracy, use Chainlink data when available.")
print("!"*70 + "\n")

# Configure data feed
config = polyalpha.DataFeedConfig(
    source=args.source,
    timeframe=args.timeframe,
    lookback_periods=args.lookback,
)

# Create data feed
print(f"\nFetching data from {args.source}...")
feed = polyalpha.DataFeed(config)

try:
    data = feed.fetch(args.asset)
    print(f"✓ Fetched {len(data)} candles for {args.asset}")
    print(f"  Date range: {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
    print(f"  Price range: ${data['low'].min():.2f} - ${data['high'].max():.2f}")
except Exception as exc:
    print(f"✗ Error fetching data: {exc}")
    sys.exit(1)

# Display latest data
print("\nLatest 5 candles:")
print(data.tail(5).to_string(index=False))

# Calculate indicators
print("\n" + "="*70)
print("CALCULATING INDICATORS")
print("="*70)

indicators = polyalpha.IndicatorCalculator(data)

# Trend indicators
print("\nTrend Indicators:")
sma20 = indicators.sma(20)
sma50 = indicators.sma(50)
ema20 = indicators.ema(20)
print(f"  SMA(20): {indicators.get_latest_value(sma20):.2f}")
print(f"  SMA(50): {indicators.get_latest_value(sma50):.2f}")
print(f"  EMA(20): {indicators.get_latest_value(ema20):.2f}")

# MACD
macd = indicators.macd(12, 26, 9)
print(f"  MACD: {indicators.get_latest_value(macd['macd']):.4f}")
print(f"  MACD Signal: {indicators.get_latest_value(macd['signal']):.4f}")
print(f"  MACD Histogram: {indicators.get_latest_value(macd['histogram']):.4f}")

# Momentum indicators
print("\nMomentum Indicators:")
rsi = indicators.rsi(14)
print(f"  RSI(14): {indicators.get_latest_value(rsi):.2f}")

stoch = indicators.stochastic(14, 3)
print(f"  Stochastic %K: {indicators.get_latest_value(stoch['k']):.2f}")
print(f"  Stochastic %D: {indicators.get_latest_value(stoch['d']):.2f}")

# Volatility indicators
print("\nVolatility Indicators:")
bb = indicators.bollinger_bands(20, 2.0)
print(f"  BB Upper: {indicators.get_latest_value(bb['upper']):.2f}")
print(f"  BB Middle: {indicators.get_latest_value(bb['middle']):.2f}")
print(f"  BB Lower: {indicators.get_latest_value(bb['lower']):.2f}")

atr = indicators.atr(14)
print(f"  ATR(14): {indicators.get_latest_value(atr):.2f}")

# Volume indicators
print("\nVolume Indicators:")
vol_sma = indicators.volume_sma(20)
print(f"  Volume SMA(20): {indicators.get_latest_value(vol_sma):.0f}")

# Generate signals
print("\n" + "="*70)
print("GENERATING SIGNALS")
print("="*70)

signals = polyalpha.SignalGenerator(indicators)

# RSI signals
print("\nRSI Signals:")
print(f"  RSI > 40: {signals.rsi_above(40)}")
print(f"  RSI < 70: {signals.rsi_below(70)}")
print(f"  RSI between 40-70: {signals.rsi_between(40, 70)}")

# Price signals
print("\nPrice Signals:")
print(f"  Price > SMA(20): {signals.price_above_sma(20)}")
print(f"  Price > EMA(20): {signals.price_above_ema(20)}")
print(f"  Price inside BB: {signals.price_inside_bb(20, 2.0)}")

# MACD signals
print("\nMACD Signals:")
print(f"  MACD bullish crossover: {signals.macd_bullish_crossover()}")
print(f"  MACD above zero: {signals.macd_above_zero()}")

# Composite signal
print("\nComposite Signal (RSI > 40 AND Price > SMA20):")
rules = [
    {"condition": "rsi_above", "params": {"threshold": 40}},
    {"condition": "price_above_sma", "params": {"period": 20}},
    {"operator": "AND"},
]
result = signals.evaluate(rules)
print(f"  Result: {result['result']}")
print(f"  Details:")
for detail in result["details"]:
    print(f"    {detail['condition']}: {detail['result']}")

# Signal summary
print("\n" + "="*70)
print("SIGNAL SUMMARY")
print("="*70)

summary = signals.summary()
print(f"  RSI: {summary['rsi']:.2f} ({summary['rsi_status']})")
print(f"  Price vs SMA20: {'above' if summary['price_vs_sma20'] else 'below'}")
print(f"  Price vs EMA20: {'above' if summary['price_vs_ema20'] else 'below'}")
print(f"  MACD Histogram: {summary['macd_histogram']:.4f} ({summary['macd_status']})")
print(f"  BB Position: {summary['bb_position']}")
print(f"  Volume vs SMA: {'above' if summary['volume_vs_sma'] else 'below'}")

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)
