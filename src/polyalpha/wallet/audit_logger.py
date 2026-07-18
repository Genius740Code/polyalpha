"""
Security audit logging for wallet operations.

This module provides comprehensive audit logging for all wallet security
operations including key access, transaction signing, and configuration changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any
from threading import Lock

from ..utils.logging_utils import mask_address, mask_transaction_hash

log = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    WALLET_CREATED = "wallet_created"
    WALLET_ACCESSED = "wallet_accessed"
    WALLET_REMOVED = "wallet_removed"
    WALLET_EXPORTED = "wallet_exported"
    WALLET_IMPORTED = "wallet_imported"
    KEY_ROTATED = "key_rotated"
    TRANSACTION_SIGNED = "transaction_signed"
    TRANSACTION_BROADCAST = "transaction_broadcast"
    HARDWARE_CONNECTED = "hardware_connected"
    HARDWARE_DISCONNECTED = "hardware_disconnected"
    MULTISIG_PROPOSED = "multisig_proposed"
    MULTISIG_SIGNED = "multisig_signed"
    MULTISIG_EXECUTED = "multisig_executed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    CONFIG_CHANGED = "config_changed"
    SECURITY_EVENT = "security_event"


@dataclass
class AuditEvent:
    """An audit event record."""
    event_type: AuditEventType
    timestamp: datetime
    wallet_address: Optional[str]
    actor: Optional[str]
    ip_address: Optional[str]
    details: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "wallet_address": self.wallet_address,
            "actor": self.actor,
            "ip_address": self.ip_address,
            "details": self.details,
            "success": self.success,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """Create from dictionary."""
        data['event_type'] = AuditEventType(data['event_type'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class AuditLogger:
    """
    Security audit logger for wallet operations.
    
    Provides:
    - Comprehensive logging of all security-relevant events
    - Structured event storage
    - Query and filtering capabilities
    - Export functionality for compliance
    - Tamper-evident logging
    """
    
    def __init__(
        self,
        log_path: Optional[Path] = None,
        max_events: int = 10000,
        enable_console_logging: bool = True,
    ):
        """
        Initialize audit logger.
        
        Parameters
        ----------
        log_path : Path, optional
            Path to store audit logs. If not provided, uses default location.
        max_events : int
            Maximum number of events to keep in memory.
        enable_console_logging : bool
            Whether to log to console as well.
        """
        self._log_path = log_path or Path.home() / ".polyalpha" / "audit.log"
        self._max_events = max_events
        self._enable_console_logging = enable_console_logging
        self._events: List[AuditEvent] = []
        self._lock = Lock()
        
        # Ensure log directory exists
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing events
        self._load_events()
        
        log.info("Initialized audit logger: %s", self._log_path)
    
    def log_event(
        self,
        event_type: AuditEventType,
        wallet_address: Optional[str] = None,
        actor: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log an audit event.
        
        Parameters
        ----------
        event_type : AuditEventType
            Type of event.
        wallet_address : str, optional
            Related wallet address.
        actor : str, optional
            Actor performing the action.
        ip_address : str, optional
            IP address of the actor.
        details : dict, optional
            Additional event details.
        success : bool
            Whether the operation succeeded.
        error_message : str, optional
            Error message if operation failed.
        """
        with self._lock:
            event = AuditEvent(
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                wallet_address=wallet_address,
                actor=actor,
                ip_address=ip_address,
                details=details or {},
                success=success,
                error_message=error_message,
            )
            
            self._events.append(event)
            
            # Trim if too many events
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
            
            # Persist to disk
            self._append_event(event)
            
            # Console logging
            if self._enable_console_logging:
                self._log_to_console(event)
    
    def _log_to_console(self, event: AuditEvent) -> None:
        """Log event to console."""
        level = logging.INFO if event.success else logging.WARNING
        msg = f"[AUDIT] {event.event_type.value}"
        if event.wallet_address:
            msg += f" | wallet: {event.wallet_address[:8]}..."
        if event.actor:
            msg += f" | actor: {event.actor[:8]}..."
        if not event.success:
            msg += f" | FAILED: {event.error_message}"
        
        log.log(level, msg)
    
    def _append_event(self, event: AuditEvent) -> None:
        """Append event to log file."""
        try:
            with open(self._log_path, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            log.error("Failed to write audit log: %s", e)
    
    def _load_events(self) -> None:
        """Load events from log file."""
        if not self._log_path.exists():
            return
        
        try:
            with open(self._log_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = AuditEvent.from_dict(json.loads(line))
                            self._events.append(event)
                        except Exception as e:
                            log.warning("Failed to parse audit log line: %s", e)
            
            # Trim if too many events
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]
            
            log.info("Loaded %d audit events", len(self._events))
        except Exception as e:
            log.error("Failed to load audit log: %s", e)
    
    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        wallet_address: Optional[str] = None,
        actor: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        success: Optional[bool] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        Query audit events with filters.
        
        Parameters
        ----------
        event_type : AuditEventType, optional
            Filter by event type.
        wallet_address : str, optional
            Filter by wallet address.
        actor : str, optional
            Filter by actor.
        start_time : datetime, optional
            Filter by start time.
        end_time : datetime, optional
            Filter by end time.
        success : bool, optional
            Filter by success status.
        limit : int
            Maximum number of events to return.
        
        Returns
        -------
        list of AuditEvent
            Filtered events.
        """
        with self._lock:
            filtered = self._events
            
            if event_type:
                filtered = [e for e in filtered if e.event_type == event_type]
            
            if wallet_address:
                filtered = [e for e in filtered if e.wallet_address == wallet_address]
            
            if actor:
                filtered = [e for e in filtered if e.actor == actor]
            
            if start_time:
                filtered = [e for e in filtered if e.timestamp >= start_time]
            
            if end_time:
                filtered = [e for e in filtered if e.timestamp <= end_time]
            
            if success is not None:
                filtered = [e for e in filtered if e.success == success]
            
            # Return most recent first
            filtered = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
            
            return filtered[:limit]
    
    def get_wallet_history(
        self,
        wallet_address: str,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        Get audit history for a specific wallet.
        
        Parameters
        ----------
        wallet_address : str
            Wallet address.
        limit : int
            Maximum number of events to return.
        
        Returns
        -------
        list of AuditEvent
            Wallet audit history.
        """
        return self.query_events(wallet_address=wallet_address, limit=limit)
    
    def get_failed_events(self, limit: int = 100) -> List[AuditEvent]:
        """
        Get all failed events.
        
        Parameters
        ----------
        limit : int
            Maximum number of events to return.
        
        Returns
        -------
        list of AuditEvent
            Failed events.
        """
        return self.query_events(success=False, limit=limit)
    
    def get_security_events(self, limit: int = 100) -> List[AuditEvent]:
        """
        Get security-related events.
        
        Parameters
        ----------
        limit : int
            Maximum number of events to return.
        
        Returns
        -------
        list of AuditEvent
            Security events.
        """
        return self.query_events(event_type=AuditEventType.SECURITY_EVENT, limit=limit)
    
    def export_events(
        self,
        export_path: Path,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """
        Export audit events to a file.
        
        Parameters
        ----------
        export_path : Path
            Path to export to.
        start_time : datetime, optional
            Start time filter.
        end_time : datetime, optional
            End time filter.
        """
        events = self.query_events(
            start_time=start_time,
            end_time=end_time,
            limit=len(self._events),
        )
        
        export_data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "event_count": len(events),
            "events": [e.to_dict() for e in events],
        }
        
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        log.info("Exported %d audit events to %s", len(events), export_path.name)
    
    def clear_old_events(self, days_to_keep: int = 90) -> int:
        """
        Clear events older than specified days.
        
        Parameters
        ----------
        days_to_keep : int
            Number of days to keep.
        
        Returns
        -------
        int
            Number of events removed.
        """
        cutoff = datetime.now(timezone.utc) - timezone.timedelta(days=days_to_keep)
        
        with self._lock:
            original_count = len(self._events)
            self._events = [e for e in self._events if e.timestamp >= cutoff]
            removed = original_count - len(self._events)
            
            # Rewrite log file
            self._rewrite_log_file()
            
            log.info("Cleared %d old audit events (older than %d days)", removed, days_to_keep)
            return removed
    
    def _rewrite_log_file(self) -> None:
        """Rewrite the entire log file with current events."""
        try:
            with open(self._log_path, 'w') as f:
                for event in self._events:
                    f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            log.error("Failed to rewrite audit log: %s", e)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get audit log statistics.
        
        Returns
        -------
        dict
            Statistics about the audit log.
        """
        with self._lock:
            if not self._events:
                return {"total_events": 0}
            
            total = len(self._events)
            successful = sum(1 for e in self._events if e.success)
            failed = total - successful
            
            # Count by event type
            event_type_counts = {}
            for event in self._events:
                event_type_counts[event.event_type.value] = event_type_counts.get(event.event_type.value, 0) + 1
            
            # Time range
            timestamps = [e.timestamp for e in self._events]
            oldest = min(timestamps)
            newest = max(timestamps)
            
            return {
                "total_events": total,
                "successful_events": successful,
                "failed_events": failed,
                "success_rate": successful / total if total > 0 else 0,
                "event_type_counts": event_type_counts,
                "oldest_event": oldest.isoformat(),
                "newest_event": newest.isoformat(),
                "unique_wallets": len(set(e.wallet_address for e in self._events if e.wallet_address)),
                "unique_actors": len(set(e.actor for e in self._events if e.actor)),
            }


# Global audit logger instance
_global_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _global_audit_logger
    if _global_audit_logger is None:
        _global_audit_logger = AuditLogger()
    return _global_audit_logger


def set_audit_logger(logger: AuditLogger) -> None:
    """Set the global audit logger instance."""
    global _global_audit_logger
    _global_audit_logger = logger


__all__ = [
    "AuditEventType",
    "AuditEvent",
    "AuditLogger",
    "get_audit_logger",
    "set_audit_logger",
]
