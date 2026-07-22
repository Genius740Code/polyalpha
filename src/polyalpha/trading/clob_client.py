"""
CLOB Client — Polymarket CLOB API integration.

This module provides a client for interacting with the Polymarket CLOB API,
including order placement, cancellation, and orderbook queries.

Uses EIP-712 typed data signing for order payloads and HMAC-SHA256
(L2) authentication for all API requests.

Usage
-----
    from polyalpha.trading.clob_client import ClobClient

    # Derive or provide L2 API credentials
    client = ClobClient(
        api_key="your-api-key",
        api_secret="your-api-secret",
        api_passphrase="your-api-passphrase",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
    )

    # Or derive credentials via L1 wallet auth
    client = ClobClient(
        api_key="",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
    )
    creds = client.derive_api_credentials()  # one-time setup

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

    # Get balance
    balance = client.get_balance()

For order-book data (bids, asks, mid-price, spreads), use
``ClobBookClient`` from ``polyalpha.orderbook`` instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

import httpx

from ..core import NetworkError, OrderRejected, OrderTimeout, RateLimitExceeded

log = logging.getLogger(__name__)

# ── Polymarket CLOB Constants ─────────────────────────────────────────────────

CLOB_CONTRACT = "0x4D16C7936c63648848F7C1d7A5bCfC6C6fF1C8f7"
NEG_RISK_CLOB_CONTRACT = "0xC5d563960C6A6e42E927C3D34E7a5E1CCf63Cb1e"
POLYGON_CHAIN_ID = 137

# EIP-712 Domain for CLOB orders
EIP712_CLOB_DOMAIN = {
    "name": "Polymarket CLOB",
    "version": "1",
    "chainId": POLYGON_CHAIN_ID,
    "verifyingContract": CLOB_CONTRACT,
}

# EIP-712 Domain for API key derivation
EIP712_DERIVE_KEY_DOMAIN = {
    "name": "Polymarket",
    "version": "1",
    "chainId": POLYGON_CHAIN_ID,
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}

# EIP-712 types for API key derivation
EIP712_DERIVE_KEY_TYPES = {
    "CreateApiKey": [
        {"name": "address", "type": "address"},
        {"name": "timestamp", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
    ],
}

# EIP-712 Order type definition matching the CLOB contract
EIP712_ORDER_TYPES = {
    "Order": [
        {"name": "salt", "type": "uint256"},
        {"name": "maker", "type": "address"},
        {"name": "signer", "type": "address"},
        {"name": "taker", "type": "address"},
        {"name": "tokenId", "type": "uint256"},
        {"name": "makerAmount", "type": "uint256"},
        {"name": "takerAmount", "type": "uint256"},
        {"name": "expiration", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "feeRateBps", "type": "uint256"},
        {"name": "side", "type": "uint8"},
        {"name": "signatureType", "type": "uint256"},
    ],
}

USDC_DECIMALS = 1_000_000  # 10^6


class ClobClient:
    """
    Client for Polymarket CLOB API.

    Handles order placement, cancellation, and orderbook queries for the
    Polymarket CLOB (Central Limit Order Book). Uses EIP-712 typed data
    signing for order payloads and HMAC-SHA256 (L2) for request auth.

    Parameters
    ----------
    api_key : str
        Polymarket API key for authentication
    private_key : str
        Private key for signing orders (wallet private key)
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
    api_secret : str, optional
        L2 API secret (HMAC key) for request signing
    api_passphrase : str, optional
        L2 API passphrase for authentication
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
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        simulate: bool = False,
    ):
        """
        Parameters
        ----------
        api_key : str
            Polymarket API key (from settings or derived via L1 auth)
        private_key : str
            Wallet private key for EIP-712 order signing
        rpc_url : str
            Polygon RPC URL
        base_url : str, optional
            CLOB API base URL (default: https://clob.polymarket.com)
        timeout : int, optional
            Request timeout in seconds (default: 10)
        retry_attempts : int, optional
            Retry attempts for failed requests (default: 3)
        retry_delay : float, optional
            Delay between retries in seconds (default: 1.0)
        api_secret : str, optional
            L2 API secret for HMAC-SHA256 request signing.
            Required for real (non-simulated) trading.
        api_passphrase : str, optional
            L2 API passphrase. Required for real trading.
        simulate : bool, optional
            Enable simulation mode (default: False)
        """
        self.api_key = api_key
        self._private_key = private_key
        self.rpc_url = rpc_url
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.base_url = base_url
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.simulate = simulate

        # httpx client (lazy init)
        self._client: Optional[httpx.Client] = None
        self._address: Optional[str] = None

        log.info("ClobClient initialized for %s (simulate=%s)", base_url, simulate)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def address(self) -> str:
        """Get wallet address derived from private key."""
        if self._address is None:
            try:
                from eth_account import Account
                account = Account.from_key(self._private_key)
                self._address = account.address
            except Exception:
                if self.simulate:
                    self._address = "0x" + "0" * 40
                else:
                    raise RuntimeError(
                        "Failed to derive address from private key. "
                        "Ensure a valid hex private key is provided. "
                        "Install eth-account if missing: pip install eth-account"
                    )
        return self._address
    
    @property
    def private_key(self) -> str:
        """Get the private key."""
        return self._private_key
    
    @private_key.setter
    def private_key(self, value: str) -> None:
        self._private_key = value
    
    def __repr__(self) -> str:
        return (
            f"ClobClient(base_url={self.base_url!r}, "
            f"address={self.address!r}, "
            f"simulate={self.simulate})"
        )

    # ── Session & Request Helpers ──────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """Get or create httpx client with proper headers."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    def _build_hmac_signature(
        self,
        method: str,
        request_path: str,
        timestamp: str,
        body: Optional[str] = None,
    ) -> str:
        """
        Build L2 HMAC-SHA256 signature for CLOB API request authentication.

        Uses the API secret as the HMAC key.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, DELETE)
        request_path : str
            API request path (e.g., /order)
        timestamp : str
            Current UNIX timestamp as string
        body : str, optional
            Request body as JSON string (included for POST requests)

        Returns
        -------
        str
            URL-safe base64-encoded HMAC-SHA256 digest
        """
        secret_bytes = base64.urlsafe_b64decode(self.api_secret)
        message = timestamp + method.upper() + request_path
        if body:
            message += str(body).replace("'", '"')
        h = hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256)
        return base64.urlsafe_b64encode(h.digest()).decode("utf-8")

    def _build_l2_headers(
        self,
        method: str,
        request_path: str,
        body: Optional[dict] = None,
    ) -> dict[str, str]:
        """
        Build L2 authentication headers for CLOB API requests using HMAC-SHA256.

        Requires API credentials (api_key, api_secret, api_passphrase).
        If credentials are missing and not in simulate mode, a RuntimeError is raised.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, DELETE)
        request_path : str
            API request path (e.g., /order)
        body : dict, optional
            Request body (serialized to JSON for HMAC signing)

        Returns
        -------
        dict[str, str]
            The 5 required L2 auth headers
        """
        if self.simulate:
            return {
                "POLY_ADDRESS": self.address,
                "POLY_SIGNATURE": "simulated-hmac-signature",
                "POLY_TIMESTAMP": str(int(time.time() * 1000)),
                "POLY_API_KEY": "simulated",
                "POLY_PASSPHRASE": "simulated",
            }

        if not self.api_secret or not self.api_passphrase:
            raise RuntimeError(
                "L2 API credentials required. "
                "Call derive_api_credentials() first or pass api_secret/api_passphrase."
            )

        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(body) if body else None
        signature = self._build_hmac_signature(method, request_path, timestamp, body_str)

        return {
            "POLY_ADDRESS": self.address,
            "POLY_SIGNATURE": signature,
            "POLY_TIMESTAMP": timestamp,
            "POLY_API_KEY": self.api_key,
            "POLY_PASSPHRASE": self.api_passphrase,
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """
        Make HTTP request to CLOB API with retry logic and auth headers.

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
        if self.simulate:
            return self._simulate_response(method, endpoint, data)

        client = self._get_client()
        url = f"{self.base_url}{endpoint}"
        headers = self._build_l2_headers(method, endpoint, data)

        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                if method == "GET":
                    response = client.get(url, params=params, headers=headers)
                elif method == "POST":
                    response = client.post(url, json=data, headers=headers)
                elif method == "DELETE":
                    response = client.delete(url, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Raise on HTTP error status
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                last_error = e

                if status_code == 429:
                    log.warning("Rate limit exceeded. Backing off...")
                    if attempt < self.retry_attempts - 1:
                        time.sleep(self.retry_delay * (2 ** attempt) * 2)
                        continue
                    raise RateLimitExceeded(
                        f"Rate limit exceeded after {self.retry_attempts} attempts"
                    )

                if status_code == 400:
                    body = e.response.text
                    log.error("Order rejected (400): reason=%s", str(e)[:200])
                    raise OrderRejected(f"Order rejected by CLOB: {body}")

                if status_code == 401:
                    raise NetworkError(f"Authentication failed: {e}")

                if status_code == 404:
                    log.warning("Resource not found: %s", endpoint)
                    if attempt < self.retry_attempts - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    raise NetworkError(f"Resource not found: {e}")

                if status_code >= 500:
                    log.warning("Server error %d on attempt %d", status_code, attempt + 1)
                    if attempt < self.retry_attempts - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    raise NetworkError(f"CLOB server error after {self.retry_attempts} attempts: {e}")

                raise NetworkError(f"HTTP {status_code}: {e}")

            except httpx.TimeoutException as e:
                last_error = e
                log.warning("Request timed out on attempt %d", attempt + 1)
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise OrderTimeout(f"Request timed out after {self.retry_attempts} attempts")

            except httpx.RequestError as e:
                last_error = e
                log.warning("Request failed on attempt %d: %s", attempt + 1, e)
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    continue
                raise NetworkError(f"Request failed after {self.retry_attempts} attempts: {e}")

        raise NetworkError(f"Request failed: {last_error}")

    # ── Simulated Responses ────────────────────────────────────────────────────

    def _simulate_response(self, method: str, endpoint: str, data: Optional[dict]) -> dict:
        """Simulate API response for testing without actual API access."""
        import uuid

        if method == "POST" and ("order" in endpoint or "place" in endpoint):
            return {
                "order_id": str(uuid.uuid4()),
                "status": "pending",
                "token_id": (data or {}).get("token_id", "unknown"),
                "side": (data or {}).get("side", "unknown"),
                "price": (data or {}).get("price", 0.0),
                "size": (data or {}).get("size", 0.0),
            }
        elif method == "DELETE" and ("order" in endpoint or "cancel" in endpoint):
            parts = endpoint.split("/")
            oid = parts[-2] if len(parts) >= 2 else parts[-1]
            return {
                "order_id": oid,
                "status": "cancelled",
            }
        elif method == "GET" and endpoint.startswith("/order/") and "orderbook" not in endpoint:
            parts = endpoint.split("/")
            oid = parts[-2] if len(parts) >= 2 else parts[-1]
            return {
                "order_id": oid,
                "status": "filled",
                "filled_size": 10.0,
                "avg_price": 0.55,
            }
        elif method == "GET" and "orderbook" in endpoint:
            return {
                "bids": [[0.54, 100.0], [0.53, 50.0]],
                "asks": [[0.56, 100.0], [0.57, 50.0]],
            }
        elif method == "GET" and ("balance" in endpoint or "allowance" in endpoint):
            return {
                "address": self.address,
                "usdc_balance": 1000.0,
                "allowance": 10000.0,
            }
        else:
            return {}

    # ── L1 Authentication (API Credential Derivation) ──────────────────────────

    def derive_api_credentials(self) -> dict:
        """
        Derive or create L2 API credentials using L1 wallet authentication.

        Calls ``POST /auth/derive-api-key`` with an EIP-712 signed message
        to generate or retrieve ``api_key``, ``secret``, and ``passphrase``.

        These credentials are cached on the instance and can be passed to
        subsequent ClobClient instances to skip the derivation step.

        Returns
        -------
        dict
            Credentials with keys: api_key, secret, passphrase

        Raises
        ------
        RuntimeError
            If L1 authentication fails (invalid key, network error)
        """
        if self.simulate:
            return {
                "api_key": "simulated-api-key",
                "secret": "simulated-secret",
                "passphrase": "simulated-passphrase",
            }

        from eth_account import Account
        from eth_account.messages import encode_typed_data

        timestamp = int(time.time() * 1000)
        nonce = 0

        l1_message = {
            "address": self.address,
            "timestamp": timestamp,
            "nonce": nonce,
        }

        signable = encode_typed_data(
            domain_data=EIP712_DERIVE_KEY_DOMAIN,
            message_types=EIP712_DERIVE_KEY_TYPES,
            message_data=l1_message,
        )
        signed = Account.from_key(self.private_key).sign_message(signable)
        l1_signature = "0x" + signed.signature.hex()

        l1_headers = {
            "POLY_ADDRESS": self.address,
            "POLY_SIGNATURE": l1_signature,
            "POLY_TIMESTAMP": str(timestamp),
            "POLY_NONCE": str(nonce),
        }

        log.info("Deriving L2 API credentials via L1 wallet authentication")
        client = self._get_client()
        url = f"{self.base_url}/auth/derive-api-key"
        try:
            response = client.post(url, headers=l1_headers)
            response.raise_for_status()
            creds = response.json()
            self.api_key = creds["api_key"]
            self.api_secret = creds["secret"]
            self.api_passphrase = creds["passphrase"]
            log.info("L2 API credentials derived successfully")
            return dict(creds)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Failed to derive API credentials: {e}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error deriving API credentials: {e}")

    # ── EIP-712 Order Signing ──────────────────────────────────────────────────

    def _build_eip712_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        nonce: int,
    ) -> dict:
        """
        Build the EIP-712 Order struct for CLOB signing.

        Parameters
        ----------
        token_id : str
            Conditional token ID for the outcome
        side : str
            "buy" or "sell"
        price : float
            Price per share in USDC (0-1 for binary markets)
        size : float
            Order size in number of shares
        nonce : int
            Unique nonce for the order

        Returns
        -------
        dict
            EIP-712 Order struct with raw (6-decimal) amounts
        """
        maker = self.address
        taker = "0x0000000000000000000000000000000000000000"

        # Convert to raw amounts (6 decimal places for USDC and tokens on Polygon)
        # For BUY: maker offers USDC, taker receives tokens
        # For SELL: maker offers tokens, taker receives USDC
        usdc_raw = int(size * price * USDC_DECIMALS)
        tokens_raw = int(size * USDC_DECIMALS)

        if side == "buy":
            maker_amount = usdc_raw
            taker_amount = tokens_raw
            side_int = 0
        else:
            maker_amount = tokens_raw
            taker_amount = usdc_raw
            side_int = 1

        # Generate random salt for uniqueness
        salt = secrets.randbits(256)

        order = {
            "salt": salt,
            "maker": maker,
            "signer": maker,
            "taker": taker,
            "tokenId": int(token_id) if token_id.isdigit() else int(hashlib.sha256(token_id.encode()).hexdigest(), 16) % (2**256),
            "makerAmount": maker_amount,
            "takerAmount": taker_amount,
            "expiration": 0,
            "nonce": nonce,
            "feeRateBps": 0,
            "side": side_int,
            "signatureType": 0,
        }
        return order

    def _sign_eip712_order(self, order: dict) -> str:
        """
        Sign an EIP-712 Order struct with the wallet's private key.

        Uses the standard Polymarket CLOB domain and Order type.

        Parameters
        ----------
        order : dict
            The EIP-712 Order struct to sign

        Returns
        -------
        str
            Hex-encoded EIP-712 signature (0x-prefixed)
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_typed_data

            signable = encode_typed_data(
                domain_data=EIP712_CLOB_DOMAIN,
                message_types=EIP712_ORDER_TYPES,
                message_data=order,
            )
            signed = Account.from_key(self.private_key).sign_message(signable)
            return "0x" + signed.signature.hex()

        except Exception:
            if self.simulate:
                return "0x" + "a" * 130
            raise RuntimeError(
                "Failed to sign EIP-712 order. "
                "Ensure a valid hex private key is provided. "
                "Install eth-account if missing: pip install eth-account"
            )

    # ── Public API Methods ─────────────────────────────────────────────────────

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

        Builds an EIP-712 signed order and sends it to the Polymarket CLOB API.

        Parameters
        ----------
        token_id : str
            Conditional token ID to trade
        side : str
            Order side ("buy" or "sell")
        price : float
            Order price per share
        size : float
            Order size in number of shares
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

        # In simulate mode, return a fake response immediately
        if self.simulate:
            import uuid
            return {
                "order_id": str(uuid.uuid4()),
                "status": "pending",
                "token_id": token_id,
                "side": side,
                "price": price,
                "size": size,
                "order_type": order_type,
            }

        # Build and sign the EIP-712 order
        order = self._build_eip712_order(token_id, side, price, size, nonce)
        signature = self._sign_eip712_order(order)

        # Prepare API request payload
        request_body = {
            "order": order,
            "signature": signature,
            "owner": self.address,
            "negRisk": False,
        }

        log.info(
            "Placing %s %s order: token=%s, price=%.4f, size=%.4f",
            order_type, side, token_id, price, size,
        )

        try:
            response = self._make_request("POST", "/order", data=request_body)

            order_id = response.get("id") or response.get("order_id", "")
            log.info("Order placed successfully: %s", order_id)

            # Normalize response for compatibility
            return {
                "order_id": order_id,
                "status": response.get("status", "pending"),
                "token_id": token_id,
                "side": side,
                "price": price,
                "size": size,
                "signature": signature,
            }

        except OrderRejected:
            raise
        except NetworkError as e:
            log.error("Failed to place order: %s", e)
            raise OrderRejected(f"Order rejected: {e}")
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
            response = self._make_request("DELETE", f"/order/{order_id}")
            return {
                "order_id": order_id,
                "status": response.get("status", "cancelled"),
            }
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
            response = self._make_request("GET", f"/order/{order_id}")
            return {
                "order_id": order_id,
                "status": response.get("status", "unknown"),
                "filled_size": float(response.get("filledAmount", response.get("filled_size", 0))),
                "avg_price": float(response.get("avgPrice", response.get("avg_price", 0))),
                "original_size": float(response.get("originalSize", response.get("size", 0))),
            }
        except Exception as e:
            log.error("Failed to get order status %s: %s", order_id, e)
            raise NetworkError(f"Failed to get order status: {e}")

    def get_orderbook(self, token_id: str) -> dict:
        """
        Get order book for a token.

        Parameters
        ----------
        token_id : str
            Token ID to query

        Returns
        -------
        dict
            Order book with bids and asks arrays of [price, size]

        Raises
        ------
        NetworkError
            If request fails
        """
        log.debug("Getting orderbook for token: %s", token_id)

        try:
            params = {"token_id": token_id}
            response = self._make_request("GET", "/orderbook", params=params)

            # Normalize bids and asks
            bids = []
            for bid in response.get("bids", []):
                if isinstance(bid, dict):
                    bids.append([float(bid.get("price", 0)), float(bid.get("size", 0))])
                else:
                    bids.append(bid)

            asks = []
            for ask in response.get("asks", []):
                if isinstance(ask, dict):
                    asks.append([float(ask.get("price", 0)), float(ask.get("size", 0))])
                else:
                    asks.append(ask)

            return {"bids": bids, "asks": asks}

        except Exception as e:
            log.error("Failed to get orderbook for token %s: %s", token_id, e)
            raise NetworkError(f"Failed to get orderbook: {e}")

    def get_balance(self) -> dict:
        """
        Get account balance and CLOB allowance.

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
            response = self._make_request("GET", "/balance/allowance")
            return {
                "address": self.address,
                "usdc_balance": float(response.get("usdc", response.get("balance", response.get("usdc_balance", 0)))),
                "allowance": float(response.get("allowance", 0)),
            }
        except Exception as e:
            log.error("Failed to get balance: %s", e)
            raise NetworkError(f"Failed to get balance: {e}")

    def close(self) -> None:
        """Close HTTP session."""
        if self._client is not None:
            self._client.close()
            self._client = None
        log.info("ClobClient closed")
