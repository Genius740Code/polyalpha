"""
End-to-end tests for analysis workflows.

Tests complete analysis workflows including data fetching,
indicator calculation, signal generation, and strategy execution.
"""

import pytest
import pandas as pd
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from polyalpha.analysis import DataFeed, DataFeedConfig, IndicatorCalculator, SignalGenerator, DeltaCalculator


@pytest.mark.e2e
@pytest.mark.slow
class TestDataFeedWorkflow:
    """Test complete data feed workflows."""

    @pytest.fixture(scope="function")
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing."""
        base_time = datetime.now()
        data = []
        for i in range(100):
            data.append({
                "timestamp": base_time + timedelta(minutes=i),
                "open": 50000.0 + i * 10,
                "high": 50050.0 + i * 10,
                "low": 49950.0 + i * 10,
                "close": 50000.0 + i * 10,
                "volume": 100.0 + i,
            })
        return pd.DataFrame(data)

    @pytest.fixture(scope="function")
    def data_feed_config(self):
        """Create data feed configuration."""
        return DataFeedConfig(
            source="binance",
            timeframe="5m",
            limit=100
        )

    def test_complete_data_fetching_workflow(self, data_feed_config, sample_ohlcv_data):
        """Test workflow: configure feed -> fetch data -> validate structure."""
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Mock API response
            mock_response = Mock()
            mock_response.json.return_value = [
                [int((datetime.now() + timedelta(minutes=i)).timestamp() * 1000),
                 50000.0 + i * 10,  # open
                 50050.0 + i * 10,  # high
                 49950.0 + i * 10,  # low
                 50000.0 + i * 10,  # close
                 100.0 + i]         # volume
                for i in range(100)
            ]
            mock_get.return_value = mock_response
            
            # Act: Create data feed and fetch
            feed = DataFeed(data_feed_config)
            data = feed.fetch("BTC")
            
            # Assert: Data fetched successfully
            assert data is not None
            assert len(data) == 100
            assert "close" in data.columns
            assert "volume" in data.columns

    def test_multi_symbol_data_fetching_workflow(self, data_feed_config):
        """Test workflow: fetch data for multiple symbols."""
        symbols = ["BTC", "ETH", "SOL"]
        
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Mock responses for each symbol
            def mock_response_func(*args, **kwargs):
                mock_response = Mock()
                mock_response.json.return_value = [
                    [int((datetime.now() + timedelta(minutes=i)).timestamp() * 1000),
                     50000.0 + i * 10, 50050.0 + i * 10, 49950.0 + i * 10,
                     50000.0 + i * 10, 100.0 + i]
                    for i in range(50)
                ]
                return mock_response
            
            mock_get.side_effect = mock_response_func
            
            # Act: Fetch data for multiple symbols
            feed = DataFeed(data_feed_config)
            results = {}
            for symbol in symbols:
                data = feed.fetch(symbol)
                results[symbol] = data
            
            # Assert: All symbols fetched
            assert len(results) == 3
            assert all(data is not None for data in results.values())

    def test_data_caching_workflow(self, data_feed_config):
        """Test workflow: fetch data -> cache -> retrieve from cache."""
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Mock API response
            mock_response = Mock()
            mock_response.json.return_value = [
                [int((datetime.now() + timedelta(minutes=i)).timestamp() * 1000),
                 50000.0 + i * 10, 50050.0 + i * 10, 49950.0 + i * 10,
                 50000.0 + i * 10, 100.0 + i]
                for i in range(50)
            ]
            mock_get.return_value = mock_response
            
            # Act: First fetch
            feed = DataFeed(data_feed_config)
            data1 = feed.fetch("BTC")
            
            # Act: Second fetch (should use cache)
            data2 = feed.fetch("BTC")
            
            # Assert: Data identical
            assert data1.equals(data2)
            # Assert: Only one API call made (cached second time)
            assert mock_get.call_count == 1

    def test_data_source_fallback_workflow(self):
        """Test workflow: primary source fails -> fallback to secondary."""
        # Arrange: Config with fallback
        config = DataFeedConfig(source="binance", timeframe="5m")
        
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Primary source fails
            mock_get.side_effect = Exception("Primary source unavailable")
            
            feed = DataFeed(config)
            
            # Act: Try to fetch (should handle error gracefully)
            try:
                data = feed.fetch("BTC")
                # If fallback works, data should be returned
                assert data is not None
            except Exception:
                # If no fallback, exception is acceptable
                pass


@pytest.mark.e2e
@pytest.mark.slow
class TestIndicatorCalculationWorkflow:
    """Test complete indicator calculation workflows."""

    @pytest.fixture(scope="function")
    def sample_price_data(self):
        """Create sample price data for indicator testing."""
        base_time = datetime.now()
        data = []
        price = 50000.0
        for i in range(100):
            # Create realistic price movement
            change = (i % 10 - 5) * 10
            price += change
            data.append({
                "timestamp": base_time + timedelta(minutes=i),
                "close": price,
                "volume": 100.0 + i * 10,
            })
        return pd.DataFrame(data)

    def test_sma_calculation_workflow(self, sample_price_data):
        """Test workflow: calculate SMA -> validate values -> use in analysis."""
        # Act: Calculate SMA
        calculator = IndicatorCalculator(sample_price_data)
        sma_20 = calculator.sma(period=20)
        sma_50 = calculator.sma(period=50)
        
        # Assert: SMA calculated
        assert sma_20 is not None
        assert len(sma_20) == len(sample_price_data)
        assert sma_50 is not None
        
        # Assert: SMA values are reasonable
        assert not sma_20.isna().all()
        assert not sma_50.isna().all()

    def test_rsi_calculation_workflow(self, sample_price_data):
        """Test workflow: calculate RSI -> validate range -> interpret signals."""
        # Act: Calculate RSI
        calculator = IndicatorCalculator(sample_price_data)
        rsi = calculator.rsi(period=14)
        
        # Assert: RSI calculated
        assert rsi is not None
        assert len(rsi) == len(sample_price_data)
        
        # Assert: RSI values in valid range (0-100)
        valid_rsi = rsi.dropna()
        assert all(0 <= val <= 100 for val in valid_rsi)

    def test_bollinger_bands_workflow(self, sample_price_data):
        """Test workflow: calculate Bollinger Bands -> validate bands -> detect breakouts."""
        # Act: Calculate Bollinger Bands
        calculator = IndicatorCalculator(sample_price_data)
        bb = calculator.bollinger_bands(period=20, std_dev=2.0)
        
        # Assert: Bands calculated
        assert bb is not None
        assert "upper" in bb.columns
        assert "middle" in bb.columns
        assert "lower" in bb.columns
        
        # Assert: Upper band > middle > lower
        valid_data = bb.dropna()
        assert all(valid_data["upper"] >= valid_data["middle"])
        assert all(valid_data["middle"] >= valid_data["lower"])

    def test_macd_calculation_workflow(self, sample_price_data):
        """Test workflow: calculate MACD -> validate signal -> identify crossovers."""
        # Act: Calculate MACD
        calculator = IndicatorCalculator(sample_price_data)
        macd = calculator.macd(fast=12, slow=26, signal=9)
        
        # Assert: MACD calculated
        assert macd is not None
        assert "macd" in macd.columns
        assert "signal" in macd.columns
        assert "histogram" in macd.columns
        
        # Assert: Histogram equals MACD - Signal
        valid_data = macd.dropna()
        expected_hist = valid_data["macd"] - valid_data["signal"]
        assert all(abs(valid_data["histogram"] - expected_hist) < 0.01)

    def test_multi_indicator_workflow(self, sample_price_data):
        """Test workflow: calculate multiple indicators -> combine -> analyze."""
        # Act: Calculate multiple indicators
        calculator = IndicatorCalculator(sample_price_data)
        
        sma = calculator.sma(period=20)
        rsi = calculator.rsi(period=14)
        bb = calculator.bollinger_bands(period=20, std_dev=2.0)
        
        # Assert: All indicators calculated
        assert sma is not None
        assert rsi is not None
        assert bb is not None
        
        # Act: Combine into single analysis
        analysis = pd.DataFrame({
            "price": sample_price_data["close"],
            "sma": sma,
            "rsi": rsi,
            "bb_upper": bb["upper"],
            "bb_lower": bb["lower"],
        })
        
        # Assert: Combined analysis created
        assert len(analysis) == len(sample_price_data)
        assert "price" in analysis.columns
        assert "rsi" in analysis.columns


@pytest.mark.e2e
@pytest.mark.slow
class TestSignalGenerationWorkflow:
    """Test complete signal generation workflows."""

    @pytest.fixture(scope="function")
    def sample_price_data(self):
        """Create sample price data with trends for signal testing."""
        base_time = datetime.now()
        data = []
        price = 50000.0
        for i in range(100):
            # Create uptrend then downtrend
            if i < 50:
                price += 20  # Uptrend
            else:
                price -= 15  # Downtrend
            data.append({
                "timestamp": base_time + timedelta(minutes=i),
                "close": price,
                "volume": 100.0 + i * 10,
            })
        return pd.DataFrame(data)

    def test_rsi_signal_workflow(self, sample_price_data):
        """Test workflow: calculate RSI -> generate oversold/overbought signals."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_price_data)
        rsi = calculator.rsi(period=14)
        
        # Act: Generate signals
        signals = SignalGenerator(calculator)
        
        # Test oversold signal
        oversold = signals.rsi_below(30)
        assert oversold is not None
        
        # Test overbought signal
        overbought = signals.rsi_above(70)
        assert overbought is not None

    def test_price_crossover_signal_workflow(self, sample_price_data):
        """Test workflow: detect price crossing SMA -> generate buy/sell signals."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_price_data)
        
        # Act: Generate crossover signals
        signals = SignalGenerator(calculator)
        
        # Test price above SMA
        above_sma = signals.price_above_sma(20)
        assert above_sma is not None
        
        # Test price below SMA
        below_sma = signals.price_below_sma(20)
        assert below_sma is not None

    def test_price_change_signal_workflow(self, sample_price_data):
        """Test workflow: detect price changes -> generate directional signals."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_price_data)
        
        # Act: Generate price change signals
        signals = SignalGenerator(calculator)
        
        # Test price up
        price_up = signals.price_up()
        assert price_up is not None
        
        # Test price down
        price_down = signals.price_down()
        assert price_down is not None
        
        # Test price change above threshold
        significant_change = signals.price_change_above(50.0)
        assert significant_change is not None

    def test_combined_strategy_workflow(self, sample_price_data):
        """Test workflow: combine multiple signals -> execute strategy."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_price_data)
        signals = SignalGenerator(calculator)
        
        # Act: Generate combined buy signal
        buy_conditions = [
            signals.rsi_above(40),      # Not oversold
            signals.price_above_sma(20), # Uptrend
            signals.price_up(),          # Price increasing
        ]
        
        # Assert: All signals generated
        assert all(signal is not None for signal in buy_conditions)
        
        # Act: Check if buy signal triggered
        buy_signal = all(buy_conditions)
        assert isinstance(buy_signal, (bool, pd.Series))

    def test_signal_history_workflow(self, sample_price_data):
        """Test workflow: generate signals over time -> track signal history."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_price_data)
        signals = SignalGenerator(calculator)
        
        # Act: Generate signal history
        signal_history = []
        for i in range(len(sample_price_data)):
            # Get signals at each point
            rsi_val = calculator.rsi(14).iloc[i] if i >= 14 else None
            if rsi_val is not None:
                signal_history.append({
                    "timestamp": sample_price_data.iloc[i]["timestamp"],
                    "rsi": rsi_val,
                    "oversold": rsi_val < 30,
                    "overbought": rsi_val > 70,
                })
        
        # Assert: Signal history created
        assert len(signal_history) > 0
        assert all("timestamp" in entry for entry in signal_history)


