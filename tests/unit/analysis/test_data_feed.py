"""
DataFeed and DataFeedConfig tests — run with: pytest tests/unit/analysis/test_data_feed.py
"""

import os
import tempfile
from datetime import datetime, timezone

import pandas as pd
import pytest

from polyalpha.analysis.data_feed import DataFeed, DataFeedConfig, TIMEFRAME_MAP


@pytest.mark.unit
class TestDataFeedConfig:
    """Test DataFeedConfig dataclass validation."""

    def test_default_config(self):
        cfg = DataFeedConfig()
        assert cfg.source == "scraping"
        assert cfg.timeframe == "5m"
        assert cfg.lookback_periods == 500
        assert cfg.use_cache is True
        assert "BTC" in cfg.asset_map

    def test_valid_source_binance(self):
        cfg = DataFeedConfig(source="binance")
        assert cfg.source == "binance"

    def test_valid_source_chainlink(self):
        cfg = DataFeedConfig(source="chainlink")
        assert cfg.source == "chainlink"

    def test_valid_source_websocket(self):
        cfg = DataFeedConfig(source="websocket")
        assert cfg.source == "websocket"

    def test_valid_source_custom(self):
        cfg = DataFeedConfig(source="custom", custom_url="http://example.com/api")
        assert cfg.source == "custom"

    def test_invalid_source(self):
        with pytest.raises(ValueError, match="Invalid source"):
            DataFeedConfig(source="invalid_source")

    def test_invalid_timeframe(self):
        with pytest.raises(ValueError, match="Invalid timeframe"):
            DataFeedConfig(timeframe="7m")

    def test_zero_lookback(self):
        with pytest.raises(ValueError, match="lookback_periods must be positive"):
            DataFeedConfig(lookback_periods=0)

    def test_negative_lookback(self):
        with pytest.raises(ValueError, match="lookback_periods must be positive"):
            DataFeedConfig(lookback_periods=-5)

    def test_custom_source_missing_url(self):
        with pytest.raises(ValueError, match="custom_url required"):
            DataFeedConfig(source="custom")

    def test_cache_dir_default_set(self):
        cfg = DataFeedConfig(use_cache=True, cache_dir=None)
        assert cfg.cache_dir is not None
        assert ".polyalpha" in cfg.cache_dir
        assert "cache" in cfg.cache_dir

    def test_cache_dir_explicit(self):
        cfg = DataFeedConfig(use_cache=True, cache_dir="/tmp/test_cache")
        assert cfg.cache_dir == "/tmp/test_cache"

    def test_cache_disabled_no_dir_set(self):
        cfg = DataFeedConfig(use_cache=False, cache_dir=None)
        assert cfg.cache_dir is None


@pytest.mark.unit
class TestDataFeedInit:
    """Test DataFeed initialization."""

    def test_init_default_cache_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = DataFeedConfig(use_cache=True, cache_dir=tmp)
            feed = DataFeed(cfg)
            assert os.path.isdir(tmp)
            assert feed.config.cache_dir == tmp

    def test_init_no_cache_no_dir(self):
        cfg = DataFeedConfig(use_cache=False, cache_dir=None)
        feed = DataFeed(cfg)
        assert feed._data is None
        assert feed._current_asset is None

    def test_init_ws_lock_created(self):
        cfg = DataFeedConfig()
        feed = DataFeed(cfg)
        assert feed._ws_lock is not None

    def test_init_default_data(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        assert feed._data is None
        assert feed._current_asset is None
        assert feed._ws_cache == []


@pytest.mark.unit
class TestDataFeedFetch:
    """Test DataFeed.fetch validation and caching."""

    def test_fetch_invalid_asset(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="not in asset_map"):
            feed.fetch("UNKNOWN")

    def test_fetch_case_insensitive_asset(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="not in asset_map"):
            feed.fetch("not_a_real_asset")

    def test_load_from_cache_no_cache_dir(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        assert feed._load_from_cache("BTC") is None

    def test_load_from_cache_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = DataFeedConfig(use_cache=True, cache_dir=tmp)
            feed = DataFeed(cfg)
            assert feed._load_from_cache("BTC") is None

    def test_save_and_load_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = DataFeedConfig(use_cache=True, cache_dir=tmp)
            feed = DataFeed(cfg)
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(["2025-01-01"]),
                "open": [50.0],
                "high": [51.0],
                "low": [49.0],
                "close": [50.5],
                "volume": [1000.0],
            })
            feed._save_to_cache("ETH", df)
            cache_path = feed._get_cache_path("ETH")
            assert os.path.exists(cache_path)

            loaded = feed._load_from_cache("ETH")
            assert loaded is not None
            assert len(loaded) == 1
            assert loaded["close"].iloc[0] == 50.5

    def test_get_cache_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = DataFeedConfig(use_cache=True, cache_dir=tmp, source="binance", timeframe="5m")
            feed = DataFeed(cfg)
            path = feed._get_cache_path("BTC")
            assert "binance_BTC_5m.csv" in path
            assert tmp in path

    def test_get_timeframe_seconds(self):
        cfg = DataFeedConfig(timeframe="5m")
        feed = DataFeed(cfg)
        assert feed._get_timeframe_seconds() == 300

    def test_get_timeframe_seconds_1m(self):
        cfg = DataFeedConfig(timeframe="1m")
        feed = DataFeed(cfg)
        assert feed._get_timeframe_seconds() == 60

    def test_get_timeframe_seconds_fallback(self):
        cfg = DataFeedConfig()
        feed = DataFeed(cfg)
        assert feed._get_timeframe_seconds() == 300


