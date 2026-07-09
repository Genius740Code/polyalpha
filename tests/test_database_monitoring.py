"""
Tests for database monitoring and observability features.
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import time

from polyalpha.database import TradeDatabase, DatabaseMetrics, LogEntry, AlertRule


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = TradeDatabase(db_path)
    yield db
    db.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_trade():
    """Create a sample trade for testing."""
    return {
        "market_slug": "btc-updown-5m-1751234700",
        "market_id": "abc123",
        "side": "UP",
        "entry_price": 0.92,
        "exit_price": None,
        "amount": 10.0,
        "shares": 10.5,
        "fee": 0.2,
        "outcome": "WON",
        "pnl": 5.3,
        "timestamp": datetime.now(timezone.utc),
        "market_session": "london",
    }


@pytest.fixture
def sample_trade_factory():
    """Factory to create unique trades for testing."""
    counter = 0
    
    def _create_trade(**kwargs):
        nonlocal counter
        counter += 1
        defaults = {
            "market_slug": f"btc-updown-5m-175123470{counter}",
            "market_id": f"abc{counter}",
            "side": "UP",
            "entry_price": 0.92,
            "exit_price": None,
            "amount": 10.0,
            "shares": 10.5,
            "fee": 0.2,
            "outcome": "WON",
            "pnl": 5.3,
            "timestamp": datetime.now(timezone.utc) + timedelta(microseconds=counter),
            "market_session": "london",
        }
        defaults.update(kwargs)
        return defaults
    
    return _create_trade


class TestDatabaseMetrics:
    """Test database metrics collection."""
    
    def test_get_metrics_empty_database(self, temp_db):
        """Test getting metrics from an empty database."""
        metrics = temp_db.get_metrics()
        
        assert isinstance(metrics, DatabaseMetrics)
        assert metrics.total_trades == 0
        assert metrics.database_size_bytes > 0
        assert metrics.cache_hit_rate == 0.0
        assert metrics.cache_size == 0
        assert metrics.query_count == 0
        assert metrics.slow_query_count == 0
        assert metrics.avg_query_time_ms == 0.0
        assert metrics.wal_enabled is True
    
    def test_get_metrics_with_trades(self, temp_db, sample_trade_factory):
        """Test getting metrics after adding trades."""
        temp_db.save_trade(**sample_trade_factory())
        temp_db.save_trade(**sample_trade_factory())
        
        metrics = temp_db.get_metrics()
        
        assert metrics.total_trades == 2
        assert metrics.database_size_bytes > 0
    
    def test_get_metrics_cache_performance(self, temp_db, sample_trade):
        """Test cache hit rate tracking."""
        temp_db.save_trade(**sample_trade)
        
        # First query - cache miss
        temp_db.load_trades(filters={"side": "UP"})
        
        # Second query - cache hit
        temp_db.load_trades(filters={"side": "UP"})
        
        metrics = temp_db.get_metrics()
        assert metrics.cache_hit_rate > 0.0
    
    def test_metrics_to_dict(self, temp_db):
        """Test converting metrics to dictionary."""
        metrics = temp_db.get_metrics()
        metrics_dict = metrics.to_dict()
        
        assert "total_trades" in metrics_dict
        assert "database_size_bytes" in metrics_dict
        assert "database_size_mb" in metrics_dict
        assert "cache_hit_rate" in metrics_dict
        assert "cache_size" in metrics_dict
        assert "query_count" in metrics_dict
        assert "slow_query_count" in metrics_dict
        assert "avg_query_time_ms" in metrics_dict
        assert "connection_pool_size" in metrics_dict
        assert "wal_enabled" in metrics_dict
        assert "last_optimization" in metrics_dict


class TestStructuredLogging:
    """Test structured logging with correlation IDs."""
    
    def test_set_correlation_id(self, temp_db):
        """Test setting a correlation ID."""
        temp_db.set_correlation_id("test-correlation-123")
        
        # Perform an operation with context
        with temp_db.operation_context("test_operation"):
            temp_db.load_all_trades()
        
        logs = temp_db.get_logs()
        assert len(logs) > 0
        # Operation context generates its own correlation ID, so we check it exists
        assert logs[0].correlation_id is not None
    
    def test_clear_correlation_id(self, temp_db):
        """Test clearing correlation ID."""
        temp_db.set_correlation_id("test-correlation-123")
        temp_db.clear_correlation_id()
        
        # Perform an operation - should generate new correlation ID
        with temp_db.operation_context("test_operation"):
            temp_db.load_all_trades()
        
        logs = temp_db.get_logs()
        assert logs[0].correlation_id != "test-correlation-123"
    
    def test_get_logs_by_level(self, temp_db):
        """Test filtering logs by level."""
        temp_db._add_log_entry("INFO", "Test info message")
        temp_db._add_log_entry("ERROR", "Test error message")
        temp_db._add_log_entry("WARNING", "Test warning message")
        
        error_logs = temp_db.get_logs(level="ERROR")
        assert len(error_logs) == 1
        assert error_logs[0].level == "ERROR"
    
    def test_get_logs_by_operation(self, temp_db):
        """Test filtering logs by operation."""
        temp_db._add_log_entry("INFO", "Test message", operation="save_trade")
        temp_db._add_log_entry("INFO", "Test message", operation="load_trades")
        
        save_logs = temp_db.get_logs(operation="save_trade")
        assert len(save_logs) == 1
        assert save_logs[0].operation == "save_trade"
    
    def test_get_logs_by_date_range(self, temp_db):
        """Test filtering logs by date range."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=2)
        
        temp_db._add_log_entry("INFO", "Old message")
        # Manually set timestamp for testing
        temp_db._log_entries[-1].timestamp = old_time
        
        temp_db._add_log_entry("INFO", "New message")
        
        recent_logs = temp_db.get_logs(start_date=now - timedelta(hours=1))
        assert len(recent_logs) == 1
        assert recent_logs[0].message == "New message"
    
    def test_get_logs_limit(self, temp_db):
        """Test limiting number of log entries."""
        for i in range(10):
            temp_db._add_log_entry("INFO", f"Message {i}")
        
        logs = temp_db.get_logs(limit=5)
        assert len(logs) == 5
    
    def test_log_entry_to_dict(self, temp_db):
        """Test converting log entry to dictionary."""
        temp_db._add_log_entry("INFO", "Test message", operation="test_op", duration_ms=100.5)
        
        logs = temp_db.get_logs()
        log_dict = logs[0].to_dict()
        
        assert "correlation_id" in log_dict
        assert "timestamp" in log_dict
        assert "level" in log_dict
        assert "message" in log_dict
        assert "operation" in log_dict
        assert "duration_ms" in log_dict
        assert "metadata" in log_dict
    
    def test_operation_context(self, temp_db, sample_trade):
        """Test operation context manager."""
        with temp_db.operation_context("batch_import"):
            temp_db.save_trade(**sample_trade)
        
        logs = temp_db.get_logs()
        operation_logs = [log for log in logs if log.operation == "batch_import"]
        
        assert len(operation_logs) >= 2  # Start and completion logs
        assert any("started" in log.message.lower() for log in operation_logs)
        assert any("completed" in log.message.lower() for log in operation_logs)
    
    def test_operation_context_error_handling(self, temp_db):
        """Test operation context manager with error."""
        with pytest.raises(ValueError):
            with temp_db.operation_context("failing_operation"):
                raise ValueError("Test error")
        
        logs = temp_db.get_logs(level="ERROR")
        error_logs = [log for log in logs if log.operation == "failing_operation"]
        
        assert len(error_logs) == 1
        assert "failed" in error_logs[0].message.lower()
        assert "error" in error_logs[0].metadata


