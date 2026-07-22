# Technical Analysis

The analysis module provides data fetching, indicator calculation, signal generation, and delta change analysis. Access via `polyalpha.analysis` or direct imports.

```python
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator, DeltaCalculator
```

---

## DataFeedConfig

```python
from polyalpha.analysis import DataFeedConfig

config = DataFeedConfig(
    source="binance",      # "binance" | "chainlink" | "scraping" | "custom" | "websocket"
    timeframe="5m",        # "1m" | "5m" | "15m" | "1h" | "4h" | "1d"
    lookback_periods=500,  # number of candles to fetch
    use_cache=True,        # cache fetched data locally
    cache_dir=None,        # defaults to ~/.polyalpha/cache/
)
```

### Data Sources

| Source | Description |
|--------|-------------|
| `"binance"` | Free Binance API with extensive historical data (default fallback) |
| `"chainlink"` | Chainlink oracle data — matches Polymarket. Falls back to Binance if web3 not installed |
| `"scraping"` | Polymarket WebSocket with configurable delay — collects live prices directly |
| `"custom"` | User-provided API with optional auth key |
| `"websocket"` | Builds OHLCV from existing Stream cache |

### Source-Specific Fields

**Binance:**
```python
config = DataFeedConfig(
    source="binance",
    binance_api_url="https://api.binance.com/api/v3/klines",  # default
)
```

**Chainlink (requires `web3`):**
```python
config = DataFeedConfig(
    source="chainlink",
    chainlink_rpc_url="https://eth.llamarpc.com",
    chainlink_contracts={
        "BTC": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
        "ETH": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    },
)
```

**Scraping (requires `websockets`):**
```python
config = DataFeedConfig(
    source="scraping",
    scraping_ws_url="wss://ws-live-data.polymarket.com",
    scraping_delay=2.0,
    scraping_timeout=90,
)
```

**Custom:**
```python
config = DataFeedConfig(
    source="custom",
    custom_url="https://your-api.com/ohlcv",
    custom_api_key="your-key",
)
```

### Asset Map

Maps PolyAlpha asset symbols to data source symbols:

| Asset | Binance Symbol | Chainlink Contract |
|-------|---------------|--------------------|
| BTC | BTCUSDT | BTC/USD |
| ETH | ETHUSDT | ETH/USD |
| SOL | SOLUSDT | SOL/USD |
| XRP | XRPUSDT | XRP/USD |
| DOGE | DOGEUSDT | DOGE/USD |

Override via `asset_map` parameter.

---

## DataFeed

```python
config = DataFeedConfig(source="binance", timeframe="5m")
feed = DataFeed(config)
```

### Methods

#### `fetch(asset)`

Fetch historical OHLCV data for an asset.

```python
data = feed.fetch("BTC")
# Returns: pd.DataFrame with columns: timestamp, open, high, low, close, volume
```

| Param | Type | Description |
|-------|------|-------------|
| `asset` | `str` | Asset symbol (e.g., `"BTC"`, `"ETH"`) |

Returns a `pd.DataFrame` with OHLCV columns. Raises `ValueError` if asset is not in asset map.

#### `update(price, timestamp=None)`

Add a real-time price tick to the WebSocket cache.

```python
feed.update(price=52345.0)
```

| Param | Type | Description |
|-------|------|-------------|
| `price` | `float` | Current price |
| `timestamp` | `datetime \| None` | Defaults to now |

#### `resample(timeframe)`

Resample data to a different timeframe.

```python
hourly_data = feed.resample("1h")
```

| Param | Type | Description |
|-------|------|-------------|
| `timeframe` | `str` | Target: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"` |

#### `get_latest(n=1)`

Get the latest `n` candles.

```python
latest_candle = feed.get_latest(1)
```

#### `to_csv(filepath)`

Export fetched data to CSV.

```python
feed.to_csv("btc_data.csv")
```

#### `from_csv(filepath)`

Import data from CSV.

```python
feed.from_csv("btc_data.csv")
```

---

## IndicatorCalculator

Calculates technical indicators using `pandas-ta` (with native numpy/pandas fallback).

```python
indicators = IndicatorCalculator(data)
```

### Trend Indicators

#### `sma(period=20, price="close")`

Simple Moving Average.

```python
sma_20 = indicators.sma(20)
sma_50 = indicators.sma(50, price="close")
```

Returns `pd.Series`.

#### `ema(period=20, price="close")`

Exponential Moving Average.

```python
ema_12 = indicators.ema(12)
ema_26 = indicators.ema(26)
```

Returns `pd.Series`.

#### `macd(fast=12, slow=26, signal=9, price="close")`

Moving Average Convergence Divergence.

```python
macd = indicators.macd()
# {"macd": pd.Series, "signal": pd.Series, "histogram": pd.Series}
```

