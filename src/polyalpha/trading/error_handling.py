"""
Comprehensive Error Handling for Real Trading.

This module provides production-ready error handling mechanisms including:
- Circuit breakers for API failures
- Error recovery strategies
- Graceful degradation modes
- Transaction rollback logic
- Disaster recovery procedures

Usage
-----
    from polyalpha.trading.error_handling import (
        CircuitBreaker,
        ErrorRecoveryManager,
        GracefulDegradation,
        TransactionRollbackManager,
        DisasterRecovery
    )

    # Circuit breaker for CLOB API
    clob_breaker = CircuitBreaker(
        name="clob_api",
        failure_threshold=5,
        recovery_timeout=60,
        expected_exception=NetworkError
    )

    # Error recovery manager
    recovery_manager = ErrorRecoveryManager()
    recovery_manager.register_recovery_strategy(
        NetworkError,
        recovery_strategy="retry_with_backoff",
        max_attempts=3
    )
"""

from __future__ import annotations

import logging
import time
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Dict, List, Any, Type
from threading import Lock
from collections import deque
import hashlib
import random

from ..core import (
    NetworkError,
    OrderRejected,
    OrderTimeout,
    TransientError,
    InsufficientBalance,
    InsufficientAllowance,
    OrderNotFound,
    PositionNotFound,
    RiskLimitExceeded,
    OrderCancelled,
)

log = logging.getLogger(__name__)


# ── Circuit Breaker ────────────────────────────────────────────────────────────────

class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, blocking requests
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: int = 60  # Seconds to wait before attempting recovery
    success_threshold: int = 2  # Number of successes to close circuit
    timeout: int = 30  # Request timeout in seconds
    monitor_window: int = 100  # Number of requests to monitor for metrics


class CircuitBreaker:
    """
    Circuit breaker pattern for preventing cascading failures.

    Monitors service health and blocks requests when failure threshold is exceeded,
    allowing the service to recover without overwhelming it with retries.

    Parameters
    ----------
    name : str
        Name of the circuit breaker (for logging/metrics)
    failure_threshold : int
        Number of consecutive failures before opening circuit
    recovery_timeout : int
        Seconds to wait before transitioning from OPEN to HALF_OPEN
    success_threshold : int
        Number of consecutive successes to close circuit from HALF_OPEN
    timeout : int
        Request timeout in seconds
    expected_exception : tuple[Type[Exception], ...]
        Exception types that should be counted as failures
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        timeout: int = 30,
        expected_exception: tuple[Type[Exception], ...] = (NetworkError, OrderTimeout),
    ):
        self.name = name
        self._config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            success_threshold=success_threshold,
            timeout=timeout,
        )
        self._expected_exception = expected_exception

        # State
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None

        # Metrics
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._request_history: deque = deque(maxlen=100)

        # Thread safety
        self._lock = Lock()

        log.info(
            "CircuitBreaker '%s' initialized: threshold=%d, timeout=%ds",
            name, failure_threshold, recovery_timeout
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit breaker state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is currently open (blocking requests)."""
        return self._state == CircuitBreakerState.OPEN

    @property
    def metrics(self) -> dict:
        """Get circuit breaker metrics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_requests": self._total_requests,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "failure_rate": (
                    self._total_failures / self._total_requests
                    if self._total_requests > 0 else 0
                ),
                "last_failure_time": self._last_failure_time,
                "last_success_time": self._last_success_time,
            }

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt circuit reset."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self._config.recovery_timeout

    def _record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._success_count += 1
            self._total_successes += 1
            self._last_success_time = time.time()
            self._request_history.append({
                "timestamp": time.time(),
                "success": True,
            })

            # If in HALF_OPEN and success threshold reached, close circuit
            if (
                self._state == CircuitBreakerState.HALF_OPEN
                and self._success_count >= self._config.success_threshold
            ):
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                log.info("CircuitBreaker '%s' closed after %d successes", self.name, self._config.success_threshold)

    def _record_failure(self, exception: Exception) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.time()
            self._request_history.append({
                "timestamp": time.time(),
                "success": False,
                "error": str(exception),
            })

            # If failure threshold reached, open circuit
            if self._failure_count >= self._config.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self._success_count = 0
                log.warning(
                    "CircuitBreaker '%s' opened after %d failures",
                    self.name, self._failure_count
                )

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Parameters
        ----------
        func : Callable
            Function to execute
        *args, **kwargs
            Arguments to pass to the function

        Returns
        -------
        Any
            Result of the function call

        Raises
        ------
        CircuitBreakerOpenError
            If circuit is open and blocking requests
        Exception
            If the function raises an exception
        """
        with self._lock:
            self._total_requests += 1

            # Check if circuit is open
            if self._state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._failure_count = 0
                    self._success_count = 0
                    log.info("CircuitBreaker '%s' transitioning to HALF_OPEN", self.name)
                else:
                    log.warning("CircuitBreaker '%s' is open, blocking request", self.name)
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is open. "
                        f"Blocking requests until {self._config.recovery_timeout}s after last failure."
                    )

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self._expected_exception as e:
            self._record_failure(e)
            raise
        except Exception as e:
            # Unexpected exceptions don't affect circuit state
            log.error("Unexpected exception in CircuitBreaker '%s': %s", self.name, e)
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            log.info("CircuitBreaker '%s' manually reset", self.name)

    def force_open(self) -> None:
        """Manually force the circuit breaker to OPEN state."""
        with self._lock:
            self._state = CircuitBreakerState.OPEN
            self._failure_count = self._config.failure_threshold
            self._last_failure_time = time.time()
            log.warning("CircuitBreaker '%s' manually forced open", self.name)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