@pytest.mark.unit
class TestDataFeedUpdate:
    """Test DataFeed.update method."""

    def test_update_adds_tick(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed.update(100.0)
        assert len(feed._ws_cache) == 1
        assert feed._ws_cache[0]["price"] == 100.0

    def test_update_with_timestamp(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        feed.update(50.0, timestamp=ts)
        assert feed._ws_cache[0]["timestamp"] == ts

    def test_update_maintains_max_size(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        from polyalpha.core.constants import DEFAULT_CACHE_MAX_TICKS
        for i in range(DEFAULT_CACHE_MAX_TICKS + 10):
            feed.update(float(i))
        assert len(feed._ws_cache) == DEFAULT_CACHE_MAX_TICKS
        assert feed._ws_cache[0]["price"] == 10.0
        assert feed._ws_cache[-1]["price"] == float(DEFAULT_CACHE_MAX_TICKS + 9)


@pytest.mark.unit
class TestDataFeedResample:
    """Test DataFeed.resample method."""

    @pytest.fixture
    def sample_data(self):
        dates = pd.date_range("2025-01-01", periods=10, freq="1h")
        return pd.DataFrame({
            "timestamp": dates,
            "open": [float(i) for i in range(10)],
            "high": [float(i + 1) for i in range(10)],
            "low": [float(i - 1) for i in range(10)],
            "close": [float(i + 0.5) for i in range(10)],
            "volume": [100.0 * i for i in range(10)],
        })

    def test_resample_raises_if_no_data(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="No data available"):
            feed.resample("1h")

    def test_resample_raises_invalid_timeframe(self, sample_data):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed._data = sample_data
        with pytest.raises(ValueError, match="Invalid timeframe"):
            feed.resample("7m")

    def test_resample_1h_to_4h(self, sample_data):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed._data = sample_data
        result = feed.resample("4h")
        assert len(result) > 0
        assert "timestamp" in result.columns
        assert "open" in result.columns
        assert "high" in result.columns
        assert "low" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns


@pytest.mark.unit
class TestDataFeedGetLatest:
    """Test DataFeed.get_latest method."""

    def test_get_latest_raises_if_no_data(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="No data available"):
            feed.get_latest()

    def test_get_latest_default_n(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed._data = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "close": [50.0, 51.0],
        })
        result = feed.get_latest()
        assert len(result) == 1
        assert result["close"].iloc[0] == 51.0

    def test_get_latest_n_2(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        feed._data = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "close": [50.0, 51.0, 52.0],
        })
        result = feed.get_latest(2)
        assert len(result) == 2
        assert result["close"].iloc[0] == 51.0


@pytest.mark.unit
class TestDataFeedIO:
    """Test DataFeed CSV and normalize methods."""

    def test_normalize_ohlcv(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        df = pd.DataFrame({
            "timestamp": ["2025-01-01"],
            "open": ["50.0"],
            "high": ["51.0"],
            "low": ["49.0"],
            "close": ["50.5"],
            "volume": ["1000"],
        })
        result = feed._normalize_ohlcv(df)
        assert result["open"].dtype == float
        assert result["close"].dtype == float
        assert result["volume"].dtype == float
        assert result["timestamp"].dtype.kind == "M"

    def test_to_csv_raises_if_no_data(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="No data available"):
            feed.to_csv("/tmp/nonexistent.csv")

    def test_to_csv_and_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = DataFeedConfig(use_cache=False)
            feed = DataFeed(cfg)
            feed._data = pd.DataFrame({
                "timestamp": pd.to_datetime(["2025-01-01"]),
                "open": [50.0],
                "high": [51.0],
                "low": [49.0],
                "close": [50.5],
                "volume": [1000.0],
            })
            path = os.path.join(tmp, "test.csv")
            feed.to_csv(path)
            assert os.path.exists(path)

            feed2 = DataFeed(cfg)
            loaded = feed2.from_csv(path)
            assert len(loaded) == 1
            assert loaded["close"].iloc[0] == 50.5
            assert loaded["timestamp"].dtype.kind == "M"

    def test_fetch_websocket_cache_raises_if_empty(self):
        cfg = DataFeedConfig(use_cache=False)
        feed = DataFeed(cfg)
        with pytest.raises(ValueError, match="No WebSocket cache data"):
            feed._fetch_websocket_cache("BTC")

    def test_fetch_websocket_cache_with_data(self):
        cfg = DataFeedConfig(use_cache=False, timeframe="1h")
        feed = DataFeed(cfg)
        feed.update(100.0, timestamp=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        feed.update(102.0, timestamp=datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc))
        result = feed._fetch_websocket_cache("BTC")
        assert len(result) > 0
        assert "open" in result.columns
        assert "close" in result.columns

    @pytest.mark.unit
    def test_all_timeframe_map_entries_present(self):
        expected = {"1m", "5m", "15m", "1h", "4h", "1d"}
        assert set(TIMEFRAME_MAP.keys()) == expected
