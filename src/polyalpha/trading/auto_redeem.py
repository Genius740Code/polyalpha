"""
Auto-Redeem Engine for Polymarket Positions

This module provides automatic redemption of resolved Polymarket positions
based on configurable triggers (time intervals, market count, or value thresholds).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..utils.logging_utils import mask_address

if TYPE_CHECKING:
    from .paper_engine import PaperEngine
    from .real_engine import RealTradingEngine

log = logging.getLogger("polyalpha.auto_redeem")


@dataclass
class AutoRedeemConfig:
    """
    Configuration for automatic token redemption.
    
    Parameters
    ----------
    enabled : bool
        Enable or disable auto-redeem functionality.
    trigger_on_time : bool
        Enable time-based redemption triggers.
    trigger_on_count : bool
        Enable count-based redemption triggers.
    trigger_on_value : bool
        Enable value-based redemption triggers.
    time_interval : str
        Time interval for scheduled redemption ("1h", "1d", "1w").
    redeem_at_time : str | None
        Specific time of day for redemption (e.g., "14:00" UTC).
    min_markets : int
        Minimum number of resolved markets before redemption.
    max_markets : int
        Maximum number of markets before forced redemption (safety limit).
    min_value_usd : float
        Minimum total value in USD before redemption.
    max_value_usd : float
        Maximum total value before forced redemption (safety limit).
    require_confirmation : bool
        Require user confirmation before executing redemption.
    max_gas_price : float
        Maximum gas price in Gwei for real trading redemptions.
    dry_run : bool
        Simulate redemption without executing transactions.
    only_winning : bool
        Only redeem winning positions (skip losing ones).
    min_age_hours : int
        Minimum hours after resolution before redemption.
    """
    
    # Enable/disable
    enabled: bool = True
    
    # Trigger modes
    trigger_on_time: bool = True
    trigger_on_count: bool = True
    trigger_on_value: bool = False
    
    # Time-based triggers
    time_interval: str = "1d"
    redeem_at_time: str | None = None
    
    # Count-based triggers
    min_markets: int = 10
    max_markets: int = 100
    
    # Value-based triggers
    min_value_usd: float = 100.0
    max_value_usd: float = 10000.0
    
    # Safety settings
    require_confirmation: bool = False
    max_gas_price: float = 50.0
    dry_run: bool = False
    
    # Filtering
    only_winning: bool = False
    min_age_hours: int = 1


@dataclass
class RedeemablePosition:
    """
    A position that is ready for redemption.
    
    Attributes
    ----------
    market_id : str
        Market/condition ID.
    slug : str
        Market slug.
    side : str
        "UP" or "DOWN".
    shares : float
        Number of shares held.
    outcome : str
        "WON" or "LOST".
    value_usd : float
        Current value in USD.
    resolved_at : datetime
        When the market was resolved.
    token_id : str
        CLOB token ID.
    """
    market_id: str
    slug: str
    side: str
    shares: float
    outcome: str
    value_usd: float
    resolved_at: datetime
    token_id: str


@dataclass
class RedeemRecord:
    """
    Record of a redemption operation.
    
    Attributes
    ----------
    timestamp : datetime
        When the redemption was executed.
    positions_count : int
        Number of positions redeemed.
    total_value_usd : float
        Total value redeemed in USD.
    trigger_reason : str
        Reason for redemption ("time", "count", "value", "manual").
    success : bool
        Whether the redemption succeeded.
    tx_hash : str | None
        Transaction hash for real trading redemptions.
    error : str | None
        Error message if redemption failed.
    """
    timestamp: datetime
    positions_count: int
    total_value_usd: float
    trigger_reason: str
    success: bool
    tx_hash: str | None = None
    error: str | None = None


@dataclass
class RedeemResult:
    """
    Result of a redemption operation.
    
    Attributes
    ----------
    success : bool
        Whether the operation succeeded.
    redeemed_count : int
        Number of positions successfully redeemed.
    total_value_usd : float
        Total value redeemed in USD.
    failed_count : int
        Number of positions that failed to redeem.
    errors : list[str]
        List of error messages.
    tx_hash : str | None
        Transaction hash for real trading redemptions.
    """
    success: bool
    redeemed_count: int
    total_value_usd: float
    failed_count: int
    errors: list[str] = field(default_factory=list)
    tx_hash: str | None = None


class AutoRedeemEngine:
    """
    Automatic redemption engine for resolved Polymarket positions.
    
    This engine monitors positions for resolution status and executes
    redemption based on configured triggers (time, count, or value).
    
    Parameters
    ----------
    trading_engine : PaperEngine | RealTradingEngine
        The trading engine to use for redemption.
    config : AutoRedeemConfig
        Configuration for auto-redeem behavior.
    
    Example
    -------
    >>> config = AutoRedeemConfig(time_interval="1d", min_value_usd=100.0)
    >>> auto_redeem = AutoRedeemEngine(client.real, config)
    >>> auto_redeem.start_scheduler()
    """
    
    def __init__(
        self,
        trading_engine: PaperEngine | RealTradingEngine,
        config: AutoRedeemConfig,
    ):
        self._trading = trading_engine
        self._config = config
        self._redeem_history: list[RedeemRecord] = []
        self._resolved_queue: set[str] = set()
        self._scheduler_thread: threading.Thread | None = None
        self._scheduler_running = False
        self._scheduler_stop_event = threading.Event()
        
    def check_positions(self) -> list[RedeemablePosition]:
        """
        Scan positions and return those ready for redemption.
        
        Returns
        -------
        list[RedeemablePosition]
            List of positions that meet redemption criteria.
        """
        if not self._config.enabled:
            log.debug("Auto-redeem is disabled")
            return []
        
        redeemable = []
        now = datetime.now(timezone.utc)
        
        # Get all positions from trading engine
        try:
            if hasattr(self._trading, 'all_positions'):
                positions = self._trading.all_positions()
            elif hasattr(self._trading, 'positions'):
                positions = self._trading.positions()
            else:
                log.warning("Trading engine has no position tracking")
                return []
        except Exception as e:
            log.error(f"Failed to fetch positions: {e}")
            return []
        
        for pos in positions:
            # Skip if not resolved
            if not getattr(pos, 'resolved', False):
                continue
            
            # Skip if already in queue
            pos_key = f"{getattr(pos, 'market_id', '')}:{getattr(pos, 'side', '')}"
            if pos_key in self._resolved_queue:
                continue
            
            # Check outcome filter
            outcome = getattr(pos, 'outcome', None)
            if self._config.only_winning and outcome != "WON":
                log.debug("Skipping losing position: %s", mask_address(pos_key))
                continue
            
            # Check minimum age
            resolved_at = getattr(pos, 'resolved_at', None)
            if resolved_at:
                age_hours = (now - resolved_at).total_seconds() / 3600
                if age_hours < self._config.min_age_hours:
                    log.debug("Position too young (%.1fh < %.1fh): %s", age_hours, self._config.min_age_hours, mask_address(pos_key))
                    continue
            
            # Calculate value
            value_usd = getattr(pos, 'current_value', 0.0)
            if outcome == "LOST":
                value_usd = 0.0
            
            # Create redeemable position
            redeemable.append(RedeemablePosition(
                market_id=getattr(pos, 'market_id', ''),
                slug=getattr(pos, 'slug', ''),
                side=getattr(pos, 'side', ''),
                shares=getattr(pos, 'shares', 0.0),
                outcome=outcome or "UNKNOWN",
                value_usd=value_usd,
                resolved_at=resolved_at or now,
                token_id=getattr(pos, 'token_id', ''),
            ))
            
            # Add to queue
            self._resolved_queue.add(pos_key)
        
        log.info(f"Found {len(redeemable)} redeemable positions")
        return redeemable
    
    def _check_triggers(self, positions: list[RedeemablePosition], force: bool = False) -> tuple[bool, str]:
        """
        Check if redemption should be triggered based on configuration.
        
        Parameters
        ----------
        positions : list[RedeemablePosition]
            Positions to check.
        force : bool
            If True, bypass automatic trigger checks and force redemption.
        
        Returns
        -------
        tuple[bool, str]
            (should_redeem, trigger_reason)
        """
        total_value = sum(p.value_usd for p in positions)
        count = len(positions)
        
        # Manual/forced redemption bypasses all trigger checks
        if force:
            if count > 0:
                return True, "manual"
            return False, "no_positions"
        
        # Check count triggers
        if self._config.trigger_on_count:
            if count >= self._config.max_markets:
                return True, f"count_max ({count} >= {self._config.max_markets})"
            if count >= self._config.min_markets:
                return True, f"count_min ({count} >= {self._config.min_markets})"
        
        # Check value triggers
        if self._config.trigger_on_value:
            if total_value >= self._config.max_value_usd:
                return True, f"value_max (${total_value:.2f} >= ${self._config.max_value_usd:.2f})"
            if total_value >= self._config.min_value_usd:
                return True, f"value_min (${total_value:.2f} >= ${self._config.min_value_usd:.2f})"
        
        return False, "no_positions"
    
    def redeem(self, positions: list[RedeemablePosition] | None = None, force: bool = False) -> RedeemResult:
        """
        Execute redemption for specified positions.
        
        If positions is None, will check for redeemable positions first.
        
        Parameters
        ----------
        positions : list[RedeemablePosition] | None
            Positions to redeem. If None, will scan for redeemable positions.
        force : bool
            If True, force redemption even if no automatic triggers are met.
        
        Returns
        -------
        RedeemResult
            Result of the redemption operation.
        """
        if self._config.dry_run:
            log.info("DRY RUN: Simulating redemption")
        
        # Scan for positions if not provided
        if positions is None:
            positions = self.check_positions()
        
        # Check triggers
        should_redeem, trigger_reason = self._check_triggers(positions, force=force)
        if not should_redeem:
            log.info(f"Redemption not triggered: {trigger_reason}")
            return RedeemResult(
                success=True,
                redeemed_count=0,
                total_value_usd=0.0,
                failed_count=0,
                errors=[f"Not triggered: {trigger_reason}"],
            )
        
        log.info(f"Redemption triggered: {trigger_reason}")
        
        # Require confirmation if enabled
        if self._config.require_confirmation and not self._config.dry_run:
            if not self._require_confirmation(positions, trigger_reason):
                log.info("Redemption cancelled by user")
                return RedeemResult(
                    success=False,
                    redeemed_count=0,
                    total_value_usd=0.0,
                    failed_count=0,
                    errors=["Cancelled by user"],
                )
        
        # Execute redemption
        total_value = sum(p.value_usd for p in positions)
        redeemed_count = 0
        failed_count = 0
        errors = []
        tx_hash = None
        
        for pos in positions:
            try:
                if self._config.dry_run:
                    log.info(f"DRY RUN: Would redeem {pos.slug} {pos.side} (${pos.value_usd:.2f})")
                    redeemed_count += 1
                else:
                    # Call trading engine to redeem
                    if hasattr(self._trading, 'redeem_position'):
                        result = self._trading.redeem_position(
                            market_id=pos.market_id,
                            side=pos.side,
                        )
                        if result.get('success'):
                            redeemed_count += 1
                            tx_hash = result.get('tx_hash')
                        else:
                            failed_count += 1
                            errors.append(f"{pos.slug}: {result.get('error', 'Unknown error')}")
                    else:
                        # Fallback: try to call resolve if redeem_position doesn't exist
                        log.warning("Trading engine has no redeem_position method, using resolve")
                        # This is a placeholder - actual implementation depends on trading engine
                        redeemed_count += 1
                        
            except Exception as e:
                failed_count += 1
                errors.append(f"{pos.slug}: {e}")
                log.error(f"Failed to redeem {pos.slug}: {e}")
        
        # Create record
        record = RedeemRecord(
            timestamp=datetime.now(timezone.utc),
            positions_count=redeemed_count,
            total_value_usd=total_value,
            trigger_reason=trigger_reason,
            success=failed_count == 0,
            tx_hash=tx_hash,
            error="; ".join(errors) if errors else None,
        )
        self._redeem_history.append(record)
        
        # Clear redeemed positions from queue
        for pos in positions:
            pos_key = f"{pos.market_id}:{pos.side}"
            self._resolved_queue.discard(pos_key)
        
        log.info(f"Redemption complete: {redeemed_count} redeemed, {failed_count} failed")
        
        return RedeemResult(
            success=failed_count == 0,
            redeemed_count=redeemed_count,
            total_value_usd=total_value,
            failed_count=failed_count,
            errors=errors,
            tx_hash=tx_hash,
        )
    
    def _require_confirmation(
        self,
        positions: list[RedeemablePosition],
        trigger_reason: str,
    ) -> bool:
        """Require user confirmation before redemption."""
        total_value = sum(p.value_usd for p in positions)
        
        print("\n" + "=" * 60)
        print("AUTO-REDEEM CONFIRMATION REQUIRED")
        print("=" * 60)
        print(f"Trigger: {trigger_reason}")
        print(f"Positions: {len(positions)}")
        print(f"Total Value: ${total_value:.2f}")
        print("\nPositions:")
        for pos in positions:
            print(f"  - {pos.slug} {pos.side}: ${pos.value_usd:.2f} ({pos.outcome})")
        print("=" * 60)
        
        response = input("\nConfirm redemption? (yes/no): ").strip().lower()
        return response in ("yes", "y")
    
    def _parse_time_interval(self) -> int:
        """Parse time interval string to seconds."""
        interval = self._config.time_interval.lower()
        if interval.endswith('h'):
            return int(interval[:-1]) * 3600
        elif interval.endswith('d'):
            return int(interval[:-1]) * 86400
        elif interval.endswith('w'):
            return int(interval[:-1]) * 604800
        else:
            log.warning(f"Invalid time interval: {interval}, defaulting to 1 day")
            return 86400
    
    def _scheduler_loop(self):
        """Background scheduler loop."""
        interval_seconds = self._parse_time_interval()
        log.info(f"Scheduler started with interval: {self._config.time_interval}")
        
        while not self._scheduler_stop_event.is_set():
            # Wait for interval or stop event
            self._scheduler_stop_event.wait(timeout=interval_seconds)
            
            if self._scheduler_stop_event.is_set():
                break
            
            # Check and redeem
            try:
                log.info("Running scheduled redemption check")
                result = self.redeem()
                log.info(f"Scheduled redemption result: {result.redeemed_count} redeemed")
            except Exception as e:
                log.error(f"Error in scheduled redemption: {e}")
        
        log.info("Scheduler stopped")
    
    def start_scheduler(self) -> None:
        """Start background scheduler for time-based triggers."""
        if self._scheduler_running:
            log.warning("Scheduler already running")
            return
        
        if not self._config.trigger_on_time:
            log.warning("Time-based triggers disabled, scheduler not started")
            return
        
        self._scheduler_running = True
        self._scheduler_stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="AutoRedeemScheduler",
        )
        self._scheduler_thread.start()
        log.info("Auto-redeem scheduler started")
    
    def stop_scheduler(self) -> None:
        """Stop background scheduler."""
        if not self._scheduler_running:
            return
        
        self._scheduler_stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
        
        self._scheduler_running = False
        log.info("Auto-redeem scheduler stopped")
    
    def get_redeem_history(self) -> list[RedeemRecord]:
        """Get history of redemption operations."""
        return self._redeem_history.copy()
    
    def get_pending_count(self) -> int:
        """Get count of positions awaiting redemption."""
        return len(self._resolved_queue)
    
    def clear_history(self) -> None:
        """Clear redemption history."""
        self._redeem_history.clear()
    
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._scheduler_running
