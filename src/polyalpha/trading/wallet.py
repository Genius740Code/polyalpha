"""
Multi-wallet support for paper trading.

This module provides PaperWallet and WalletManager classes for managing
multiple paper trading wallets with different selection strategies.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional, List
from enum import Enum

from ..utils.logging_utils import mask_address
from ..core import (
    InsufficientBalance,
    OrderNotFound,
    PositionNotFound,
    TAKER_FEE_RATE,
    PRICE_ROUNDING,
    DISPLAY_ROUNDING_SHARES,
    DISPLAY_ROUNDING_PRICES,
    DISPLAY_ROUNDING_PNL,
    DISPLAY_ROUNDING_PNL_PCT,
)

if TYPE_CHECKING:
    from .real_config import RealTradingConfig

from .paper_config import PaperConfig
from .paper_types import PaperOrder, PaperPosition
from .paper_risk import RiskManager

log = logging.getLogger(__name__)


class WalletSelectionStrategy(Enum):
    """Wallet selection strategies."""
    ROUND_ROBIN = "round_robin"
    BALANCE_BASED = "balance_based"
    RANDOM = "random"
    CUSTOM = "custom"


@dataclass
class PaperWallet:
    """
    Individual paper trading wallet.
    
    Each wallet maintains its own balance, orders, positions, and risk limits.
    """
    
    wallet_id: str
    balance: float
    config: PaperConfig = field(default_factory=PaperConfig)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Internal state
    _orders: dict[str, PaperOrder] = field(default_factory=dict)
    _positions: dict[str, PaperPosition] = field(default_factory=dict)
    _risk_manager: Optional[RiskManager] = None
    
    def __post_init__(self):
        """Initialize wallet after creation."""
        if self._risk_manager is None:
            self._risk_manager = RiskManager(self.config, self.balance)
        log.info("PaperWallet created: %s with balance $%.2f", self.wallet_id, self.balance)
    
    @property
    def orders(self) -> dict[str, PaperOrder]:
        """Get all orders for this wallet."""
        return self._orders
    
    @property
    def positions(self) -> dict[str, PaperPosition]:
        """Get all positions for this wallet."""
        return self._positions
    
    @property
    def risk_manager(self) -> RiskManager:
        """Get the risk manager for this wallet."""
        return self._risk_manager
    
    def set_balance(self, amount: float) -> None:
        """Set wallet balance."""
        if amount < 0:
            raise ValueError("Balance cannot be negative")
        self.balance = float(amount)
        log.debug("PaperWallet %s balance set to $%.2f", self.wallet_id, amount)
    
    def add_order(self, order: PaperOrder) -> None:
        """Add an order to this wallet."""
        self._orders[order.id] = order
        log.debug("PaperWallet %s: order %s added", self.wallet_id, order.id[:8])
    
    def get_order(self, order_id: str) -> PaperOrder:
        """Get an order by ID."""
        if order_id not in self._orders:
            raise OrderNotFound(f"Order {order_id} not found in wallet {self.wallet_id}")
        return self._orders[order_id]
    
    def remove_order(self, order_id: str) -> None:
        """Remove an order from this wallet."""
        if order_id in self._orders:
            del self._orders[order_id]
            log.debug("PaperWallet %s: order %s removed", self.wallet_id, order_id[:8])
    
    def add_position(self, position: PaperPosition) -> None:
        """Add or update a position for this wallet."""
        key = f"{position.market_id}:{position.side}"
        self._positions[key] = position
        log.debug("PaperWallet %s: position %s added/updated", self.wallet_id, mask_address(key))
    
    def get_position(self, market_id: str, side: str) -> PaperPosition:
        """Get a position by market and side."""
        key = f"{market_id}:{side}"
        if key not in self._positions:
            raise PositionNotFound(f"Position {key} not found in wallet {self.wallet_id}")
        return self._positions[key]
    
    def get_all_positions(self) -> List[PaperPosition]:
        """Get all positions for this wallet."""
        return list(self._positions.values())
    
    def remove_position(self, market_id: str, side: str) -> None:
        """Remove a position from this wallet."""
        key = f"{market_id}:{side}"
        if key in self._positions:
            del self._positions[key]
            log.debug("PaperWallet %s: position %s removed", self.wallet_id, mask_address(key))
    
    def get_summary(self) -> dict:
        """Get wallet summary statistics."""
        total_cost_basis = sum(p.cost_basis for p in self._positions.values())
        total_current_value = sum(p.current_value for p in self._positions.values())
        total_pnl = sum(p.pnl for p in self._positions.values())
        
        return {
            "wallet_id": self.wallet_id,
            "balance": self.balance,
            "total_positions": len(self._positions),
            "total_orders": len(self._orders),
            "total_cost_basis": total_cost_basis,
            "total_current_value": total_current_value,
            "total_pnl": total_pnl,
            "available_balance": self.balance - total_cost_basis,
        }


@dataclass
class WalletManager:
    """
    Manager for multiple paper trading wallets.
    
    Handles wallet selection strategies and provides aggregated statistics.
    """
    
    wallets: dict[str, PaperWallet] = field(default_factory=dict)
    selection_strategy: WalletSelectionStrategy = WalletSelectionStrategy.ROUND_ROBIN
    custom_selector: Optional[Callable] = None
    
    # Round-robin state
    _round_robin_index: int = 0
    
    def add_wallet(self, wallet: PaperWallet) -> None:
        """Add a wallet to the manager."""
        if wallet.wallet_id in self.wallets:
            raise ValueError(f"Wallet {wallet.wallet_id} already exists")
        self.wallets[wallet.wallet_id] = wallet
        log.info("WalletManager: added wallet %s", wallet.wallet_id)
    
    def remove_wallet(self, wallet_id: str) -> None:
        """Remove a wallet from the manager."""
        if wallet_id in self.wallets:
            del self.wallets[wallet_id]
            log.info("WalletManager: removed wallet %s", wallet_id)
    
    def get_wallet(self, wallet_id: str) -> PaperWallet:
        """Get a specific wallet by ID."""
        if wallet_id not in self.wallets:
            raise ValueError(f"Wallet {wallet_id} not found")
        return self.wallets[wallet_id]
    
    def get_all_wallets(self) -> List[PaperWallet]:
        """Get all wallets."""
        return list(self.wallets.values())
    
    def select_wallet(self, strategy: Optional[WalletSelectionStrategy] = None) -> PaperWallet:
        """
        Select a wallet based on the configured strategy.
        
        Parameters
        ----------
        strategy : WalletSelectionStrategy, optional
            Override the default strategy for this selection.
        
        Returns
        -------
        PaperWallet
            The selected wallet.
        """
        if not self.wallets:
            raise ValueError("No wallets available")
        
        if len(self.wallets) == 1:
            return next(iter(self.wallets.values()))
        
        strategy = strategy or self.selection_strategy
        
        if strategy == WalletSelectionStrategy.ROUND_ROBIN:
            return self._select_round_robin()
        elif strategy == WalletSelectionStrategy.BALANCE_BASED:
            return self._select_balance_based()
        elif strategy == WalletSelectionStrategy.RANDOM:
            return self._select_random()
        elif strategy == WalletSelectionStrategy.CUSTOM:
            return self._select_custom()
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    def _select_round_robin(self) -> PaperWallet:
        """Select wallet using round-robin strategy."""
        wallet_ids = list(self.wallets.keys())
        selected_id = wallet_ids[self._round_robin_index % len(wallet_ids)]
        self._round_robin_index += 1
        return self.wallets[selected_id]
    
    def _select_balance_based(self) -> PaperWallet:
        """Select wallet with highest balance."""
        return max(self.wallets.values(), key=lambda w: w.balance)
    
    def _select_random(self) -> PaperWallet:
        """Select wallet randomly."""
        import random
        return random.choice(list(self.wallets.values()))
    
    def _select_custom(self) -> PaperWallet:
        """Select wallet using custom selector function."""
        if self.custom_selector is None:
            raise ValueError("Custom selector not provided")
        return self.custom_selector(list(self.wallets.values()))
    
    def set_selection_strategy(self, strategy: WalletSelectionStrategy) -> None:
        """Set the wallet selection strategy."""
        self.selection_strategy = strategy
        self._round_robin_index = 0  # Reset round-robin index
        log.info("WalletManager: selection strategy set to %s", strategy.value)
    
    def set_custom_selector(self, selector: Callable) -> None:
        """Set a custom wallet selector function."""
        self.custom_selector = selector
        self.selection_strategy = WalletSelectionStrategy.CUSTOM
        log.info("WalletManager: custom selector set")
    
    def get_aggregated_summary(self) -> dict:
        """Get aggregated statistics across all wallets."""
        if not self.wallets:
            return {
                "total_wallets": 0,
                "total_balance": 0.0,
                "total_positions": 0,
                "total_orders": 0,
                "total_pnl": 0.0,
            }
        
        summaries = [w.get_summary() for w in self.wallets.values()]
        
        return {
            "total_wallets": len(self.wallets),
            "total_balance": sum(s["balance"] for s in summaries),
            "total_positions": sum(s["total_positions"] for s in summaries),
            "total_orders": sum(s["total_orders"] for s in summaries),
            "total_cost_basis": sum(s["total_cost_basis"] for s in summaries),
            "total_current_value": sum(s["total_current_value"] for s in summaries),
            "total_pnl": sum(s["total_pnl"] for s in summaries),
            "total_available_balance": sum(s["available_balance"] for s in summaries),
        }
    
    def get_per_wallet_summary(self) -> dict[str, dict]:
        """Get per-wallet summary statistics."""
        return {wallet_id: wallet.get_summary() for wallet_id, wallet in self.wallets.items()}


# ── Real Trading Wallet Classes ────────────────────────────────────────────────────

class RealWallet:
    """
    Individual real trading wallet with its own blockchain connection and state.

    Each wallet has its own private key, WalletManager (blockchain ops),
    ClobClient (order signing), orders, positions, balance, and risk manager.
    """

    def __init__(
        self,
        wallet_id: str,
        private_key: str,
        rpc_url: str,
        polymarket_api_key: str,
        config: object = None,
        address: Optional[str] = None,
        polymarket_api_secret: str = "",
        polymarket_api_passphrase: str = "",
        clob_timeout: int = 30,
        clob_retry_attempts: int = 3,
        clob_retry_delay: float = 1.0,
        simulate: bool = False,
    ):
        from .real_wallet import WalletManager
        from .real_risk import RiskManager

        self.wallet_id = wallet_id
        self.wallet_manager = WalletManager(
            private_key, rpc_url,
            log_balance_updates=config.log_balance_updates if config else False,
        )
        self.config = config

        from .clob_client import ClobClient
        self._clob_client = ClobClient(
            api_key=polymarket_api_key,
            private_key=private_key,
            rpc_url=rpc_url,
            api_secret=polymarket_api_secret or (config.polymarket_api_secret if config else ""),
            api_passphrase=polymarket_api_passphrase or (config.polymarket_api_passphrase if config else ""),
            timeout=clob_timeout,
            retry_attempts=clob_retry_attempts,
            retry_delay=clob_retry_delay,
            simulate=simulate,
        )
        self._risk_manager = RiskManager(config) if config else None
        self.orders: dict = {}
        self.positions: dict = {}
        self.balance: float = 0.0
        self.allowance: float = 0.0

        self._address: Optional[str] = address
        log.info("RealWallet created: %s", wallet_id)

    @property
    def clob_client(self):
        """Get the CLOB client for this wallet."""
        return self._clob_client

    @property
    def risk_manager(self):
        """Get the risk manager for this wallet."""
        return self._risk_manager

    @property
    def address(self) -> Optional[str]:
        """Get the wallet address."""
        if self._address:
            return self._address
        return self.wallet_manager.address

    def refresh_balance(self) -> None:
        """Refresh balance and allowance from blockchain."""
        self.balance = self.wallet_manager.get_balance()
        from .alchemy_client import AlchemyClient
        self.allowance = self.wallet_manager.get_allowance(AlchemyClient.CTF_ADDRESS)
        if self.config and self.config.log_balance_updates:
            log.debug("RealWallet %s: balance=%.2f, allowance=%.2f",
                      self.wallet_id, self.balance, self.allowance)

    def get_summary(self) -> dict:
        """Get wallet summary statistics."""
        return {
            "wallet_id": self.wallet_id,
            "balance": self.balance,
            "allowance": self.allowance,
            "total_orders": len(self.orders),
            "total_positions": len(self.positions),
            "address": self.address,
        }


class RealTradingWalletManager:
    """
    Manager for multiple real trading wallets.

    Handles wallet creation, selection strategies, and aggregated reporting.
    """

    def __init__(self):
        self.wallets: dict[str, RealWallet] = {}
        self.selection_strategy: WalletSelectionStrategy = WalletSelectionStrategy.ROUND_ROBIN
        self.custom_selector: Optional[Callable] = None
        self._round_robin_index: int = 0
        self._alchemy_client = None

    def add_wallet(self, wallet: RealWallet) -> None:
        """Add a wallet to the manager."""
        if wallet.wallet_id in self.wallets:
            raise ValueError(f"Wallet {wallet.wallet_id} already exists")
        self.wallets[wallet.wallet_id] = wallet
        log.info("RealTradingWalletManager: added wallet %s", wallet.wallet_id)

    def remove_wallet(self, wallet_id: str) -> None:
        """Remove a wallet from the manager."""
        if wallet_id in self.wallets:
            del self.wallets[wallet_id]
            log.info("RealTradingWalletManager: removed wallet %s", wallet_id)

    def get_wallet(self, wallet_id: str) -> RealWallet:
        """Get a specific wallet by ID."""
        if wallet_id not in self.wallets:
            raise ValueError(f"Wallet {wallet_id} not found")
        return self.wallets[wallet_id]

    def get_all_wallets(self) -> list[RealWallet]:
        """Get all wallets."""
        return list(self.wallets.values())

    def select_wallet(self, strategy: Optional[WalletSelectionStrategy] = None) -> RealWallet:
        """
        Select a wallet based on the configured strategy.

        Parameters
        ----------
        strategy : WalletSelectionStrategy, optional
            Override the default strategy for this selection.

        Returns
        -------
        RealWallet
            The selected wallet.
        """
        if not self.wallets:
            raise ValueError("No wallets available")

        if len(self.wallets) == 1:
            return next(iter(self.wallets.values()))

        strategy = strategy or self.selection_strategy

        if strategy == WalletSelectionStrategy.ROUND_ROBIN:
            return self._select_round_robin()
        elif strategy == WalletSelectionStrategy.BALANCE_BASED:
            return self._select_balance_based()
        elif strategy == WalletSelectionStrategy.RANDOM:
            return self._select_random()
        elif strategy == WalletSelectionStrategy.CUSTOM:
            return self._select_custom()
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _select_round_robin(self) -> RealWallet:
        """Select wallet using round-robin strategy."""
        wallet_ids = list(self.wallets.keys())
        selected_id = wallet_ids[self._round_robin_index % len(wallet_ids)]
        self._round_robin_index += 1
        return self.wallets[selected_id]

    def _select_balance_based(self) -> RealWallet:
        """Select wallet with highest balance."""
        return max(self.wallets.values(), key=lambda w: w.balance)

    def _select_random(self) -> RealWallet:
        """Select wallet randomly."""
        import random
        return random.choice(list(self.wallets.values()))

    def _select_custom(self) -> RealWallet:
        """Select wallet using custom selector function."""
        if self.custom_selector is None:
            raise ValueError("Custom selector not provided")
        return self.custom_selector(list(self.wallets.values()))

    def set_selection_strategy(self, strategy: WalletSelectionStrategy) -> None:
        """Set the wallet selection strategy."""
        self.selection_strategy = strategy
        self._round_robin_index = 0
        log.info("RealTradingWalletManager: strategy set to %s", strategy.value)

    def set_custom_selector(self, selector: Callable) -> None:
        """Set a custom wallet selector function."""
        self.custom_selector = selector
        self.selection_strategy = WalletSelectionStrategy.CUSTOM
        log.info("RealTradingWalletManager: custom selector set")

    def refresh_all_balances(self) -> None:
        """Refresh balances for all wallets from blockchain."""
        for wallet in self.wallets.values():
            try:
                wallet.refresh_balance()
            except Exception as e:
                log.error("Failed to refresh balance for wallet %s: %s", wallet.wallet_id, e)

    def get_aggregated_summary(self) -> dict:
        """Get aggregated statistics across all wallets."""
        if not self.wallets:
            return {
                "total_wallets": 0,
                "total_balance": 0.0,
                "total_orders": 0,
                "total_positions": 0,
            }

        summaries = [w.get_summary() for w in self.wallets.values()]
        return {
            "total_wallets": len(self.wallets),
            "total_balance": sum(s["balance"] for s in summaries),
            "total_orders": sum(s["total_orders"] for s in summaries),
            "total_positions": sum(s["total_positions"] for s in summaries),
        }

    def get_per_wallet_summary(self) -> dict[str, dict]:
        """Get per-wallet summary statistics."""
        return {wid: w.get_summary() for wid, w in self.wallets.items()}

    def find_order_across_wallets(self, order_id: str):
        """Find an order across all wallets."""
        for wallet in self.wallets.values():
            if order_id in wallet.orders:
                return wallet.orders[order_id], wallet
        return None, None

    def find_position_across_wallets(self, market_id: str, side: str):
        """Find a position across all wallets."""
        key = f"{market_id}:{side}"
        for wallet in self.wallets.values():
            if key in wallet.positions:
                return wallet.positions[key], wallet
        return None, None

    def get_all_orders(self) -> dict:
        """Get all orders across all wallets."""
        all_orders = {}
        for wallet in self.wallets.values():
            all_orders.update(wallet.orders)
        return all_orders

    def get_all_positions(self) -> dict:
        """Get all positions across all wallets."""
        all_positions = {}
        for wallet in self.wallets.values():
            all_positions.update(wallet.positions)
        return all_positions