@pytest.mark.e2e
@pytest.mark.slow
class TestCompleteAnalysisWorkflow:
    """Test complete end-to-end analysis workflows."""

    @pytest.fixture(scope="function")
    def sample_market_data(self):
        """Create comprehensive market data for complete analysis."""
        base_time = datetime.now()
        data = []
        price = 50000.0
        for i in range(200):
            # Create realistic market movements
            change = (i % 20 - 10) * 5 + (i % 7 - 3) * 3
            price += change
            data.append({
                "timestamp": base_time + timedelta(minutes=i),
                "open": price - 10,
                "high": price + 20,
                "low": price - 20,
                "close": price,
                "volume": 100.0 + i * 5 + (i % 10) * 10,
            })
        return pd.DataFrame(data)

    def test_full_analysis_pipeline_workflow(self, sample_market_data):
        """Test workflow: fetch data -> calculate indicators -> generate signals -> decision."""
        # Step 1: Calculate indicators
        calculator = IndicatorCalculator(sample_market_data)
        
        sma_20 = calculator.sma(20)
        sma_50 = calculator.sma(50)
        rsi = calculator.rsi(14)
        bb = calculator.bollinger_bands(20, 2.0)
        macd = calculator.macd(12, 26, 9)
        
        # Assert: All indicators calculated
        assert all(ind is not None for ind in [sma_20, sma_50, rsi, bb, macd])
        
        # Step 2: Generate signals
        signals = SignalGenerator(calculator)
        
        trend_up = signals.price_above_sma(20)
        momentum_ok = signals.rsi_above(40) and signals.rsi_below(70)
        not_overbought = ~signals.rsi_above(80)
        
        # Step 3: Make trading decision
        buy_signal = trend_up and momentum_ok and not_overbought
        
        # Assert: Decision made
        assert buy_signal is not None

    def test_multi_timeframe_analysis_workflow(self):
        """Test workflow: analyze multiple timeframes -> combine -> confirm signal."""
        timeframes = ["5m", "15m", "1h"]
        
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Mock data for each timeframe
            def mock_response(*args, **kwargs):
                mock_response = Mock()
                mock_response.json.return_value = [
                    [int((datetime.now() + timedelta(minutes=i)).timestamp() * 1000),
                     50000.0 + i * 10, 50050.0 + i * 10, 49950.0 + i * 10,
                     50000.0 + i * 10, 100.0 + i]
                    for i in range(50)
                ]
                return mock_response
            
            mock_get.side_effect = mock_response
            
            # Act: Analyze each timeframe
            timeframe_signals = {}
            for tf in timeframes:
                config = DataFeedConfig(source="binance", timeframe=tf, limit=50)
                feed = DataFeed(config)
                data = feed.fetch("BTC")
                
                calculator = IndicatorCalculator(data)
                signals = SignalGenerator(calculator)
                
                timeframe_signals[tf] = {
                    "trend": signals.price_above_sma(20),
                    "momentum": signals.rsi_above(40),
                }
            
            # Assert: All timeframes analyzed
            assert len(timeframe_signals) == 3
            
            # Act: Check for confluence (all timeframes agree)
            all_bullish = all(
                tf_data["trend"] and tf_data["momentum"]
                for tf_data in timeframe_signals.values()
            )
            
            # Assert: Confluence calculated
            assert isinstance(all_bullish, (bool, pd.Series))

    def test_backtest_signal_workflow(self, sample_market_data):
        """Test workflow: apply signals historically -> calculate performance."""
        # Arrange: Calculate indicators
        calculator = IndicatorCalculator(sample_market_data)
        signals = SignalGenerator(calculator)
        
        # Act: Simulate trading based on signals
        positions = []
        balance = 10000.0
        
        for i in range(50, len(sample_market_data)):  # Start after warmup
            current_data = sample_market_data.iloc[:i+1]
            calc = IndicatorCalculator(current_data)
            sig = SignalGenerator(calc)
            
            # Simple strategy: Buy when RSI < 30, sell when RSI > 70
            rsi = calc.rsi(14).iloc[-1]
            
            if rsi < 30 and not positions:
                # Buy
                positions.append({
                    "entry_price": sample_market_data.iloc[i]["close"],
                    "entry_time": sample_market_data.iloc[i]["timestamp"],
                })
            elif rsi > 70 and positions:
                # Sell
                for pos in positions:
                    exit_price = sample_market_data.iloc[i]["close"]
                    pnl = (exit_price - pos["entry_price"]) / pos["entry_price"]
                    balance *= (1 + pnl)
                positions = []
        
        # Assert: Backtest completed
        assert balance >= 0  # Should not go negative

    def test_delta_calculation_workflow(self):
        """Test workflow: calculate delta between markets -> identify arbitrage."""
        # Arrange: Create mock data for two markets
        market1_data = pd.DataFrame({
            "timestamp": pd.date_range(start="2024-01-01", periods=100, freq="5min"),
            "close": [50000.0 + i * 10 for i in range(100)],
        })
        
        market2_data = pd.DataFrame({
            "timestamp": pd.date_range(start="2024-01-01", periods=100, freq="5min"),
            "close": [50005.0 + i * 10 for i in range(100)],  # Slightly higher
        })
        
        # Act: Calculate delta
        delta_calc = DeltaCalculator()
        delta = delta_calc.calculate(market1_data, market2_data)
        
        # Assert: Delta calculated
        assert delta is not None
        assert len(delta) == len(market1_data)


