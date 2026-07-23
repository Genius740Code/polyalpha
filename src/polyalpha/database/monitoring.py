from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from threading import Lock
from contextlib import contextmanager

from .models import TradeRecord, LogEntry, AlertRule, DatabaseMetrics

log = logging.getLogger(__name__)


class DatabaseMonitor:
    def __init__(self):
        self._query_count = 0
        self._slow_query_count = 0
        self._query_times: List[float] = []
        self._max_query_times = 1000
        self._slow_query_threshold_ms = 1000.0

        self._log_entries: List[LogEntry] = []
        self._max_log_entries = 10000
        self._log_lock = Lock()

        self._alert_rules: Dict[str, AlertRule] = {}
        self._alert_lock = Lock()

        self._current_correlation_id: Optional[str] = None
        self._correlation_lock = Lock()

    def set_correlation_id(self, correlation_id: str) -> None:
        with self._correlation_lock:
            self._current_correlation_id = correlation_id

    def clear_correlation_id(self) -> None:
        with self._correlation_lock:
            self._current_correlation_id = None

    def _get_correlation_id(self) -> str:
        with self._correlation_lock:
            if self._current_correlation_id is None:
                self._current_correlation_id = str(uuid.uuid4())
            return self._current_correlation_id

    def _add_log_entry(
        self,
        level: str,
        message: str,
        operation: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        correlation_id = self._get_correlation_id()
        entry = LogEntry(
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
            level=level.upper(),
            message=message,
            operation=operation,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        with self._log_lock:
            self._log_entries.append(entry)
            if len(self._log_entries) > self._max_log_entries:
                self._log_entries.pop(0)

    def get_logs(
        self,
        level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        with self._log_lock:
            filtered_logs = self._log_entries.copy()
        if level:
            filtered_logs = [l for l in filtered_logs if l.level == level.upper()]
        if start_date:
            filtered_logs = [l for l in filtered_logs if l.timestamp >= start_date]
        if end_date:
            filtered_logs = [l for l in filtered_logs if l.timestamp <= end_date]
        if operation:
            filtered_logs = [l for l in filtered_logs if l.operation == operation]
        filtered_logs.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered_logs[:limit]

    def set_alert(
        self,
        name: str,
        metric: str,
        threshold: float,
        comparison: str = "gt",
        callback: Optional[Callable[[str, float, float], None]] = None,
    ) -> None:
        valid_comparisons = {"gt", "lt", "eq", "gte", "lte"}
        if comparison not in valid_comparisons:
            raise ValueError(f"Invalid comparison '{comparison}'. Valid options: {valid_comparisons}")
        with self._alert_lock:
            self._alert_rules[name] = AlertRule(
                name=name, metric=metric, threshold=threshold,
                comparison=comparison, enabled=True, callback=callback,
                last_triggered=None, trigger_count=0,
            )
        log.info("Alert rule set: %s on %s %s %s", name, metric, comparison, threshold)

    def remove_alert(self, name: str) -> None:
        with self._alert_lock:
            self._alert_rules.pop(name, None)
            log.info("Alert rule removed: %s", name)

    def get_alerts(self) -> Dict[str, Dict[str, Any]]:
        with self._alert_lock:
            return {
                name: {
                    "metric": rule.metric,
                    "threshold": rule.threshold,
                    "comparison": rule.comparison,
                    "enabled": rule.enabled,
                    "last_triggered": rule.last_triggered.isoformat() if rule.last_triggered else None,
                    "trigger_count": rule.trigger_count,
                }
                for name, rule in self._alert_rules.items()
            }

    def check_alerts(self, metrics: DatabaseMetrics) -> None:
        metric_values = metrics.to_dict()
        with self._alert_lock:
            for name, rule in self._alert_rules.items():
                if not rule.enabled:
                    continue
                metric_value = metric_values.get(rule.metric)
                if metric_value is None:
                    continue
                triggered = False
                if rule.comparison == "gt" and metric_value > rule.threshold:
                    triggered = True
                elif rule.comparison == "lt" and metric_value < rule.threshold:
                    triggered = True
                elif rule.comparison == "eq" and metric_value == rule.threshold:
                    triggered = True
                elif rule.comparison == "gte" and metric_value >= rule.threshold:
                    triggered = True
                elif rule.comparison == "lte" and metric_value <= rule.threshold:
                    triggered = True
                if triggered:
                    rule.last_triggered = datetime.now(timezone.utc)
                    rule.trigger_count += 1
                    if rule.callback:
                        try:
                            rule.callback(name, metric_value, rule.threshold)
                        except Exception as e:
                            log.error("Error in alert callback for %s: %s", name, e)
                    log.warning("Alert triggered: %s - %s = %s (threshold: %s)",
                                name, rule.metric, metric_value, rule.threshold)

    @contextmanager
    def _track_query(self, operation: str):
        correlation_id = self._get_correlation_id()
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._query_count += 1
            self._query_times.append(duration_ms)
            if len(self._query_times) > self._max_query_times:
                self._query_times.pop(0)
            if duration_ms > self._slow_query_threshold_ms:
                self._slow_query_count += 1
                self._add_log_entry(level="WARNING", message=f"Slow query detected: {operation}",
                                    operation=operation, duration_ms=duration_ms)
            self._add_log_entry(level="DEBUG", message=f"Query completed: {operation}",
                                operation=operation, duration_ms=duration_ms)

    @contextmanager
    def operation_context(self, operation_name: str):
        old_correlation_id = self._current_correlation_id
        self.set_correlation_id(str(uuid.uuid4()))
        self._add_log_entry(level="INFO", message=f"Operation started: {operation_name}",
                            operation=operation_name)
        start_time = time.perf_counter()
        try:
            yield
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._add_log_entry(level="INFO", message=f"Operation completed: {operation_name}",
                                operation=operation_name, duration_ms=duration_ms)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._add_log_entry(level="ERROR", message=f"Operation failed: {operation_name} - {str(e)}",
                                operation=operation_name, duration_ms=duration_ms,
                                metadata={"error": str(e), "error_type": type(e).__name__})
            raise
        finally:
            self._current_correlation_id = old_correlation_id


class EventSystem:
    def __init__(self):
        self._trade_saved_hooks: List[Callable[[TradeRecord], None]] = []
        self._trade_updated_hooks: List[Callable[[int, Dict[str, Any]], None]] = []
        self._trade_deleted_hooks: List[Callable[[int], None]] = []
        self._hooks_lock = Lock()
        self._streaming_enabled = False

    def on_trade_saved(self, callback: Callable[[TradeRecord], None]) -> Callable[[TradeRecord], None]:
        with self._hooks_lock:
            self._trade_saved_hooks.append(callback)
        return callback

    def on_trade_updated(self, callback: Callable[[int, Dict[str, Any]], None]) -> Callable[[int, Dict[str, Any]], None]:
        with self._hooks_lock:
            self._trade_updated_hooks.append(callback)
        return callback

    def on_trade_deleted(self, callback: Callable[[int], None]) -> Callable[[int], None]:
        with self._hooks_lock:
            self._trade_deleted_hooks.append(callback)
        return callback

    def remove_trade_saved_hook(self, callback: Callable[[TradeRecord], None]) -> None:
        with self._hooks_lock:
            if callback in self._trade_saved_hooks:
                self._trade_saved_hooks.remove(callback)

    def remove_trade_updated_hook(self, callback: Callable[[int, Dict[str, Any]], None]) -> None:
        with self._hooks_lock:
            if callback in self._trade_updated_hooks:
                self._trade_updated_hooks.remove(callback)

    def remove_trade_deleted_hook(self, callback: Callable[[int], None]) -> None:
        with self._hooks_lock:
            if callback in self._trade_deleted_hooks:
                self._trade_deleted_hooks.remove(callback)

    def _trigger_trade_saved_hooks(self, trade: TradeRecord) -> None:
        with self._hooks_lock:
            for callback in self._trade_saved_hooks:
                try:
                    callback(trade)
                except Exception as e:
                    log.error("Error in trade_saved callback %s: %s", callback.__name__, e)

    def _trigger_trade_updated_hooks(self, trade_id: int, changes: Dict[str, Any]) -> None:
        with self._hooks_lock:
            for callback in self._trade_updated_hooks:
                try:
                    callback(trade_id, changes)
                except Exception as e:
                    log.error("Error in trade_updated callback %s: %s", callback.__name__, e)

    def _trigger_trade_deleted_hooks(self, trade_id: int) -> None:
        with self._hooks_lock:
            for callback in self._trade_deleted_hooks:
                try:
                    callback(trade_id)
                except Exception as e:
                    log.error("Error in trade_deleted callback %s: %s", callback.__name__, e)

    def enable_streaming(self) -> None:
        self._streaming_enabled = True
        log.info("Real-time streaming enabled")

    def disable_streaming(self) -> None:
        self._streaming_enabled = False
        log.info("Real-time streaming disabled")

    @property
    def streaming_enabled(self) -> bool:
        return self._streaming_enabled
