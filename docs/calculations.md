# Calculations Library

The calculations library provides unified, modular calculation functions for market data analysis across all data sources (Chainlink, Binance, Coinbase). It's designed to be source-aware, providing appropriate calculations based on data availability.

## Overview

The library is organized into three main components:

1. **Market Calculations** - Universal price calculations for all data sources
2. **Volume Calculations** - Volume-specific calculations for data sources with volume data
3. **Data Source Accessors** - Source-specific accessors that integrate calculations with live data

## Market Calculations

Universal price calculations that work with any time series data from Chainlink, Binance, Coinbase, or other price sources.

```python
from polyalpha.calculations import MarketCalculations

# Percentage change over N periods
change = MarketCalculations.change_pct(data, period=1)

# Absolute price change over N periods  
abs_change = MarketCalculations.change_abs(data, period=1)

# Rate of change per second (derivative)
rate = MarketCalculations.rate_of_change(data, period=1, time_interval=1.0)

# Trend direction (UP/DOWN/NEUTRAL)
trend = MarketCalculations.trend(data, period=1, threshold=0.0)

# Simple direction ("up"/"down"/"flat")
direction = MarketCalculations.direction(data, period=1)

# Price volatility (standard deviation)
volatility = MarketCalculations.volatility(data, period=10)

# Highest price in period
high = MarketCalculations.high(data, period=10)

# Lowest price in period
low = MarketCalculations.low(data, period=10)

# Price range (high - low)
price_range = MarketCalculations.range(data, period=10)
```

### API Reference

#### `change_pct(data, period=1)`

Calculate percentage change over a given period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods back to compare (default: 1)

**Returns:** `float | None` - Percentage change as decimal (e.g., 0.12 for 12%). Returns None if insufficient data.

**Example:**
```python
data = [100.0, 105.0, 103.0]
result = MarketCalculations.change_pct(data, period=2)  # 0.03
```

#### `change_abs(data, period=1)`

Calculate absolute price change over a given period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods back to compare (default: 1)

**Returns:** `float | None` - Absolute price difference. Returns None if insufficient data.

**Example:**
```python
data = [100.0, 105.0, 103.0]
result = MarketCalculations.change_abs(data, period=2)  # 3.0
```

#### `rate_of_change(data, period=1, time_interval=1.0)`

Calculate rate of change per time unit (derivative).

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods back to compare (default: 1)
- `time_interval` (float): Time between data points in seconds (default: 1.0)

**Returns:** `float | None` - Rate of change per second. Returns None if insufficient data or time_interval is 0.

**Example:**
```python
data = [100.0, 105.0, 103.0]
result = MarketCalculations.rate_of_change(data, period=1, time_interval=5.0)  # -0.4
```

#### `trend(data, period=1, threshold=0.0)`

Determine overall trend direction over a period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods back to analyze (default: 1)
- `threshold` (float): Minimum absolute change to consider a trend (default: 0.0)

**Returns:** `TrendDirection` - UP, DOWN, or NEUTRAL based on price movement.

**Example:**
```python
data = [100.0, 105.0, 103.0, 108.0]
result = MarketCalculations.trend(data, period=3)  # TrendDirection.UP
```

#### `direction(data, period=1)`

Get simple direction of change (up/down/flat).

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods back to compare (default: 1)

**Returns:** `str | None` - "up", "down", or "flat". Returns None if insufficient data.

**Example:**
```python
data = [100.0, 105.0, 103.0]
result = MarketCalculations.direction(data, period=2)  # "up"
```

#### `volatility(data, period=10)`

Calculate price volatility (standard deviation) over a period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods to analyze (default: 10)

**Returns:** `float | None` - Standard deviation of prices over the period. Returns None if insufficient data.

**Example:**
```python
data = [100.0, 105.0, 103.0, 108.0, 102.0]
result = MarketCalculations.volatility(data, period=5)  # ~2.68
```

#### `high(data, period=10)`

Get highest price over a period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods to analyze (default: 10)

**Returns:** `float | None` - Highest price in the period. Returns None if no data.

**Example:**
```python
data = [100.0, 105.0, 103.0, 108.0, 102.0]
result = MarketCalculations.high(data, period=5)  # 108.0
```

#### `low(data, period=10)`

Get lowest price over a period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods to analyze (default: 10)

**Returns:** `float | None` - Lowest price in the period. Returns None if no data.

**Example:**
```python
data = [100.0, 105.0, 103.0, 108.0, 102.0]
result = MarketCalculations.low(data, period=5)  # 100.0
```

#### `range(data, period=10)`

Calculate price range (high - low) over a period.

**Parameters:**
- `data` (List[float]): Time series data points (oldest to newest)
- `period` (int): Number of periods to analyze (default: 10)

**Returns:** `float | None` - Price range (high - low). Returns None if insufficient data.

**Example:**
```python
data = [100.0, 105.0, 103.0, 108.0, 102.0]
result = MarketCalculations.range(data, period=5)  # 8.0
```

