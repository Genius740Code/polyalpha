"""
CLOB Client — Polymarket CLOB API integration.

This module provides a client for interacting with the Polymarket CLOB API,
including order placement, cancellation, and orderbook queries.

Usage
-----
    from polyalpha.trading.clob_client import ClobClient

    client = ClobClient(
        api_key="your-api-key",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
    )

    # Place an order
    response = client.place_order(
        token_id="token-id",
        side="buy",
        price=0.55,
        size=10.0,
        order_type="limit",
    )

    # Get order status
    status = client.get_order_status(order_id="order-id")

    # Cancel an order
    response = client.cancel_order(order_id="order-id")

    # Get orderbook
    orderbook = client.get_orderbook(token_id="token-id")

    # Get balance
    balance = client.get_balance()
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..core import NetworkError, OrderRejected, OrderTimeout, TransientError

log = logging.getLogger(__name__)


class ClobClient:
    """
    Client for Polymarket CLOB API.

    Handles order placement, cancellation, and orderbook queries for the
    Polymarket CLOB (Central Limit Order Book).

    Parameters
    ----------
    api_key : str
        Polymarket API key for authentication
    private_key : str
        Private key for signing orders
    rpc_url : str
        Polygon RPC URL for blockchain interaction
    base_url : str, optional
        Base URL for CLOB API (default: https://clob.polymarket.com)
    timeout : int, optional
        Request timeout in seconds (default: 10)
    retry_attempts : int, optional
        Number of retry attempts for failed requests (default: 3)
    retry_delay : float, optional
        Delay between retry attempts in seconds (default: 1.0)
    """

    def __init__(
        self,
        api_key: str,
        private_key: str,
        rpc_url: str,
        base_url: str = "https://clob.polymarket.com",
        timeout: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        simulate: bool = False,
    ):
        self.api_key = api_key
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.base_url = base_url
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.simulate = simulate

        # Session for HTTP requests (lazy initialization)
        self._session = None
        self._address: Optional[str] = None

        log.info("ClobClient initialized for %s (simulate=%s)", base_url, simulate)

    def _get_session(self):
        """Get or create HTTP session."""
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                self._session.headers.update({
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                })
            except ImportError:
                log.warning("requests library not available. CLOB operations will be simulated.")
                self._session = None
        return self._session

    def _get_address(self) -> str:
        """Get wallet address from private key."""
        if self._address is None:
            if self.simulate:
                # Simulated address for testing
                self._address = "0x" + "0" * 40
            else:
                try:
                    from eth_account import Account
                    account = Account.from_key(self.private_key)
                    self._address = account.address
                except ImportError:
                    log.warning("eth_account not available. Using simulated address.")
                    self._address = "0x" + self.private_key[:40]
        return self._address

    def _sign_order(self, order_data: dict) -> str:
        """
        Sign order data with private key.

        Parameters
        ----------
        order_data : dict
            Order data to sign

        Returns
        -------
        str
            Signature
        """
        if self.simulate:
            # Simulated signature for testing
            return "0x" + "a" * 130

        try:
            from eth_account import Account
            import json

            message = json.dumps(order_data, sort_keys=True)
            message_hash = Account.from_key(self.private_key).sign_message(
                text=message
            )
            return message_hash.signature.hex()
        except ImportError:
            log.warning("eth_account not available. Using simulated signature.")
            return "0x" + "a" * 130

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """
        Make HTTP request to CLOB API with retry logic.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, DELETE)
        endpoint : str
            API endpoint
        data : dict, optional
            Request body data
        params : dict, optional
            Query parameters

        Returns
        -------
        dict
            Response data

        Raises
        ------
        NetworkError
            If request fails after retries
        OrderRejected
            If order is rejected by CLOB
        """
        # Use simulation mode if enabled
        if self.simulate:
            return self._simulate_response(method, endpoint, data)

        session = self._get_session()
        url = f"{self.base_url}{endpoint}"

        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                if session is None:
                    # Simulated response for testing without requests
                    return self._simulate_response(method, endpoint, data)

                if method == "GET":
                    response = session.get(url, params=params, timeout=self.timeout)
                elif method == "POST":
                    response = session.post(url, json=data, timeout=self.timeout)
                elif method == "DELETE":
                    response = session.delete(url, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

            except Exception as e:
                last_error = e
                if attempt < self.retry_attempts - 1:
                    log.warning(
                        "Request attempt %d failed: %s. Retrying in %.1fs...",
                        attempt + 1, e, self.retry_delay
                    )
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    log.error("All %d request attempts failed", self.retry_attempts)
                    raise NetworkError(f"Request failed after {self.retry_attempts} attempts: {e}")

        raise NetworkError(f"Request failed: {last_error}")

    def _simulate_response(self, method: str, endpoint: str, data: Optional[dict]) -> dict:
        """
        Simulate API response for testing without actual API access.

        Parameters
        ----------
        method : str
            HTTP method
        endpoint : str
            API endpoint
        data : dict, optional
            Request data

        Returns
        -------
        dict
            Simulated response
        """
        import uuid

        if method == "POST" and "place" in endpoint:
            return {
                "order_id": str(uuid.uuid4()),
                "status": "pending",
                "token_id": data.get("token_id", "unknown"),
                "side": data.get("side", "unknown"),
                "price": data.get("price", 0.0),
                "size": data.get("size", 0.0),
            }
        elif method == "DELETE" and endpoint.endswith("/cancel"):
            return {
                "order_id": endpoint.split("/")[-2],
                "status": "cancelled",
            }
        elif method == "GET" and "status" in endpoint:
            return {
                "order_id": endpoint.split("/")[-2],
                "status": "filled",
                "filled_size": 10.0,
                "avg_price": 0.55,
            }
        elif method == "GET" and "orderbook" in endpoint:
            return {
                "bids": [[0.54, 100.0], [0.53, 50.0]],
                "asks": [[0.56, 100.0], [0.57, 50.0]],
            }
        elif method == "GET" and "balance" in endpoint:
            return {
                "address": self._get_address(),
                "usdc_balance": 1000.0,
                "allowance": 10000.0,
            }
        else:
            return {}

    def place_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str = "limit",
        nonce: Optional[int] = None,
    ) -> dict:
        """
        Place an order on the CLOB.

        Parameters
        ----------
        token_id : str
            Token ID to trade
        side : str
            Order side ("buy" or "sell")
        price : float
            Order price
        size : float
            Order size in shares
        order_type : str, optional
            Order type ("limit" or "market", default: "limit")
        nonce : int, optional
            Order nonce (auto-generated if not provided)

        Returns
        -------
        dict
            Order response with order_id and status

        Raises
        ------
        OrderRejected
            If order is rejected by CLOB
        NetworkError
            If request fails
        """
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got '{side}'")

        if order_type not in ("limit", "market"):
            raise ValueError(f"order_type must be 'limit' or 'market', got '{order_type}'")

        if nonce is None:
            nonce = int(time.time() * 1000)

        order_data = {
            "token_id": token_id,
            "side": side,
            "price": price,
            "size": size,
            "order_type": order_type,
            "nonce": nonce,
            "maker": self._get_address(),
        }

        # Sign the order
        signature = self._sign_order(order_data)
        order_data["signature"] = signature

        log.info(
            "Placing %s order: %s %s @ %.4f, size=%.2f",
            order_type, side, token_id, price, size
        )

        try:
            response = self._make_request("POST", "/orders/place", data=order_data)
            log.info("Order placed successfully: %s", response.get("order_id"))
            return response
        except Exception as e:
            log.error("Failed to place order: %s", e)
            raise OrderRejected(f"Order rejected: {e}")

    def cancel_order(self, order_id: str) -> dict:
        """
        Cancel an order on the CLOB.

        Parameters
        ----------
        order_id : str
            Order ID to cancel

        Returns
        -------
        dict
            Cancellation response

        Raises
        ------
        NetworkError
            If request fails
        OrderTimeout
            If order cancellation times out
        """
        log.info("Cancelling order: %s", order_id)

        try:
            response = self._make_request("DELETE", f"/orders/{order_id}/cancel")
            log.info("Order cancelled successfully: %s", order_id)
            return response
        except Exception as e:
            log.error("Failed to cancel order %s: %s", order_id, e)
            raise NetworkError(f"Failed to cancel order: {e}")

    def get_order_status(self, order_id: str) -> dict:
        """
        Get order status from CLOB.

        Parameters
        ----------
        order_id : str
            Order ID to query

        Returns
        -------
        dict
            Order status with fields: status, filled_size, avg_price, etc.

        Raises
        ------
        NetworkError
            If request fails
        """
        log.debug("Getting order status: %s", order_id)

        try:
            response = self._make_request("GET", f"/orders/{order_id}/status")
            return response
        except Exception as e:
            log.error("Failed to get order status %s: %s", order_id, e)
            raise NetworkError(f"Failed to get order status: {e}")

    def get_orderbook(self, token_id: str) -> dict:
        """
        Get current orderbook for a token.

        Parameters
        ----------
        token_id : str
            Token ID to query

        Returns
        -------
        dict
            Orderbook with bids and asks arrays
            Format: {"bids": [[price, size], ...], "asks": [[price, size], ...]}

        Raises
        ------
        NetworkError
            If request fails
        """
        log.debug("Getting orderbook for token: %s", token_id)

        try:
            response = self._make_request("GET", f"/orderbook/{token_id}")
            return response
        except Exception as e:
            log.error("Failed to get orderbook for %s: %s", token_id, e)
            raise NetworkError(f"Failed to get orderbook: {e}")

    def get_balance(self) -> dict:
        """
        Get account balance from CLOB.

        Returns
        -------
        dict
            Balance information with fields: address, usdc_balance, allowance

        Raises
        ------
        NetworkError
            If request fails
        """
        log.debug("Getting account balance")

        try:
            response = self._make_request("GET", "/account/balance")
            return response
        except Exception as e:
            log.error("Failed to get balance: %s", e)
            raise NetworkError(f"Failed to get balance: {e}")

    def close(self) -> None:
        """Close HTTP session."""
        if self._session is not None:
            self._session.close()
            self._session = None
        log.info("ClobClient closed")