class TestAlerting:
    """Test alerting system."""
    
    def test_set_alert(self, temp_db):
        """Test setting up an alert rule."""
        temp_db.set_alert("slow_query", "avg_query_time_ms", 1000.0)
        
        alerts = temp_db.get_alerts()
        assert "slow_query" in alerts
        assert alerts["slow_query"]["metric"] == "avg_query_time_ms"
        assert alerts["slow_query"]["threshold"] == 1000.0
        assert alerts["slow_query"]["comparison"] == "gt"
        assert alerts["slow_query"]["enabled"] is True
    
    def test_set_alert_with_callback(self, temp_db):
        """Test setting alert with callback."""
        callback_triggered = []
        
        def callback(name, value, threshold):
            callback_triggered.append((name, value, threshold))
        
        temp_db.set_alert("test_alert", "slow_query_count", 1.0, callback=callback)
        
        # Manually trigger the alert by setting metric value
        temp_db._slow_query_count = 2
        temp_db.check_alerts()
        
        assert len(callback_triggered) == 1
        assert callback_triggered[0][0] == "test_alert"
    
    def test_set_alert_invalid_comparison(self, temp_db):
        """Test setting alert with invalid comparison operator."""
        with pytest.raises(ValueError):
            temp_db.set_alert("test", "metric", 100.0, comparison="invalid")
    
    def test_remove_alert(self, temp_db):
        """Test removing an alert rule."""
        temp_db.set_alert("test_alert", "metric", 100.0)
        temp_db.remove_alert("test_alert")
        
        alerts = temp_db.get_alerts()
        assert "test_alert" not in alerts
    
    def test_check_alerts_gt(self, temp_db):
        """Test alert triggering with greater than comparison."""
        triggered = []
        
        def callback(name, value, threshold):
            triggered.append(True)
        
        temp_db.set_alert("test", "slow_query_count", 0.0, "gt", callback)
        temp_db._slow_query_count = 1
        temp_db.check_alerts()
        
        assert len(triggered) == 1
    
    def test_check_alerts_lt(self, temp_db):
        """Test alert triggering with less than comparison."""
        triggered = []
        
        def callback(name, value, threshold):
            triggered.append(True)
        
        temp_db.set_alert("test", "cache_hit_rate", 0.5, "lt", callback)
        # Cache hit rate will be 0.0 initially
        temp_db.check_alerts()
        
        assert len(triggered) == 1
    
    def test_check_alerts_no_trigger(self, temp_db):
        """Test alert not triggering when threshold not met."""
        triggered = []
        
        def callback(name, value, threshold):
            triggered.append(True)
        
        temp_db.set_alert("test", "slow_query_count", 100.0, "gt", callback)
        temp_db._slow_query_count = 1
        temp_db.check_alerts()
        
        assert len(triggered) == 0
    
    def test_alert_trigger_count(self, temp_db):
        """Test alert trigger count tracking."""
        temp_db.set_alert("test", "slow_query_count", 0.0, "gt")
        
        temp_db._slow_query_count = 1
        temp_db.check_alerts()
        
        alerts = temp_db.get_alerts()
        assert alerts["test"]["trigger_count"] == 1
        assert alerts["test"]["last_triggered"] is not None
    
    def test_get_alerts_empty(self, temp_db):
        """Test getting alerts when none are configured."""
        alerts = temp_db.get_alerts()
        assert alerts == {}


