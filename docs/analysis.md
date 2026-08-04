# Technical Analysis

The analysis module provides data fetching, indicator calculation, signal generation, delta change analysis, and live Binance streaming feeds (CVD + liquidations). Access via `polyalpha.analysis` or direct imports.

```python
from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator, DeltaCalculator, ChainlinkStreamer, ChainlinkStreamerConfig, CVDTracker, CVDTrackerConfig, LiquidationTracker, LiquidationTrackerConfig
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
| `"binance"` | Free Binance API with extensive historical data (fallback when scraping/chainlink unavailable) |
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

#### `supertrend(period=7, multiplier=3.0)`

Supertrend — trailing stop-loss indicator.

```python
st = indicators.supertrend(7, 3.0)
# {"trend": pd.Series, "direction": pd.Series}
```

`direction` is 1 (uptrend, price above band) or -1 (downtrend, price below band).

Returns dict with keys: `"trend"`, `"direction"`.

#### `psar(af=0.02, af_max=0.2)`

Parabolic SAR — trend-following with acceleration factor.

```python
psar = indicators.psar(0.02, 0.2)
# {"value": pd.Series, "trend": pd.Series}
```

`trend` is 1 (price above SAR), -1 (price below SAR), or 0 (unknown).

Returns dict with keys: `"value"`, `"trend"`.

#### `ichimoku(tenkan=9, kijun=26, senkou=52)`

Ichimoku Cloud — comprehensive trend, support/resistance, and momentum.

```python
ichi = indicators.ichimoku()
# {"tenkan": pd.Series, "kijun": pd.Series, "chikou": pd.Series,
#  "span_a": pd.Series, "span_b": pd.Series,
#  "cloud": {"top": pd.Series, "bottom": pd.Series}}
```

Returns dict with keys: `"tenkan"`, `"kijun"`, `"chikou"`, `"span_a"`, `"span_b"`, `"cloud"`.

#### `donchian(length=20)`

Donchian Channels — rolling period high/low range.

```python
dc = indicators.donchian(20)
# {"upper": pd.Series, "middle": pd.Series, "lower": pd.Series}
```

Returns dict with keys: `"upper"`, `"middle"`, `"lower"`.

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

Supports additional keys: `"supertrend"`, `"psar"`, `"donchian"`, `"ichimoku"`.

```python
all_indicators = indicators.calculate_all({
    "supertrend": {"period": 7, "multiplier": 3.0},
    "donchian": {"length": 20},
    "ichimoku": {"tenkan": 9, "kijun": 26, "senkou": 52},
})
```

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
| `ema_bullish_crossover(fast=9, slow=21, price="close")` | Fast EMA crossed above slow EMA |
| `ema_bearish_crossover(fast=9, slow=21, price="close")` | Fast EMA crossed below slow EMA |

### Bollinger Band Signals

| Method | Description |
|--------|-------------|
| `price_above_bb_upper(period=20, std_dev=2.0)` | Price > upper band |
| `price_below_bb_lower(period=20, std_dev=2.0)` | Price < lower band |
| `price_inside_bb(period=20, std_dev=2.0)` | Price inside bands |
| `bb_width(period=20, std_dev=2.0, price="close")` | Current band width (upper - lower) |
| `bb_width_pct(period=20, std_dev=2.0, avg_period=50, price="close")` | Width as % of rolling avg — squeeze detection |
| `bb_squeeze(period=20, std_dev=2.0, avg_period=50, threshold=1.0, price="close")` | True when band width is tight (squeeze) |

### MACD Signals

| Method | Description |
|--------|-------------|
| `macd_bullish_crossover(fast=12, slow=26, signal=9)` | MACD crossed above signal |
| `macd_bearish_crossover(fast=12, slow=26, signal=9)` | MACD crossed below signal |
| `macd_above_zero(fast=12, slow=26, signal=9)` | MACD histogram > 0 |
| `macd_below_zero(fast=12, slow=26, signal=9)` | MACD histogram < 0 |

### SuperTrend Signals

| Method | Description |
|--------|-------------|
| `supertrend_uptrend(period=7, multiplier=3.0)` | Direction == 1 (uptrend) |
| `supertrend_downtrend(period=7, multiplier=3.0)` | Direction == -1 (downtrend) |
| `supertrend_turned_up(period=7, multiplier=3.0)` | Direction just flipped from -1 to 1 |
| `supertrend_turned_down(period=7, multiplier=3.0)` | Direction just flipped from 1 to -1 |

### PSAR Signals

| Method | Description |
|--------|-------------|
| `psar_uptrend(af=0.02, af_max=0.2)` | Price above SAR |
| `psar_downtrend(af=0.02, af_max=0.2)` | Price below SAR |
| `psar_turned_up(af=0.02, af_max=0.2)` | SAR just flipped from downtrend to uptrend |
| `psar_turned_down(af=0.02, af_max=0.2)` | SAR just flipped from uptrend to downtrend |
| `price_above_psar(af=0.02, af_max=0.2, price="close")` | Price > SAR value |
| `price_below_psar(af=0.02, af_max=0.2, price="close")` | Price < SAR value |

### Ichimoku Signals

| Method | Description |
|--------|-------------|
| `ichimoku_tenkan_above_kijun(tenkan=9, kijun=26)` | Tenkan-sen > Kijun-sen |
| `ichimoku_tenkan_below_kijun(tenkan=9, kijun=26)` | Tenkan-sen < Kijun-sen |
| `ichimoku_tenkan_crossed_above_kijun(tenkan=9, kijun=26)` | Tenkan just crossed above Kijun |
| `ichimoku_tenkan_crossed_below_kijun(tenkan=9, kijun=26)` | Tenkan just crossed below Kijun |
| `ichimoku_price_above_cloud(tenkan=9, kijun=26, senkou=52, price="close")` | Price above both cloud spans |
| `ichimoku_price_below_cloud(tenkan=9, kijun=26, senkou=52, price="close")` | Price below both cloud spans |
| `ichimoku_price_inside_cloud(tenkan=9, kijun=26, senkou=52, price="close")` | Price inside the cloud |
| `ichimoku_chikou_above_price(tenkan=9, kijun=26, price="close")` | Chikou span > price |
| `ichimoku_chikou_below_price(tenkan=9, kijun=26, price="close")` | Chikou span < price |
| `ichimoku_bullish_breakout(tenkan=9, kijun=26, senkou=52, price="close")` | Price above cloud AND tenkan > kijun |
| `ichimoku_bearish_breakout(tenkan=9, kijun=26, senkou=52, price="close")` | Price below cloud AND tenkan < kijun |

### Donchian Channel Signals

| Method | Description |
|--------|-------------|
| `price_above_dc_upper(length=20, price="close")` | Price > upper channel |
| `price_below_dc_lower(length=20, price="close")` | Price < lower channel |
| `price_inside_dc(length=20, price="close")` | Price inside channel |
| `dc_breakout_above(length=20, price="close")` | Price just broke above upper channel |
| `dc_breakout_below(length=20, price="close")` | Price just broke below lower channel |

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

## ChainlinkStreamer

Real-time Chainlink price streaming from Polymarket WebSocket.

```python
from polyalpha.analysis import ChainlinkStreamer, ChainlinkStreamerConfig
```

### ChainlinkStreamerConfig

Configuration for the price streamer.

```python
config = ChainlinkStreamerConfig(
    ws_url="wss://ws-live-data.polymarket.com",
    symbol_map={
        "BTC": "btc/usd",
        "ETH": "eth/usd",
        "SOL": "sol/usd",
        "XRP": "xrp/usd",
        "DOGE": "doge/usd",
    },
    timeout=30,
    reconnect_delay=5.0,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ws_url` | `str` | `"wss://ws-live-data.polymarket.com"` | Polymarket WebSocket URL |
| `symbol_map` | `dict` | BTC, ETH, SOL, XRP, DOGE | Asset to WebSocket symbol mapping |
| `timeout` | `int` | `30` | WebSocket timeout in seconds |
| `reconnect_delay` | `float` | `5.0` | Reconnection delay in seconds |

### ChainlinkStreamer

Stream live Chainlink prices from Polymarket WebSocket.

```python
streamer = ChainlinkStreamer()
```

#### Events

| Event | Callback Signature | Description |
|-------|-------------------|-------------|
| `price` | `(symbol: str, price: float, timestamp: datetime)` | Price update |
| `error` | `(exc: Exception)` | Connection or parsing error |
| `connect` | `()` | Successful connection |
| `disconnect` | `()` | Connection lost |

#### Methods

##### `on(event)`

Register a callback for an event.

```python
@streamer.on("price")
def on_price(symbol: str, price: float, timestamp: datetime):
    print(f"{symbol}: ${price:.2f}")
```

##### `start(symbol, background=False)`

Start streaming prices for a symbol.

```python
# Blocking mode
streamer.start("BTC")

# Background mode
streamer.start("BTC", background=True)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | `str` | — | Asset symbol (e.g., `"BTC"`, `"ETH"`) |
| `background` | `bool` | `False` | Run in background thread if True |

##### `stop()`

Stop streaming.

```python
streamer.stop()
```

### Example

```python
from polyalpha.analysis import ChainlinkStreamer

# Create streamer
streamer = ChainlinkStreamer()

# Register callbacks
@streamer.on("price")
def on_price(symbol: str, price: float, timestamp):
    print(f"[{timestamp.strftime('%H:%M:%S')}] {symbol}: ${price:.2f}")

@streamer.on("error")
def on_error(exc: Exception):
    print(f"Error: {exc}")

@streamer.on("connect")
def on_connect():
    print("Connected")

# Start streaming
streamer.start("BTC")
```

### Requirements

Requires `websockets` library:

```bash
pip install websockets>=12.0
```

---

## CVDTracker (Binance cumulative volume delta)

Streams Binance BTC/USDT spot aggregate trades and tracks the cumulative
volume delta — signed by aggressor side (`m=false` → buy → `+qty`;
`m=true` → sell → `-qty`). Runs its own connection in a background task and
reconnects forever on drop.

```python
from polyalpha.analysis import CVDTracker

cvd = CVDTracker()
cvd.start()
```

### CVDTrackerConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ws_url` | `str` | `"wss://stream.binance.com:9443/ws/btcusdt@aggTrade"` | Binance aggTrade WebSocket endpoint |
| `ping_interval` | `float` | `20.0` | WebSocket ping interval |
| `reconnect_delay` | `float` | `3.0` | Delay between reconnect attempts |
| `snapshot_interval` | `float` | `10.0` | Seconds between CVD snapshots |
| `sample_max_age` | `float` | `180.0` | Max age of a signed trade before pruning |
| `history_maxlen` | `int` | `200` | Max `cvd30`/`cvd60` snapshots retained |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `cvd(window_s=60)` | `float` | Sum of signed qty with `ts >= now - window_s` |
| `z(window_s=60)` | `float \| None` | CVD z-score vs snapshot history (needs `>= 5` snapshots) |
| `decelerating()` | `bool \| None` | Last two `cvd30` snapshots share a sign and magnitude shrinks |
| `velocity(key="cvd60")` | `float \| None` | Change between the last two snapshots |
| `acceleration(key="cvd60")` | `float \| None` | Rate of change of velocity (needs `>= 3` snapshots) |
| `start()` | — | Start the background reconnect loop (idempotent) |
| `stop()` | — | Stop the loop and cancel tasks |

```python
cvd.start()

if cvd.z() > 2.0 and not cvd.decelerating():
    print("strong CVD momentum")

cvd.stop()
```

---

## LiquidationTracker (Binance futures liquidations)

Streams Binance USDT-M `btcusdt@forceOrder` and detects one-sided
liquidation clusters — bursts of SELL or BUY liquidations that signal forced
deleveraging. A **SELL** liquidation closes a long (bearish pressure); a
**BUY** liquidation closes a short (bullish pressure). Runs its own connection
and reconnects forever on drop.

```python
from polyalpha.analysis import LiquidationTracker

liq = LiquidationTracker()
liq.start()
```

### LiquidationTrackerConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ws_url` | `str` | `"wss://fstream.binance.com/ws/btcusdt@forceOrder"` | Binance futures forceOrder WebSocket endpoint |
| `ping_interval` | `float` | `20.0` | WebSocket ping interval |
| `reconnect_delay` | `float` | `3.0` | Delay between reconnect attempts |
| `events_maxlen` | `int` | `500` | Max liquidation events retained |

### `cluster(window_s=20, min_count=3, notional_mult=2.0)`

Detect a one-sided liquidation cluster in the last `window_s` seconds:

1. `recent` = events within `window_s`; `< min_count` → `None`.
2. `side` = the **last** event's side; `same` = events with that side;
   `len(same) < min_count` → `None`.
3. `notional = sum(same)`; hourly avg = mean notional over events within
   3600s; if that exists and `notional < avg * notional_mult` → `None`.

Returns `{"direction": "DOWN" | "UP", "notional": float, "count": int}` —
`SELL` → `"DOWN"`, `BUY` → `"UP"` — or `None` when there is no cluster.

```python
liq.start()

if (c := liq.cluster()) is not None:
    print(c["direction"], c["notional"], c["count"])

liq.stop()
```

---

## Shared Globals (one connection, many strategies)

`Globals` holds one instance of every continuously-running feed so all
strategies and markets read the same data — adding a strategy costs zero extra
connections. Caller owns the lifecycle: construct once, `start()` everything,
`stop()` everything in a `finally`.

```python
from polyalpha import Globals, MarketCtx, watch_market, default_globals

globals = default_globals("BTC", price_feed=True, cvd=True, liq=True)
globals.start()

try:
    ...  # run markets
finally:
    globals.stop()
```

### Globals

`Globals(asset="BTC", price_feed=None, klines=None, cvd=None, obi_cache=None,
futures=None, liq=None, db=None, eth_feed=None, klines_15m=None,
klines_1h=None)`.

| Field | Feed | Built by `defaults()` |
|-------|------|------------------------|
| `price_feed` | `ChainlinkStreamer` (BTC spot oracle) | `price_feed=True` |
| `cvd` | `CVDTracker` (Binance spot CVD) | `cvd=True` |
| `liq` | `LiquidationTracker` (Binance futures liquidations) | `liq=True` |
| `klines`, `obi_cache`, `futures`, `db`, `eth_feed`, `klines_15m`, `klines_1h` | out of scope — `None` by default | — |

| Method | Description |
|--------|-------------|
| `defaults(asset, *, price_feed=True, cvd=True, liq=False)` | Build (not start) the standard feeds |
| `start()` | Start every non-`None` feed once (idempotent; `price_feed` via `background=True`) |
| `stop()` | Stop started feeds in reverse order (idempotent) |
| `started` | List of feeds currently started |

### MarketCtx

Per-market scope wrapping one `TokenPairTracker` plus the shared `globals`.

`MarketCtx(globals, tracker, open_price=None, end_time=None)` — attributes
`globals`, `tracker`, `open_price`, `end_time`.

| Member | Description |
|--------|-------------|
| `remaining` | Seconds left in the window (`float("inf")` when no `end_time`) |
| `expired` | True once `remaining <= 0` |
| `price()` | `(up_mid, down_mid)` |
| `favourite()` | `("UP", mid)` / `("DOWN", mid)` / `(None, None)` |
| `spread(side)` | `{"current", "stats", "expansion"}` for one leg |
| `trade_sweep(side, **kwargs)` | One-sided trade burst via `tracker.sweep` |

### watch_market

```python
await watch_market(globals, market, tick, interval=2.0, timeframe=None)
```

Creates and starts a per-market `TokenPairTracker`, wraps it in a `MarketCtx`,
calls `tick(ctx)` every `interval` seconds while `ctx.remaining > 0`, and
stops the tracker in a `finally`. `market` must expose `up_token` /
`down_token` / `end_time` (a `polyalpha.core.market.Market` works directly);
`timeframe` (`"5m"`, …) is the fallback duration when `end_time` can't be
parsed.

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
