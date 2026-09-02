"""Position sync from chain — extracted from RealTradingEngine."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from ..core import FALLBACK_PRICE

log = logging.getLogger(__name__)


class RealPositionSyncMixin:
    """Mixin for syncing positions from Alchemy / chain."""

    _alchemy_client: object
    _wallet: object
    _clob_client: object
    _positions: dict
    _real_wallet_manager: object
    _use_multi_wallet: bool
    _last_position_sync: float
    _position_sync_ttl: float

    def _sync_single_wallet_positions(self, address: str, clob_client, positions_dict: dict) -> None:
        balances = self._alchemy_client.get_token_balances(address)  # type: ignore
        transfers = self._alchemy_client.get_asset_transfers(address)  # type: ignore
        token_ids = list(balances.keys())
        if not token_ids:
            return
        metadata = self._alchemy_client.fetch_polymarket_metadata(token_ids)  # type: ignore
        transfers_by_token: dict[str, list[dict]] = {}
        for t in transfers:
            for m in t.get("erc1155Metadata", []):
                tid = m.get("tokenId", "")
                if tid:
                    transfers_by_token.setdefault(tid, []).append(t)
        orders = self._get_all_orders_across_wallets()  # type: ignore
        for token_id, amount in balances.items():
            if amount <= 0:
                continue
            meta = metadata.get(token_id, {})
            market_id = meta.get("market_id", token_id)
            slug = meta.get("slug", token_id)
            question = meta.get("question", "Unknown Market")
            gamma_price = float(meta.get("price", 0.0) or 0)
            side = meta.get("side", "UP")
            clob_token_ids = meta.get("clobTokenIds", "")
            if isinstance(clob_token_ids, str) and clob_token_ids:
                tokens = [t.strip() for t in clob_token_ids.split(",")]
                if len(tokens) > 1:
                    token_dec = str(int(token_id, 16)) if token_id.startswith("0x") else token_id
                    side = "UP" if tokens[0] == token_dec else "DOWN"
            fill_price = None
            for order in orders.values():
                if order.market_id == market_id and order.side == side and float(getattr(order, "avg_fill_price", 0) or 0) > 0:
                    fill_price = order.avg_fill_price
                    break
            if fill_price is None and gamma_price > 0:
                fill_price = gamma_price
            if fill_price is None:
                try:
                    ob = clob_client.get_orderbook(token_id)
                    bids = ob.get("bids", [])
                    asks = ob.get("asks", [])
                    best_bid = float(bids[0][0]) if bids else 0.0
                    best_ask = float(asks[0][0]) if asks else 0.0
                    if best_bid > 0 and best_ask > 0:
                        fill_price = (best_bid + best_ask) / 2.0
                    elif best_bid > 0:
                        fill_price = best_bid
                    elif best_ask > 0:
                        fill_price = best_ask
                except Exception:
                    log.warning("Failed to fetch orderbook for fill price", exc_info=True)
            position_key = f"{market_id}:{side}"
            if fill_price is None and position_key in positions_dict:
                fill_price = positions_dict[position_key].avg_price
            if fill_price is None or fill_price <= 0:
                fill_price = FALLBACK_PRICE
            cost_basis = amount * fill_price
            current_price = gamma_price if gamma_price > 0 else fill_price
            entry_time = None
            incoming = [t for t in transfers_by_token.get(token_id, []) if t.get("to", "").lower() == address.lower()]
            if incoming:
                timestamps: list[datetime] = []
                for t in incoming:
                    ts = t.get("metadata", {}).get("blockTimestamp", "")
                    if ts:
                        try:
                            timestamps.append(datetime.fromisoformat(str(ts).replace("Z", "+00:00")))
                        except (ValueError, TypeError):
                            pass
                if timestamps:
                    entry_time = min(timestamps)
            from .real_orders import RealPosition
            position = RealPosition(
                market_id=market_id,
                slug=slug,
                question=question,
                side=side,
                shares=amount,
                avg_price=fill_price,
                current_price=current_price,
                cost_basis=cost_basis,
                current_value=amount * current_price,
                entry_time=entry_time,
            )
            positions_dict[position_key] = position

    def sync_positions_from_chain(self) -> None:
        log.debug("Syncing positions from blockchain...")
        if self._use_multi_wallet and self._real_wallet_manager:
            for wallet in self._real_wallet_manager.get_all_wallets():  # type: ignore
                try:
                    self._sync_single_wallet_positions(wallet.address, wallet.clob_client, wallet.positions)
                except Exception:
                    log.exception("Failed to sync positions for wallet %s", getattr(wallet, "wallet_id", "?"))
        else:
            self._sync_single_wallet_positions(self._wallet.address, self._clob_client, self._positions)  # type: ignore

    def positions(self) -> list:
        now = time.time()
        if now - self._last_position_sync > self._position_sync_ttl:
            try:
                self.sync_positions_from_chain()
            except Exception:
                log.debug("positions() sync failed, returning cached", exc_info=True)
            self._last_position_sync = now
        positions = self._get_all_positions_across_wallets()  # type: ignore
        return [p for p in positions.values() if not getattr(p, "resolved", False)]

    def all_positions(self) -> list:
        now = time.time()
        if now - self._last_position_sync > self._position_sync_ttl:
            try:
                self.sync_positions_from_chain()
            except Exception:
                log.debug("all_positions() sync failed", exc_info=True)
            self._last_position_sync = now
        positions = self._get_all_positions_across_wallets()  # type: ignore
        return list(positions.values())