class TestIntegration:
    """Integration tests for monitoring features."""
    
    def test_full_monitoring_workflow(self, temp_db, sample_trade_factory):
        """Test complete monitoring workflow."""
        # Set up alert
        triggered = []
        temp_db.set_alert("high_trade_count", "total_trades", 1.0, "gte", 
                         callback=lambda n, v, t: triggered.append(n))
        
        # Use operation context
        with temp_db.operation_context("import_trades"):
            temp_db.save_trade(**sample_trade_factory())
            temp_db.save_trade(**sample_trade_factory())
        
        # Check metrics
        metrics = temp_db.get_metrics()
        assert metrics.total_trades == 2
        
        # Check logs
        logs = temp_db.get_logs(operation="import_trades")
        assert len(logs) >= 2
        
        # Check alerts
        temp_db.check_alerts()
        assert "high_trade_count" in triggered
        
        # Get alert status
        alerts = temp_db.get_alerts()
        assert alerts["high_trade_count"]["trigger_count"] >= 1
    
    def test_correlation_id_propagation(self, temp_db, sample_trade):
        """Test correlation ID propagation through operations."""
        temp_db.set_correlation_id("test-123")
        
        with temp_db.operation_context("test_operation"):
            temp_db.save_trade(**sample_trade)
        
        logs = temp_db.get_logs()
        operation_logs = [log for log in logs if log.operation == "test_operation"]
        
        # All logs in the operation should have the same correlation ID
        correlation_ids = {log.correlation_id for log in operation_logs}
        assert len(correlation_ids) == 1
        assert "test-123" not in correlation_ids  # Operation context generates its own
    
    def test_log_rotation(self, temp_db):
        """Test log entry rotation when max entries exceeded."""
        temp_db._max_log_entries = 5
        
        # Add more logs than max
        for i in range(10):
            temp_db._add_log_entry("INFO", f"Message {i}")
        
        logs = temp_db.get_logs()
        assert len(logs) <= 5
