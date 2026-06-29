# Market Analysis & Signals

The `polyalpha.analysis` module provides tools for technical analysis and signal generation, allowing you to build data-driven trading strategies on top of Polymarket Up/Down markets.

It works seamlessly with both external data feeds (e.g. Binance, Chainlink) and the Sniper bot.

---

## Quick start

```python
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator

# 1. Fetch historical data
config = DataFeedConfig(source="binance", timeframe="5m", lookback_periods=200)
feed = DataFeed(config)
data = feed.fetch("BTC")

# 2. Calculate indicators
indicators = IndicatorCalculator(data)

# 3. Generate signals
signals = SignalGenerator(indicators)

# Check simple conditions
if signals.rsi_above(40) and signals.price_above_sma(20):
    print("BUY signal triggered!")
```

---

## Data Feeds

A `DataFeed` retrieves historical OHLCV data for an asset. By default, it integrates with external providers like Binance.

```python
config = DataFeedConfig(
    source="binance",          # "binance", "chainlink", or "custom"
    timeframe="5m",            # matches polyalpha timeframes
    lookback_periods=200,      # number of candles to fetch
)

feed = DataFeed(config)
df = feed.fetch("BTC")         # Returns a pandas DataFrame
```

---

## Indicator Calculator

The `IndicatorCalculator` computes technical indicators based on a data feed's dataframe. It computes values across the entire dataset.

```python
indicators = IndicatorCalculator(data)

# Calculate indicators
rsi = indicators.rsi(period=14)
sma = indicators.sma(period=20)
macd_data = indicators.macd(fast=12, slow=26, signal=9)

print(macd_data["macd"], macd_data["signal"], macd_data["histogram"])
```

| Indicator | Method | Description |
|---|---|---|
| RSI | `rsi(period=14)` | Relative Strength Index |
| SMA | `sma(period=20)` | Simple Moving Average |
| EMA | `ema(period=20)` | Exponential Moving Average |
| MACD | `macd(fast=12, slow=26, signal=9)` | Returns dictionary with `macd`, `signal`, `histogram` series |
| Bollinger Bands | `bollinger_bands(...)` | Returns `upper`, `middle`, `lower` series |

---

## Signal Generator

The `SignalGenerator` sits on top of the indicators and exposes methods to query boolean trading signals for the most recent data points.

```python
signals = SignalGenerator(indicators)
```

### Simple Signals

Methods return `True` or `False` depending on current market conditions:

| Method | Returns True if... |
|---|---|
| `rsi_above(threshold)` | Current RSI is strictly greater than `threshold` |
| `rsi_below(threshold)` | Current RSI is strictly less than `threshold` |
| `price_above_sma(period)` | Current close price is greater than the SMA |
| `price_below_sma(period)` | Current close price is less than the SMA |
| `macd_bullish_cross()` | MACD line just crossed above the signal line |
| `macd_bearish_cross()` | MACD line just crossed below the signal line |

### Custom Signal Evaluation

You can pass an abstract dictionary of rules to the `evaluate()` method to construct complex, composite signals.

```python
rules = {
    "operator": "AND",
    "conditions": [
        {"indicator": "RSI", "condition": "above", "value": 50},
        {"indicator": "MACD", "condition": "bullish_cross"}
    ]
}

result = signals.evaluate(rules)
print(result["result"])  # True/False
```

---

## Integration with Sniper Bot

The simplest way to use signals is by letting the `Sniper` bot handle them natively. Set `use_ta=True` and configure your thresholds in `SniperConfig`:

```python
from polyalpha.bots import SniperConfig, Sniper

config = SniperConfig(
    asset="BTC",
    timeframe="5m",
    side="UP",
    entry_price=0.92,
    window_seconds=35,
    amount=20.0,
    
    # Enable technical analysis
    use_ta=True,
    ta_data_source="binance",
    ta_rsi_threshold=50,       # Only buy if RSI > 50
    ta_sma_period=20,          # Only buy if Price > SMA(20)
)

# You can also pass custom composite rules
# config.ta_rules = rules

sniper = Sniper(client, config)
sniper.run()
```

When enabled, the bot automatically checks the signal conditions upon entering the trading window or when the `entry_price` is reached. If conditions fail, it aborts the entry and waits for the next cycle.