## Volume Calculations

Volume-specific calculations for data sources that provide volume information such as Binance and Coinbase. Chainlink/Polymarket data does not include volume.

```python
from polyalpha.calculations import VolumeCalculations

# Current volume as ratio to average volume
vol_ratio = VolumeCalculations.vol_ratio(data, period=10)

# Volume trend direction
volume_trend = VolumeCalculations.volume_trend(data, period=5, threshold=0.1)

# Detect volume surge
volume_surge = VolumeCalculations.volume_surge(data, multiplier=2.0, period=10)

# Average volume
avg_volume = VolumeCalculations.avg_volume(data, period=10)

# Volume momentum (% change)
volume_momentum = VolumeCalculations.volume_momentum(data, period=5)

# Relative volume (percentile-based)
relative_volume = VolumeCalculations.relative_volume(data, percentile=0.75, period=20)
```

### API Reference

#### `vol_ratio(data, period=10)`

Calculate current volume as ratio to average volume over period.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `period` (int): Number of periods to calculate average (default: 10)

**Returns:** `float | None` - Current volume / average volume over period. Returns None if insufficient data or average is 0.

**Example:**
```python
data = [100.0, 120.0, 110.0, 130.0]
result = VolumeCalculations.vol_ratio(data, period=3)  # ~1.18
```

#### `volume_trend(data, period=5, threshold=0.1)`

Determine volume trend direction over a period.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `period` (int): Number of periods back to analyze (default: 5)
- `threshold` (float): Minimum relative change to consider a trend (default: 0.1 for 10%)

**Returns:** `VolumeTrend` - INCREASING, DECREASING, or STABLE based on volume movement.

**Example:**
```python
data = [100.0, 120.0, 110.0, 130.0]
result = VolumeCalculations.volume_trend(data, period=3, threshold=0.1)  # VolumeTrend.INCREASING
```

#### `volume_surge(data, multiplier=2.0, period=10)`

Detect sudden volume surge compared to recent average.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `multiplier` (float): Multiple of average volume to consider a surge (default: 2.0)
- `period` (int): Number of periods to calculate average (default: 10)

**Returns:** `bool | None` - True if current volume is > multiplier * average volume. Returns None if insufficient data.

**Example:**
```python
data = [100.0, 110.0, 105.0, 120.0, 250.0]
result = VolumeCalculations.volume_surge(data, multiplier=2.0, period=4)  # True
```

#### `avg_volume(data, period=10)`

Calculate average volume over a period.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `period` (int): Number of periods to average (default: 10)

**Returns:** `float | None` - Average volume over the period. Returns None if no data.

**Example:**
```python
data = [100.0, 120.0, 110.0, 130.0]
result = VolumeCalculations.avg_volume(data, period=3)  # 120.0
```

#### `volume_momentum(data, period=5)`

Calculate volume momentum - rate of volume change.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `period` (int): Number of periods back to compare (default: 5)

**Returns:** `float | None` - Percentage change in volume over period. Returns None if insufficient data.

**Example:**
```python
data = [100.0, 120.0, 110.0, 130.0]
result = VolumeCalculations.volume_momentum(data, period=3)  # 0.30 (30% increase)
```

#### `relative_volume(data, percentile=0.75, period=20)`

Check if current volume is above a percentile of recent volumes.

**Parameters:**
- `data` (List[float]): Volume data points (oldest to newest)
- `percentile` (float): Percentile threshold (0.0 to 1.0, default: 0.75 for 75th percentile)
- `period` (int): Number of periods to analyze (default: 20)

**Returns:** `bool | None` - True if current volume is above the specified percentile. Returns None if insufficient data.

**Example:**
```python
data = [100.0, 110.0, 105.0, 120.0, 130.0]
result = VolumeCalculations.relative_volume(data, percentile=0.75, period=4)  # True
```

## Data Source Accessors

Source-specific accessors that integrate TimeWindow with calculation methods for real-time data analysis.

### ChainlinkAccessor

Chainlink/Polymarket data accessor with price calculations only (no volume data).

```python
from polyalpha.calculations import ChainlinkAccessor
from polyalpha.windows import TimeWindow

# Create accessor with TimeWindow
window = TimeWindow(max_age=120)
accessor = ChainlinkAccessor(window)

# Update with Chainlink prices
accessor.update(67850.0)
accessor.update(67900.0)

# Price calculations
change_pct = accessor.change_pct(30)    # % change over 30 seconds
trend = accessor.trend(60)              # trend direction
direction = accessor.direction(30)      # "up"/"down"/"flat"
volatility = accessor.volatility(120)   # price volatility

# Convenience methods
is_rising = accessor.is_rising(30)     # True if price increased
is_falling = accessor.is_falling(30)    # True if price decreased
is_fresh = accessor.is_fresh(60)        # True if data is recent
is_valid = accessor.is_valid_price()   # True if price is valid

# Direct TimeWindow access
latest = accessor.value                 # latest price
age = accessor.age_s                   # seconds since last update
```