Returns dict with keys: `"macd"`, `"signal"`, `"histogram"`.

#### `adx(period=14)`

Average Directional Index.

```python
adx = indicators.adx(14)
# {"adx": pd.Series, "plus_di": pd.Series, "minus_di": pd.Series}
```

Returns dict with keys: `"adx"`, `"plus_di"`, `"minus_di"`.

### Momentum Indicators

#### `rsi(period=14, price="close")`

Relative Strength Index (0–100).

```python
rsi = indicators.rsi(14)
```

Returns `pd.Series`.

#### `stochastic(k_period=14, d_period=3, smooth_k=3)`

Stochastic Oscillator.

```python
stoch = indicators.stochastic()
# {"k": pd.Series, "d": pd.Series}
```

Returns dict with keys: `"k"`, `"d"`.

#### `williams_r(period=14)`

Williams %R (−100 to 0).

```python
willr = indicators.williams_r(14)
```

Returns `pd.Series`.

#### `cci(period=20)`

Commodity Channel Index.

```python
cci = indicators.cci(20)
```

Returns `pd.Series`.

### Volatility Indicators

#### `bollinger_bands(period=20, std_dev=2.0, price="close")`

Bollinger Bands.

```python
bb = indicators.bollinger_bands()
# {"upper": pd.Series, "middle": pd.Series, "lower": pd.Series}
```

Returns dict with keys: `"upper"`, `"middle"`, `"lower"`.

#### `atr(period=14)`

Average True Range.

```python
atr = indicators.atr(14)
```

Returns `pd.Series`.

#### `keltner_channels(period=20, atr_period=10, atr_mult=2.0)`

Keltner Channels.

```python
kc = indicators.keltner_channels()
# {"upper": pd.Series, "middle": pd.Series, "lower": pd.Series}
```

Returns dict with keys: `"upper"`, `"middle"`, `"lower"`.

### Volume Indicators

#### `obv()`

On-Balance Volume.

```python
obv = indicators.obv()
```

Returns `pd.Series`.

#### `volume_sma(period=20)`

Volume Simple Moving Average.

```python
vol_sma = indicators.volume_sma(20)
```

Returns `pd.Series`.

#### `volume_roc(period=12)`

Volume Rate of Change.

```python
vol_roc = indicators.volume_roc(12)
```

Returns `pd.Series`.

### Batch Calculation

#### `calculate_all(config=None)`

Calculate multiple indicators at once.

```python
all_indicators = indicators.calculate_all({
    "sma": [20, 50],
    "ema": [12, 26],
    "rsi": [14],
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bollinger_bands": {"period": 20, "std_dev": 2.0},
    "atr": [14],
})
```

Default config calculates SMA(20,50), EMA(12,26), RSI(14), MACD, Bollinger Bands, and ATR(14).

### Helpers

| Method | Description |
|--------|-------------|
| `get_latest_value(series)` | Get latest non-NaN value from a series |
| `get_latest_values(indicators)` | Get latest values from multiple indicators |
| `clear_cache()` | Clear indicator result cache |

```python
latest_rsi = indicators.get_latest_value(indicators.rsi(14))
```

---

## SignalGenerator

Generates boolean trading signals from indicators.

```python
signals = SignalGenerator(indicators)
```

### RSI Signals

| Method | Description |
|--------|-------------|
| `rsi_above(threshold, period=14)` | RSI > threshold |
| `rsi_below(threshold, period=14)` | RSI < threshold |
| `rsi_between(lower, upper, period=14)` | lower < RSI < upper |

### Moving Average Signals

| Method | Description |
|--------|-------------|
| `price_above_sma(period=20, price="close")` | Price > SMA |
| `price_below_sma(period=20, price="close")` | Price < SMA |
| `price_above_ema(period=20, price="close")` | Price > EMA |
| `price_below_ema(period=20, price="close")` | Price < EMA |

### Bollinger Band Signals

| Method | Description |
|--------|-------------|
| `price_above_bb_upper(period=20, std_dev=2.0)` | Price > upper band |
| `price_below_bb_lower(period=20, std_dev=2.0)` | Price < lower band |
| `price_inside_bb(period=20, std_dev=2.0)` | Price inside bands |

### MACD Signals

| Method | Description |
|--------|-------------|
| `macd_bullish_crossover(fast=12, slow=26, signal=9)` | MACD crossed above signal |
| `macd_bearish_crossover(fast=12, slow=26, signal=9)` | MACD crossed below signal |
| `macd_above_zero(fast=12, slow=26, signal=9)` | MACD histogram > 0 |
| `macd_below_zero(fast=12, slow=26, signal=9)` | MACD histogram < 0 |

### Stochastic Signals

| Method | Description |
|--------|-------------|
| `stochastic_above(threshold, k_period=14, d_period=3, line="k")` | Stochastic line > threshold |
| `stochastic_below(threshold, k_period=14, d_period=3, line="k")` | Stochastic line < threshold |