# ── Error Recovery Manager ───────────────────────────────────────────────────────────

class RecoveryStrategy(Enum):
    """Error recovery strategies."""
    RETRY_IMMEDIATE = "retry_immediate"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_WITH_JITTER = "retry_with_jitter"
    FALLBACK_TO_ALTERNATIVE = "fallback_to_alternative"
    CIRCUIT_BREAKER = "circuit_breaker"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    MANUAL_INTERVENTION = "manual_intervention"
    ABORT = "abort"


@dataclass
class RecoveryConfig:
    """Configuration for error recovery."""
    strategy: RecoveryStrategy
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: float = 0.1
    fallback_func: Optional[Callable] = None
    abort_on_failure: bool = False


class ErrorRecoveryManager:
    """
    Manages error recovery strategies for different exception types.

    Automatically applies appropriate recovery strategies based on the
    type of error encountered, with configurable retry logic and fallbacks.

    Parameters
    ----------
    default_config : RecoveryConfig
        Default recovery configuration for unregistered exceptions
    """

    def __init__(self, default_config: Optional[RecoveryConfig] = None):
        self._recovery_strategies: Dict[Type[Exception], RecoveryConfig] = {}
        self._default_config = default_config or RecoveryConfig(
            strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
            max_attempts=3,
        )

        # Register default strategies for common errors
        self._register_default_strategies()

        log.info("ErrorRecoveryManager initialized")

    def _register_default_strategies(self) -> None:
        """Register default recovery strategies for common exceptions."""
        # Transient errors - retry with backoff
        self.register_recovery_strategy(
            TransientError,
            RecoveryConfig(
                strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
                max_attempts=5,
                initial_delay=1.0,
                backoff_factor=2.0,
            )
        )

        # Network errors - retry with jitter
        self.register_recovery_strategy(
            NetworkError,
            RecoveryConfig(
                strategy=RecoveryStrategy.RETRY_WITH_JITTER,
                max_attempts=3,
                initial_delay=2.0,
                backoff_factor=2.0,
                jitter=0.2,
            )
        )

        # Order timeout - retry with backoff
        self.register_recovery_strategy(
            OrderTimeout,
            RecoveryConfig(
                strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
                max_attempts=2,
                initial_delay=5.0,
            )
        )

        # Insufficient allowance - manual intervention
        self.register_recovery_strategy(
            InsufficientAllowance,
            RecoveryConfig(
                strategy=RecoveryStrategy.MANUAL_INTERVENTION,
                max_attempts=1,
                abort_on_failure=True,
            )
        )

        # Insufficient balance - abort
        self.register_recovery_strategy(
            InsufficientBalance,
            RecoveryConfig(
                strategy=RecoveryStrategy.ABORT,
                max_attempts=1,
                abort_on_failure=True,
            )
        )

        # Order rejected - abort
        self.register_recovery_strategy(
            OrderRejected,
            RecoveryConfig(
                strategy=RecoveryStrategy.ABORT,
                max_attempts=1,
                abort_on_failure=True,
            )
        )

    def register_recovery_strategy(
        self,
        exception_type: Type[Exception],
        config: RecoveryConfig,
    ) -> None:
        """
        Register a recovery strategy for a specific exception type.

        Parameters
        ----------
        exception_type : Type[Exception]
            Exception type to handle
        config : RecoveryConfig
            Recovery configuration
        """
        self._recovery_strategies[exception_type] = config
        log.info(
            "Registered recovery strategy for %s: %s",
            exception_type.__name__, config.strategy.value
        )

    def get_recovery_config(self, exception: Exception) -> RecoveryConfig:
        """
        Get recovery configuration for an exception.

        Parameters
        ----------
        exception : Exception
            Exception to get config for

        Returns
        -------
        RecoveryConfig
            Recovery configuration
        """
        # Check for exact match
        for exc_type, config in self._recovery_strategies.items():
            if isinstance(exception, exc_type):
                return config

        # Use default config
        return self._default_config

    def execute_with_recovery(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute a function with automatic error recovery.

        Parameters
        ----------
        func : Callable
            Function to execute
        *args, **kwargs
            Arguments to pass to the function

        Returns
        -------
        Any
            Result of the function call

        Raises
        -------
        Exception
            If all recovery attempts fail
        """
        last_exception = None

        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            config = self.get_recovery_config(e)

            if config.strategy == RecoveryStrategy.ABORT:
                log.error("Aborting on exception: %s", e)
                raise

            elif config.strategy == RecoveryStrategy.MANUAL_INTERVENTION:
                log.error("Manual intervention required for: %s", e)
                raise ManualInterventionRequiredError(
                    f"Manual intervention required: {e}"
                )

            elif config.strategy == RecoveryStrategy.RETRY_IMMEDIATE:
                for attempt in range(config.max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as retry_e:
                        last_exception = retry_e
                        if attempt < config.max_attempts - 1:
                            log.warning(
                                "Retry %d/%d for %s",
                                attempt + 1, config.max_attempts, retry_e
                            )
                        else:
                            log.error("All retry attempts failed")
                            raise

            elif config.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
                for attempt in range(config.max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as retry_e:
                        last_exception = retry_e
                        if attempt < config.max_attempts - 1:
                            delay = min(
                                config.initial_delay * (config.backoff_factor ** attempt),
                                config.max_delay
                            )
                            log.warning(
                                "Retry %d/%d for %s in %.1fs",
                                attempt + 1, config.max_attempts, retry_e, delay
                            )
                            time.sleep(delay)
                        else:
                            log.error("All retry attempts failed")
                            raise

            elif config.strategy == RecoveryStrategy.RETRY_WITH_JITTER:
                for attempt in range(config.max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except Exception as retry_e:
                        last_exception = retry_e
                        if attempt < config.max_attempts - 1:
                            base_delay = min(
                                config.initial_delay * (config.backoff_factor ** attempt),
                                config.max_delay
                            )
                            delay = base_delay + base_delay * config.jitter * random.random()
                            log.warning(
                                "Retry %d/%d for %s in %.1fs (with jitter)",
                                attempt + 1, config.max_attempts, retry_e, delay
                            )
                            time.sleep(delay)
                        else:
                            log.error("All retry attempts failed")
                            raise

            elif config.strategy == RecoveryStrategy.FALLBACK_TO_ALTERNATIVE:
                if config.fallback_func:
                    try:
                        log.info("Attempting fallback function")
                        return config.fallback_func(*args, **kwargs)
                    except Exception as fallback_e:
                        last_exception = fallback_e
                        log.error("Fallback function failed: %s", fallback_e)
                        raise
                else:
                    log.error("No fallback function configured")
                    raise

            else:
                log.error("Unknown recovery strategy: %s", config.strategy)
                raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Execution failed without exception")


class ManualInterventionRequiredError(Exception):
    """Raised when manual intervention is required to recover from an error."""
    pass


# ── Graceful Degradation ────────────────────────────────────────────────────────────

class DegradationLevel(Enum):
    """System degradation levels."""
    NORMAL = "normal"
    DEGRADED = "degraded"
    MINIMAL = "minimal"
    CRITICAL = "critical"

    def __lt__(self, other):
        order = ["normal", "degraded", "minimal", "critical"]
        return order.index(self.value) < order.index(other.value)

    def __gt__(self, other):
        order = ["normal", "degraded", "minimal", "critical"]
        return order.index(self.value) > order.index(other.value)


@dataclass
class DegradationConfig:
    """Configuration for graceful degradation."""
    level: DegradationLevel
    disable_advanced_features: bool = True
    disable_analytics: bool = True
    disable_reporting: bool = False
    max_orders_per_minute: int = 10
    max_position_size: float = 100.0
    require_confirmation: bool = True
    enable_read_only_mode: bool = False


class GracefulDegradation:
    """
    Manages graceful degradation of system functionality during errors.

    When system components fail, gracefully degrades functionality to maintain
    core operations while preventing complete system failure.

    Parameters
    ----------
    initial_level : DegradationLevel
        Initial degradation level
    """

    def __init__(self, initial_level: DegradationLevel = DegradationLevel.NORMAL):
        self._current_level = initial_level
        self._configs: Dict[DegradationLevel, DegradationConfig] = {
            DegradationLevel.NORMAL: DegradationConfig(
                level=DegradationLevel.NORMAL,
                disable_advanced_features=False,
                disable_analytics=False,
                disable_reporting=False,
                max_orders_per_minute=100,
                max_position_size=10000.0,
                require_confirmation=False,
                enable_read_only_mode=False,
            ),
            DegradationLevel.DEGRADED: DegradationConfig(
                level=DegradationLevel.DEGRADED,
                disable_advanced_features=True,
                disable_analytics=True,
                disable_reporting=False,
                max_orders_per_minute=30,
                max_position_size=500.0,
                require_confirmation=True,
                enable_read_only_mode=False,
            ),
            DegradationLevel.MINIMAL: DegradationConfig(
                level=DegradationLevel.MINIMAL,
                disable_advanced_features=True,
                disable_analytics=True,
                disable_reporting=True,
                max_orders_per_minute=5,
                max_position_size=100.0,
                require_confirmation=True,
                enable_read_only_mode=False,
            ),
            DegradationLevel.CRITICAL: DegradationConfig(
                level=DegradationLevel.CRITICAL,
                disable_advanced_features=True,
                disable_analytics=True,
                disable_reporting=True,
                max_orders_per_minute=0,
                max_position_size=0.0,
                require_confirmation=True,
                enable_read_only_mode=True,
            ),
        }
        self._degradation_history: List[Dict] = []

        log.info("GracefulDegradation initialized at level: %s", initial_level.value)

    @property
    def current_level(self) -> DegradationLevel:
        """Current degradation level."""
        return self._current_level

    @property
    def config(self) -> DegradationConfig:
        """Current degradation configuration."""
        return self._configs[self._current_level]

    def degrade(self, new_level: DegradationLevel, reason: str) -> None:
        """
        Degrade system to a lower functionality level.

        Parameters
        ----------
        new_level : DegradationLevel
            New degradation level
        reason : str
            Reason for degradation
        """
        if new_level > self._current_level:
            log.warning(
                "Degrading from %s to %s: %s",
                self._current_level.value, new_level.value, reason
            )

            self._degradation_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_level": self._current_level.value,
                "to_level": new_level.value,
                "reason": reason,
            })

            self._current_level = new_level

    def recover(self, new_level: DegradationLevel, reason: str) -> None:
        """
        Recover system to a higher functionality level.

        Parameters
        ----------
        new_level : DegradationLevel
            New degradation level
        reason : str
            Reason for recovery
        """
        if new_level < self._current_level:
            log.info(
                "Recovering from %s to %s: %s",
                self._current_level.value, new_level.value, reason
            )

            self._degradation_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_level": self._current_level.value,
                "to_level": new_level.value,
                "reason": reason,
            })

            self._current_level = new_level

    def can_execute_order(self) -> tuple[bool, str]:
        """
        Check if orders can be executed at current degradation level.

        Returns
        -------
        tuple[bool, str]
            (can_execute, reason)
        """
        config = self.config

        if config.enable_read_only_mode:
            return False, "System in read-only mode"

        if config.max_orders_per_minute == 0:
            return False, "Order execution disabled at current degradation level"

        return True, "Order execution allowed"

    def get_degradation_summary(self) -> dict:
        """Get summary of current degradation state."""
        return {
            "current_level": self._current_level.value,
            "config": {
                "disable_advanced_features": self.config.disable_advanced_features,
                "disable_analytics": self.config.disable_analytics,
                "disable_reporting": self.config.disable_reporting,
                "max_orders_per_minute": self.config.max_orders_per_minute,
                "max_position_size": self.config.max_position_size,
                "require_confirmation": self.config.require_confirmation,
                "enable_read_only_mode": self.config.enable_read_only_mode,
            },
            "history": self._degradation_history,
        }


# ── Transaction Rollback Manager ───────────────────────────────────────────────────

@dataclass
class TransactionState:
    """State of a transaction for rollback purposes."""
    transaction_id: str
    steps: List[Dict] = field(default_factory=list)
    completed_steps: int = 0
    rollback_data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    status: str = "in_progress"  # in_progress, completed, rolled_back, failed


class TransactionRollbackManager:
    """
    Manages transaction rollback for multi-step operations.

    Tracks the state of multi-step transactions and can roll back
    completed steps if a later step fails.

    Parameters
    ----------
    rollback_timeout : int
        Timeout for rollback operations in seconds
    """

    def __init__(self, rollback_timeout: int = 300):
        self._transactions: Dict[str, TransactionState] = {}
        self._rollback_timeout = rollback_timeout
        self._rollback_handlers: Dict[str, Callable] = {}

        log.info("TransactionRollbackManager initialized")

    def begin_transaction(self, transaction_id: str) -> None:
        """
        Begin a new transaction.

        Parameters
        ----------
        transaction_id : str
            Unique transaction identifier
        """
        self._transactions[transaction_id] = TransactionState(
            transaction_id=transaction_id
        )
        log.info("Transaction %s started", transaction_id)

    def register_step(
        self,
        transaction_id: str,
        step_name: str,
        execute_func: Callable,
        rollback_func: Optional[Callable] = None,
        **kwargs,
    ) -> Any:
        """
        Register and execute a transaction step.

        Parameters
        ----------
        transaction_id : str
            Transaction identifier
        step_name : str
            Name of the step
        execute_func : Callable
            Function to execute the step
        rollback_func : Callable, optional
            Function to rollback the step
        **kwargs
            Arguments to pass to execute_func

        Returns
        -------
        Any
            Result of execute_func

        Raises
        ------
        Exception
            If step execution fails
        """
        if transaction_id not in self._transactions:
            raise ValueError(f"Transaction {transaction_id} not found")

        transaction = self._transactions[transaction_id]

        try:
            result = execute_func(**kwargs)

            # Record successful step
            transaction.steps.append({
                "name": step_name,
                "status": "completed",
                "result": str(result),
                "timestamp": time.time(),
            })
            transaction.completed_steps += 1

            # Store rollback handler if provided
            if rollback_func:
                self._rollback_handlers[f"{transaction_id}:{step_name}"] = rollback_func

            log.info("Transaction %s step %s completed", transaction_id, step_name)
            return result

        except Exception as e:
            # Record failed step
            transaction.steps.append({
                "name": step_name,
                "status": "failed",
                "error": str(e),
                "timestamp": time.time(),
            })
            transaction.status = "failed"

            log.error("Transaction %s step %s failed: %s", transaction_id, step_name, e)

            # Trigger rollback
            self.rollback(transaction_id, reason=f"Step {step_name} failed")

            raise

    def commit_transaction(self, transaction_id: str) -> None:
        """
        Commit a transaction as successfully completed.

        Parameters
        ----------
        transaction_id : str
            Transaction identifier
        """
        if transaction_id not in self._transactions:
            raise ValueError(f"Transaction {transaction_id} not found")

        transaction = self._transactions[transaction_id]
        transaction.status = "completed"

        log.info("Transaction %s committed successfully", transaction_id)

        # Clean up old transactions
        self._cleanup_old_transactions()

    def rollback(self, transaction_id: str, reason: str) -> None:
        """
        Rollback a transaction by reversing completed steps.

        Parameters
        ----------
        transaction_id : str
            Transaction identifier
        reason : str
            Reason for rollback
        """
        if transaction_id not in self._transactions:
            log.warning("Cannot rollback unknown transaction: %s", transaction_id)
            return

        transaction = self._transactions[transaction_id]

        if transaction.status == "rolled_back":
            log.warning("Transaction %s already rolled back", transaction_id)
            return

        log.warning("Rolling back transaction %s: %s", transaction_id, reason)

        # Rollback steps in reverse order
        for step in reversed(transaction.steps):
            if step["status"] == "completed":
                step_name = step["name"]
                handler_key = f"{transaction_id}:{step_name}"

                if handler_key in self._rollback_handlers:
                    try:
                        rollback_func = self._rollback_handlers[handler_key]
                        rollback_func()
                        step["rollback_status"] = "completed"
                        log.info("Rolled back step %s", step_name)
                    except Exception as e:
                        step["rollback_status"] = "failed"
                        log.error("Failed to rollback step %s: %s", step_name, e)
                else:
                    step["rollback_status"] = "skipped"
                    log.warning("No rollback handler for step %s", step_name)

        transaction.status = "rolled_back"
        log.warning("Transaction %s rollback completed", transaction_id)

    def _cleanup_old_transactions(self) -> None:
        """Clean up old completed transactions."""
        current_time = time.time()
        to_remove = []

        for tx_id, transaction in self._transactions.items():
            if (
                transaction.status in ("completed", "rolled_back", "failed")
                and current_time - transaction.timestamp > self._rollback_timeout
            ):
                to_remove.append(tx_id)

        for tx_id in to_remove:
            del self._transactions[tx_id]
            log.debug("Cleaned up old transaction: %s", tx_id)

    def get_transaction_status(self, transaction_id: str) -> Optional[dict]:
        """
        Get the status of a transaction.

        Parameters
        ----------
        transaction_id : str
            Transaction identifier

        Returns
        -------
        dict or None
            Transaction status information
        """
        if transaction_id not in self._transactions:
            return None

        transaction = self._transactions[transaction_id]
        return {
            "transaction_id": transaction.transaction_id,
            "status": transaction.status,
            "completed_steps": transaction.completed_steps,
            "total_steps": len(transaction.steps),
            "steps": transaction.steps,
            "timestamp": transaction.timestamp,
        }


# ── Disaster Recovery ───────────────────────────────────────────────────────────────

@dataclass
class BackupConfig:
    """Configuration for disaster recovery backups."""
    backup_dir: str = "./backups"
    max_backups: int = 10
    backup_interval: int = 3600  # 1 hour
    compress_backups: bool = True


class DisasterRecovery:
    """
    Manages disaster recovery procedures.

    Provides backup and restore functionality for critical trading data,
    ensuring system can recover from catastrophic failures.

    Parameters
    ----------
    config : BackupConfig
        Backup configuration
    """

    def __init__(self, config: Optional[BackupConfig] = None):
        self._config = config or BackupConfig()
        self._backup_dir = self._config.backup_dir
        self._ensure_backup_dir()

        log.info("DisasterRecovery initialized with backup dir: %s", self._backup_dir)

    def _ensure_backup_dir(self) -> None:
        """Ensure backup directory exists."""
        os.makedirs(self._backup_dir, exist_ok=True)

    def _generate_backup_filename(self, data_type: str) -> str:
        """Generate a unique backup filename."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique = hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:8]
        filename = f"{data_type}_{timestamp}_{unique}.json"
        if self._config.compress_backups:
            filename += ".gz"
        return os.path.join(self._backup_dir, filename)

    def create_backup(
        self,
        data: Dict,
        data_type: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Create a backup of trading data.

        Parameters
        ----------
        data : dict
            Data to backup
        data_type : str
            Type of data (e.g., "positions", "orders", "config")
        metadata : dict, optional
            Additional metadata to include in backup

        Returns
        -------
        str
            Path to backup file
        """
        filename = self._generate_backup_filename(data_type)

        backup_data = {
            "metadata": metadata or {},
            "data_type": data_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        try:
            if self._config.compress_backups:
                import gzip
                with gzip.open(filename, 'wt', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2)
            else:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2)

            log.info("Backup created: %s", filename)
            self._cleanup_old_backups()
            return filename

        except Exception as e:
            log.error("Failed to create backup: %s", e)
            raise

    def restore_backup(self, backup_path: str) -> Dict:
        """
        Restore data from a backup file.

        Parameters
        ----------
        backup_path : str
            Path to backup file

        Returns
        -------
        dict
            Restored data

        Raises
        ------
        FileNotFoundError
            If backup file doesn't exist
        ValueError
            If backup file is corrupted
        """
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        try:
            if backup_path.endswith('.gz'):
                import gzip
                with gzip.open(backup_path, 'rt', encoding='utf-8') as f:
                    backup_data = json.load(f)
            else:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)

            log.info("Backup restored from: %s", backup_path)
            return backup_data

        except json.JSONDecodeError as e:
            log.error("Backup file corrupted: %s", e)
            raise ValueError(f"Backup file corrupted: {e}")
        except Exception as e:
            log.error("Failed to restore backup: %s", e)
            raise

    def list_backups(self, data_type: Optional[str] = None) -> List[Dict]:
        """
        List available backups.

        Parameters
        ----------
        data_type : str, optional
            Filter by data type

        Returns
        -------
        list[dict]
            List of backup information
        """
        backups = []

        for filename in os.listdir(self._backup_dir):
            filepath = os.path.join(self._backup_dir, filename)

            if not (filename.endswith('.json') or filename.endswith('.json.gz')):
                continue

            if data_type and not filename.startswith(data_type):
                continue

            try:
                # Read metadata without loading full backup
                if filename.endswith('.gz'):
                    import gzip
                    with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                        backup_data = json.load(f)
                else:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        backup_data = json.load(f)

                backups.append({
                    "filename": filename,
                    "path": filepath,
                    "data_type": backup_data.get("data_type"),
                    "timestamp": backup_data.get("timestamp"),
                    "size": os.path.getsize(filepath),
                })

            except Exception as e:
                log.warning("Failed to read backup metadata for %s: %s", filename, e)

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    def _cleanup_old_backups(self) -> None:
        """Clean up old backups, keeping only the most recent ones."""
        backups = self.list_backups()

        if len(backups) > self._config.max_backups:
            # Remove oldest backups
            for backup in backups[self._config.max_backups:]:
                try:
                    os.remove(backup["path"])
                    log.info("Removed old backup: %s", backup["filename"])
                except Exception as e:
                    log.error("Failed to remove old backup %s: %s", backup["filename"], e)

    def create_emergency_snapshot(
        self,
        positions: Dict,
        orders: Dict,
        config: Dict,
    ) -> str:
        """
        Create an emergency snapshot of critical trading state.

        Parameters
        ----------
        positions : dict
            Current positions
        orders : dict
            Current orders
        config : dict
        Trading configuration

        Returns
        -------
        str
            Path to snapshot file
        """
        snapshot_data = {
            "positions": positions,
            "orders": orders,
            "config": config,
            "snapshot_type": "emergency",
        }

        return self.create_backup(
            snapshot_data,
            "emergency_snapshot",
            metadata={"emergency": True, "trigger": "manual"},
        )
