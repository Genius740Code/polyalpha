"""
Tests for error handling module — run with: pytest tests/unit/trading/test_error_handling.py
"""

import time
import json
import os
import pytest
from unittest.mock import Mock, patch, PropertyMock
from datetime import datetime, timezone

from polyalpha.trading.error_handling import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    ErrorRecoveryManager,
    RecoveryStrategy,
    RecoveryConfig,
    ManualInterventionRequiredError,
    GracefulDegradation,
    DegradationLevel,
    TransactionRollbackManager,
    DisasterRecovery,
    BackupConfig,
)
from polyalpha.core import (
    NetworkError,
    OrderRejected,
    OrderTimeout,
    TransientError,
    InsufficientBalance,
    InsufficientAllowance,
)


# ── CircuitBreaker Tests ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestCircuitBreaker:
    def test_initialization(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10)
        assert cb.name == "test"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.is_open is False
        assert cb.metrics["failure_rate"] == 0

    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitBreakerState.CLOSED

    def test_successful_call(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        result = cb.call(lambda x: x + 1, 5)
        assert result == 6

    def test_failure_opens_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)

        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        assert cb.state == CircuitBreakerState.CLOSED

        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open is True

    def test_open_circuit_blocks_requests(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)

        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        assert cb.is_open is True

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not reach")

    def test_mixed_exception_no_effect(self):
        cb = CircuitBreaker("test", failure_threshold=2, expected_exception=(NetworkError,))

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("unexpected")))

        assert cb.state == CircuitBreakerState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)

        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        assert cb.is_open is True
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.is_open is False

    def test_force_open(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.force_open()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.is_open is True

    def test_metrics_tracking(self):
        cb = CircuitBreaker("test", failure_threshold=3)

        cb.call(lambda: "ok")
        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        metrics = cb.metrics
        assert metrics["total_requests"] == 2
        assert metrics["total_successes"] == 1
        assert metrics["total_failures"] == 1
        assert metrics["failure_rate"] == 0.5

    def test_half_open_recovers(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01, success_threshold=1)

        with pytest.raises(NetworkError):
            cb.call(lambda: (_ for _ in ()).throw(NetworkError("fail")))

        assert cb.state == CircuitBreakerState.OPEN

        time.sleep(0.02)

        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitBreakerState.CLOSED


# ── ErrorRecoveryManager Tests ───────────────────────────────────────────────

@pytest.mark.unit
class TestErrorRecoveryManager:
    def test_initialization(self):
        mgr = ErrorRecoveryManager()
        assert mgr is not None

    def test_default_strategies_registered(self):
        mgr = ErrorRecoveryManager()
        config = mgr.get_recovery_config(TransientError("test"))
        assert config.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF
        assert config.max_attempts == 5

        config = mgr.get_recovery_config(NetworkError("test"))
        assert config.strategy == RecoveryStrategy.RETRY_WITH_JITTER

        config = mgr.get_recovery_config(OrderTimeout("test"))
        assert config.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF

        config = mgr.get_recovery_config(InsufficientAllowance("test"))
        assert config.strategy == RecoveryStrategy.MANUAL_INTERVENTION

        config = mgr.get_recovery_config(InsufficientBalance("test"))
        assert config.strategy == RecoveryStrategy.ABORT

        config = mgr.get_recovery_config(OrderRejected("test"))
        assert config.strategy == RecoveryStrategy.ABORT

    def test_register_custom_strategy(self):
        mgr = ErrorRecoveryManager()
        mgr.register_recovery_strategy(
            ValueError,
            RecoveryConfig(strategy=RecoveryStrategy.RETRY_IMMEDIATE, max_attempts=2),
        )
        config = mgr.get_recovery_config(ValueError("test"))
        assert config.strategy == RecoveryStrategy.RETRY_IMMEDIATE
        assert config.max_attempts == 2

    def test_unregistered_exception_uses_default(self):
        mgr = ErrorRecoveryManager()
        config = mgr.get_recovery_config(RuntimeError("test"))
        assert config.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF

    def test_execute_with_recovery_abort(self):
        mgr = ErrorRecoveryManager()

        with pytest.raises(InsufficientBalance):
            mgr.execute_with_recovery(lambda: (_ for _ in ()).throw(InsufficientBalance("no funds")))

    def test_execute_with_recovery_manual_intervention(self):
        mgr = ErrorRecoveryManager()

        with pytest.raises(ManualInterventionRequiredError):
            mgr.execute_with_recovery(lambda: (_ for _ in ()).throw(InsufficientAllowance("needs approval")))

    def test_execute_with_recovery_success(self):
        mgr = ErrorRecoveryManager()
        result = mgr.execute_with_recovery(lambda x: x * 2, 21)
        assert result == 42

    def test_execute_with_recovery_retry_immediate(self):
        mgr = ErrorRecoveryManager()
        mgr.register_recovery_strategy(
            ValueError,
            RecoveryConfig(strategy=RecoveryStrategy.RETRY_IMMEDIATE, max_attempts=2),
        )

        attempts = [0]
        def fail_once():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("transient")
            return "ok"

        result = mgr.execute_with_recovery(fail_once)
        assert result == "ok"
        assert attempts[0] == 2

    def test_execute_with_recovery_backoff(self):
        mgr = ErrorRecoveryManager()
        mgr.register_recovery_strategy(
            ValueError,
            RecoveryConfig(
                strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
                max_attempts=2,
                initial_delay=0.01,
                backoff_factor=2.0,
            ),
        )

        attempts = [0]
        def fail_always():
            attempts[0] += 1
            raise ValueError("persistent")

        with pytest.raises(ValueError):
            mgr.execute_with_recovery(fail_always)

        assert attempts[0] == 3

    def test_execute_with_recovery_fallback(self):
        mgr = ErrorRecoveryManager()
        mgr.register_recovery_strategy(
            ValueError,
            RecoveryConfig(
                strategy=RecoveryStrategy.FALLBACK_TO_ALTERNATIVE,
                fallback_func=lambda: "fallback_result",
            ),
        )

        def primary():
            raise ValueError("primary failed")

        result = mgr.execute_with_recovery(primary)
        assert result == "fallback_result"

    def test_execute_with_recovery_fallback_missing(self):
        mgr = ErrorRecoveryManager()
        mgr.register_recovery_strategy(
            ValueError,
            RecoveryConfig(strategy=RecoveryStrategy.FALLBACK_TO_ALTERNATIVE),
        )

        def primary():
            raise ValueError("primary failed")

        with pytest.raises(ValueError):
            mgr.execute_with_recovery(primary)


# ── GracefulDegradation Tests ────────────────────────────────────────────────

@pytest.mark.unit
class TestGracefulDegradation:
    def test_initialization(self):
        gd = GracefulDegradation()
        assert gd.current_level == DegradationLevel.NORMAL

    def test_initialization_custom(self):
        gd = GracefulDegradation(DegradationLevel.DEGRADED)
        assert gd.current_level == DegradationLevel.DEGRADED

    def test_config_property(self):
        gd = GracefulDegradation()
        config = gd.config
        assert config.max_orders_per_minute == 100
        assert config.disable_advanced_features is False

    def test_degrade(self):
        gd = GracefulDegradation()
        gd.degrade(DegradationLevel.DEGRADED, "Test degradation")
        assert gd.current_level == DegradationLevel.DEGRADED

    def test_degrade_only_downwards(self):
        gd = GracefulDegradation(DegradationLevel.DEGRADED)
        gd.degrade(DegradationLevel.NORMAL, "Should not upgrade")
        assert gd.current_level == DegradationLevel.DEGRADED

    def test_recover(self):
        gd = GracefulDegradation(DegradationLevel.CRITICAL)
        gd.recover(DegradationLevel.MINIMAL, "Recovering")
        assert gd.current_level == DegradationLevel.MINIMAL

    def test_recover_only_upwards(self):
        gd = GracefulDegradation(DegradationLevel.DEGRADED)
        gd.recover(DegradationLevel.CRITICAL, "Should not degrade")
        assert gd.current_level == DegradationLevel.DEGRADED

    def test_degradation_levels_progressive(self):
        gd = GracefulDegradation()
        levels = [DegradationLevel.DEGRADED, DegradationLevel.MINIMAL, DegradationLevel.CRITICAL]

        for level in levels:
            gd.degrade(level, "Progressive degradation")
            assert gd.current_level == level

    def test_can_execute_order_normal(self):
        gd = GracefulDegradation()
        can, reason = gd.can_execute_order()
        assert can is True

    def test_can_execute_order_critical(self):
        gd = GracefulDegradation(DegradationLevel.CRITICAL)
        can, reason = gd.can_execute_order()
        assert can is False
        assert "read-only" in reason

    def test_get_degradation_summary(self):
        gd = GracefulDegradation()
        gd.degrade(DegradationLevel.MINIMAL, "API failure")

        summary = gd.get_degradation_summary()
        assert summary["current_level"] == "minimal"
        assert summary["config"]["max_orders_per_minute"] == 5
        assert len(summary["history"]) == 1

    def test_degradation_history_tracking(self):
        gd = GracefulDegradation()
        gd.degrade(DegradationLevel.DEGRADED, "First")
        gd.degrade(DegradationLevel.MINIMAL, "Second")

        assert len(gd.get_degradation_summary()["history"]) == 2

    def test_config_at_each_level(self):
        configs = {
            DegradationLevel.NORMAL: (100, False, False),
            DegradationLevel.DEGRADED: (30, True, False),
            DegradationLevel.MINIMAL: (5, True, True),
            DegradationLevel.CRITICAL: (0, True, True),
        }

        for level, (max_orders, disable_advanced, disable_reporting) in configs.items():
            gd = GracefulDegradation(level)
            assert gd.config.max_orders_per_minute == max_orders
            assert gd.config.disable_advanced_features == disable_advanced
            assert gd.config.disable_reporting == disable_reporting


# ── TransactionRollbackManager Tests ─────────────────────────────────────────

@pytest.mark.unit
class TestTransactionRollbackManager:
    def test_initialization(self):
        mgr = TransactionRollbackManager()
        assert mgr is not None

    def test_begin_transaction(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")
        status = mgr.get_transaction_status("tx-1")
        assert status is not None
        assert status["status"] == "in_progress"

    def test_register_step_success(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")

        result = mgr.register_step("tx-1", "step1", lambda: "step1_result")
        assert result == "step1_result"

        status = mgr.get_transaction_status("tx-1")
        assert status["completed_steps"] == 1

    def test_register_step_failure_triggers_rollback(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")

        rollback_called = [False]
        def rollback_func():
            rollback_called[0] = True

        mgr.register_step("tx-1", "step1", lambda: "ok", rollback_func)

        with pytest.raises(ValueError):
            mgr.register_step("tx-1", "step2", lambda: (_ for _ in ()).throw(ValueError("fail")), rollback_func)

        assert rollback_called[0] is True

    def test_commit_transaction(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")
        mgr.commit_transaction("tx-1")

        status = mgr.get_transaction_status("tx-1")
        assert status["status"] == "completed"

    def test_commit_unknown_transaction(self):
        mgr = TransactionRollbackManager()
        with pytest.raises(ValueError):
            mgr.commit_transaction("unknown")

    def test_rollback_unknown_transaction(self):
        mgr = TransactionRollbackManager()
        mgr.rollback("unknown", "test")
        # Should not raise

    def test_rollback_reverses_steps(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")

        rollback_order = []
        def make_rollback(name):
            def rb():
                rollback_order.append(name)
            return rb

        mgr.register_step("tx-1", "step1", lambda: "ok", make_rollback("step1"))
        mgr.register_step("tx-1", "step2", lambda: "ok", make_rollback("step2"))

        mgr.rollback("tx-1", "manual rollback")

        assert rollback_order == ["step2", "step1"]

    def test_double_rollback_noop(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")
        mgr.rollback("tx-1", "first")
        mgr.rollback("tx-1", "second")

        status = mgr.get_transaction_status("tx-1")
        assert status["status"] == "rolled_back"

    def test_rollback_without_handler(self):
        mgr = TransactionRollbackManager()
        mgr.begin_transaction("tx-1")
        mgr.register_step("tx-1", "step1", lambda: "ok")
        mgr.rollback("tx-1", "no handler")
        # Should not raise

    def test_get_transaction_status_unknown(self):
        mgr = TransactionRollbackManager()
        assert mgr.get_transaction_status("unknown") is None


# ── DisasterRecovery Tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestDisasterRecovery:
    def test_initialization(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), max_backups=3))
        assert dr is not None
        assert os.path.exists(temp_dir)

    def test_create_backup(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False, max_backups=5))
        path = dr.create_backup({"key": "value"}, "test_data", {"version": "1.0"})
        assert os.path.exists(path)
        assert "test_data" in path
        assert path.endswith(".json")

        with open(path) as f:
            data = json.load(f)
        assert data["data"] == {"key": "value"}
        assert data["data_type"] == "test_data"
        assert data["metadata"]["version"] == "1.0"

    def test_restore_backup(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False))
        path = dr.create_backup({"key": "value"}, "test_data")

        restored = dr.restore_backup(path)
        assert restored["data"] == {"key": "value"}

    def test_restore_backup_not_found(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir)))
        with pytest.raises(FileNotFoundError):
            dr.restore_backup(str(temp_dir / "nonexistent.json"))

    def test_restore_backup_gzip(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=True, max_backups=5))
        path = dr.create_backup({"key": "value"}, "test_data")
        assert path.endswith(".gz")

        restored = dr.restore_backup(path)
        assert restored["data"] == {"key": "value"}

    def test_list_backups(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False, max_backups=10))
        dr.create_backup({"a": 1}, "type_a")
        dr.create_backup({"b": 2}, "type_b")

        backups = dr.list_backups()
        assert len(backups) == 2

    def test_list_backups_filtered(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False))
        dr.create_backup({"a": 1}, "positions")
        dr.create_backup({"b": 2}, "orders")

        positions = dr.list_backups("positions")
        assert len(positions) == 1

    def test_cleanup_old_backups(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False, max_backups=2))
        dr.create_backup({"a": 1}, "data")
        dr.create_backup({"b": 2}, "data")
        dr.create_backup({"c": 3}, "data")

        backups = dr.list_backups()
        assert len(backups) == 2

    def test_create_emergency_snapshot(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False))
        path = dr.create_emergency_snapshot(
            positions={"BTC": 1.0},
            orders={"order-1": {"side": "buy"}},
            config={"max_loss": 500},
        )
        assert os.path.exists(path)
        assert "emergency_snapshot" in path

    def test_create_backup_failure_propagates(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False))
        with patch("builtins.open", side_effect=PermissionError("no write")):
            with pytest.raises(PermissionError):
                dr.create_backup({"data": 1}, "test")

    def test_restore_corrupted_backup(self, temp_dir):
        corrupted = temp_dir / "corrupt.json"
        corrupted.write_text("{invalid json")

        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir)))
        with pytest.raises(ValueError, match="Backup file corrupted"):
            dr.restore_backup(str(corrupted))

    def test_backup_filename_format(self, temp_dir):
        dr = DisasterRecovery(BackupConfig(backup_dir=str(temp_dir), compress_backups=False))
        path = dr.create_backup({"x": 1}, "my_data")
        assert "my_data_" in path
        assert path.endswith(".json")