### Volume Signals

| Method | Description |
|--------|-------------|
| `volume_above_sma(period=20)` | Volume > volume SMA |
| `volume_below_sma(period=20)` | Volume < volume SMA |

### Price Change Signals

| Method | Description |
|--------|-------------|
| `price_change_above(min_change, candles_back=1)` | \|Δprice\| ≥ min_change |
| `price_change_below(max_change, candles_back=1)` | \|Δprice\| ≤ max_change |
| `price_above_by(min_change, candles_back=1)` | Price up by ≥ min_change |
| `price_below_by(min_change, candles_back=1)` | Price down by ≥ min_change |
| `price_change_percent_above(min_pct, candles_back=1)` | \|Δ%\| ≥ min_pct |
| `price_change_percent_below(max_pct, candles_back=1)` | \|Δ%\| ≤ max_pct |
| `price_up(candles_back=1)` | Price is up |
| `price_down(candles_back=1)` | Price is down |
| `price_up_by_percent(min_pct, candles_back=1)` | Price up by ≥ min_pct% |
| `price_down_by_percent(min_pct, candles_back=1)` | Price down by ≥ min_pct% |

All price change methods accept optional `candles_back` (lookback periods) and `price` (column to use).

### Composite Signals

#### `evaluate(rules)`

Evaluate multiple signal rules with AND/OR operators.

```python
rules = [
    {"condition": "rsi_above", "params": {"threshold": 40}},
    {"condition": "price_above_sma", "params": {"period": 20}},
    {"operator": "AND"},
    {"condition": "volume_above_sma", "params": {"period": 20}},
    {"operator": "OR"},
]
result = signals.evaluate(rules)
# {"result": True, "signals": [True, True, True], "details": [...]}
```

#### `custom(condition_fn)`

Evaluate a custom condition function.

```python
def my_rule(indicators):
    rsi = indicators.get_latest_value(indicators.rsi(14))
    price = indicators.data["close"].iloc[-1]
    return rsi is not None and rsi > 40 and price > 50000

result = signals.custom(my_rule)
```

### Summary

#### `summary()`

Generate a summary of current signal states.

```python
state = signals.summary()
# {
#     "rsi": 55.2,
#     "rsi_status": "bullish",   # "bullish" | "bearish" | "overbought" | "oversold"
#     "price_vs_sma20": True,
#     "price_vs_ema20": False,
#     "macd_histogram": 12.5,
#     "macd_status": "bullish",
#     "bb_position": "inside",   # "inside" | "above_upper" | "below_lower"
#     "volume_vs_sma": True,
# }
```

---

## DeltaCalculator

Measures price velocity and acceleration (rate of change).

```python
from polyalpha.analysis import DeltaCalculator

delta = DeltaCalculator(data)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `delta(price="close")` | `pd.Series` | Price change between consecutive periods |
| `delta_period(period=1, price="close")` | `pd.Series` | Price change over N periods |
| `delta_percent(price="close")` | `pd.Series` | Percentage change between consecutive periods |
| `delta_percent_period(period=1, price="close")` | `pd.Series` | Percentage change over N periods |
| `delta_acceleration(period=1, price="close")` | `pd.Series` | Rate of change of delta (2nd derivative) |
| `delta_smoothed(period=1, smooth_period=3, price="close")` | `pd.Series` | Delta with SMA smoothing |
| `get_latest_value(series)` | `float \| None` | Latest non-NaN value |
| `clear_cache()` | — | Clear cached results |

```python
simple = delta.delta()
pct_change = delta.delta_percent()
acceleration = delta.delta_acceleration()
smoothed = delta.delta_smoothed(period=5, smooth_period=3)
```

---

## Complete Example

```python
from polyalpha.analysis import (
    DataFeed, DataFeedConfig,
    IndicatorCalculator, SignalGenerator, DeltaCalculator,
)

# 1. Fetch data
config = DataFeedConfig(source="binance", timeframe="5m", lookback_periods=200)
feed = DataFeed(config)
data = feed.fetch("BTC")

# 2. Calculate indicators
indicators = IndicatorCalculator(data)
rsi = indicators.rsi(14)
sma = indicators.sma(20)
bb = indicators.bollinger_bands()

# 3. Generate signals
signals = SignalGenerator(indicators)

if signals.rsi_above(50) and signals.price_above_sma(20):
    print("Bullish signal")

if signals.macd_bullish_crossover():
    print("MACD bullish crossover")

state = signals.summary()
print(f"RSI: {state['rsi']:.1f} ({state['rsi_status']})")

# 4. Delta analysis
delta = DeltaCalculator(data)
price_velocity = delta.delta_percent()
print(f"Latest price change: {delta.get_latest_value(price_velocity):.2f}%")
```