#### Chainlink-Specific Methods

- `asset` (str): Get/set the asset symbol (default: "BTC")
- `is_fresh(max_age_seconds=60)`: Check if data is recent
- `is_valid_price()`: Check if current price is valid (exists and positive)
- `price_change_since(seconds)`: Absolute price change over time period
- `price_change_pct_since(seconds)`: Percentage price change over time period
- `is_rising(seconds)`: Check if price is increasing over time period
- `is_falling(seconds)`: Check if price is decreasing over time period

### BinanceAccessor Integration

The existing `BinanceAccessor` in `bot_hub.py` has been enhanced with calculation library integration:

```python
# Enhanced BinanceAccessor methods
ctx.binance.change_pct(3)        # % change over 3 candles
ctx.binance.change_abs(3)        # absolute change over 3 candles
ctx.binance.trend(3)             # trend direction
ctx.binance.direction(3)         # "up"/"down"/"flat"
ctx.binance.volatility(10)       # price volatility

# Volume calculations (Binance has volume data)
ctx.binance.vol_ratio(10)        # current / avg volume
ctx.binance.volume_trend(5)      # INCREASING/DECREASING/STABLE
ctx.binance.volume_surge(2.0)    # detect volume spikes
ctx.binance.avg_volume(10)       # average volume
```

## Source Availability

Different data sources have different calculation capabilities:

| Data Source | Price Calculations | Volume Calculations |
|-------------|-------------------|-------------------|
| **Chainlink** | ✅ All price calculations | ❌ No volume data |
| **Binance** | ✅ All price calculations | ✅ All volume calculations |
| **Coinbase** | ✅ All price calculations (future) | ✅ All volume calculations (future) |

## Usage Examples

### Basic Price Analysis

```python
from polyalpha.calculations import MarketCalculations

price_data = [100.0, 105.0, 103.0, 108.0, 102.0]

# Analyze price changes
change_1 = MarketCalculations.change_pct(price_data, period=1)
change_2 = MarketCalculations.change_pct(price_data, period=2)

# Determine trend
trend = MarketCalculations.trend(price_data, period=3, threshold=0.02)

# Calculate volatility
volatility = MarketCalculations.volatility(price_data, period=5)

# Get price range
price_range = MarketCalculations.range(price_data, period=5)
```

### Volume Analysis

```python
from polyalpha.calculations import VolumeCalculations

volume_data = [100.0, 120.0, 110.0, 130.0, 250.0]

# Check for volume surge
is_surge = VolumeCalculations.volume_surge(volume_data, multiplier=2.0, period=4)

# Get volume trend
trend = VolumeCalculations.volume_trend(volume_data, period=3, threshold=0.1)

# Calculate volume ratio
vol_ratio = VolumeCalculations.vol_ratio(volume_data, period=3)
```

### Real-Time Chainlink Analysis

```python
from polyalpha.calculations import ChainlinkAccessor
from polyalpha.windows import TimeWindow

window = TimeWindow(max_age=120)
accessor = ChainlinkAccessor(window)

# Simulate Chainlink price updates
for price in [67850.0, 67900.0, 67875.0, 67925.0]:
    accessor.update(price)
    
    # Real-time analysis
    if accessor.is_rising(30):
        print("Price is rising")
    
    if accessor.volatility(60) > 0.01:
        print("High volatility detected")
```

## Testing

The calculations library includes comprehensive unit tests:

```bash
# Run all calculation tests
python -m pytest tests/unit/calculations/ -v

# Run specific test files
python -m pytest tests/unit/calculations/test_market_calculations.py -v
python -m pytest tests/unit/calculations/test_volume_calculations.py -v
python -m pytest tests/unit/calculations/test_base_accessor.py -v
python -m pytest tests/unit/calculations/test_chainlink_accessor.py -v
```

## Architecture

The calculations library follows a modular architecture:

```
src/polyalpha/calculations/
├── __init__.py                 # Public API exports
├── market_calculations.py      # Universal price calculations
├── volume_calculations.py      # Volume-specific calculations
├── base_accessor.py            # Base class with TimeWindow integration
└── chainlink_accessor.py       # Chainlink-specific accessor
```

### Design Principles

1. **Modularity**: Each calculation type has its own module
2. **Source-aware**: Accessors adapt to available data (price-only vs price+volume)
3. **Extensibility**: Easy to add new data sources (Coinbase, etc.)
4. **Type safety**: Uses type hints throughout
5. **Well-tested**: Comprehensive unit test coverage

## Future Enhancements

Planned additions to the calculations library:

- **CoinbaseAccessor**: Full price + volume calculations for Coinbase data
- **Additional calculations**: More advanced technical indicators
- **Performance optimizations**: Caching for frequently used calculations
- **Cross-source calculations**: Arbitrage detection between data sources