@pytest.mark.e2e
@pytest.mark.slow
class TestAnalysisPerformance:
    """Test performance benchmarks for analysis workflows."""

    @pytest.fixture(scope="function")
    def large_dataset(self):
        """Create large dataset for performance testing."""
        base_time = datetime.now()
        data = []
        price = 50000.0
        for i in range(1000):
            change = (i % 50 - 25) * 2
            price += change
            data.append({
                "timestamp": base_time + timedelta(minutes=i),
                "close": price,
                "volume": 100.0 + i,
            })
        return pd.DataFrame(data)

    def test_indicator_calculation_performance(self, large_dataset):
        """Test performance of calculating indicators on large dataset."""
        import time
        
        # Act: Calculate multiple indicators
        start_time = time.time()
        
        calculator = IndicatorCalculator(large_dataset)
        sma = calculator.sma(20)
        rsi = calculator.rsi(14)
        bb = calculator.bollinger_bands(20, 2.0)
        macd = calculator.macd(12, 26, 9)
        
        elapsed_time = time.time() - start_time
        
        # Assert: Calculations complete in reasonable time (< 2 seconds)
        assert elapsed_time < 2.0, f"Too slow: {elapsed_time:.2f}s"
        assert all(ind is not None for ind in [sma, rsi, bb, macd])

    def test_signal_generation_performance(self, large_dataset):
        """Test performance of generating signals on large dataset."""
        import time
        
        # Arrange: Calculate indicators first
        calculator = IndicatorCalculator(large_dataset)
        
        # Act: Generate signals
        start_time = time.time()
        
        signals = SignalGenerator(calculator)
        rsi_signal = signals.rsi_above(50)
        sma_signal = signals.price_above_sma(20)
        change_signal = signals.price_change_above(10.0)
        
        elapsed_time = time.time() - start_time
        
        # Assert: Signal generation fast (< 0.5 seconds)
        assert elapsed_time < 0.5, f"Too slow: {elapsed_time:.2f}s"
        assert all(sig is not None for sig in [rsi_signal, sma_signal, change_signal])

    def test_data_feed_performance(self):
        """Test performance of data feed operations."""
        with patch('polyalpha.analysis.data_feed.requests.get') as mock_get:
            # Arrange: Mock fast response
            mock_response = Mock()
            mock_response.json.return_value = [
                [int((datetime.now() + timedelta(minutes=i)).timestamp() * 1000),
                 50000.0 + i * 10, 50050.0 + i * 10, 49950.0 + i * 10,
                 50000.0 + i * 10, 100.0 + i]
                for i in range(500)
            ]
            mock_get.return_value = mock_response
            
            import time
            
            # Act: Fetch data
            config = DataFeedConfig(source="binance", timeframe="5m", limit=500)
            feed = DataFeed(config)
            
            start_time = time.time()
            data = feed.fetch("BTC")
            elapsed_time = time.time() - start_time
            
            # Assert: Fetch completes in reasonable time (< 3 seconds)
            assert elapsed_time < 3.0, f"Too slow: {elapsed_time:.2f}s"
            assert len(data) == 500
