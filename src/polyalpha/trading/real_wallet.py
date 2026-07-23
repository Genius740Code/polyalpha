"""Wallet management for real trading on Polygon.

Handles USDC balance, CLOB allowances, and transaction signing.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional

from ..core import NetworkError, GasEstimationError, TransactionRebroadcastError

log = logging.getLogger(__name__)


class WalletManager:
    """Manages wallet operations for real trading."""

    def __init__(self, private_key: str, rpc_url: str, log_balance_updates: bool = False):
        self._private_key = private_key
        self._rpc_url = rpc_url
        self._address: Optional[str] = None
        self._balance: float = 0.0
        self._allowance: float = 0.0
        self._log_balance_updates = log_balance_updates

        self._web3 = None
        self._usdc_contract = None
        self._clob_contract = None

        self._nonce_lock = Lock()

        log.info("WalletManager initialized")

    @property
    def address(self) -> Optional[str]:
        """Get the wallet address."""
        if not self._address:
            from eth_account import Account
            account = Account.from_key(self._private_key)
            self._address = account.address
        return self._address

    def _init_web3(self) -> None:
        """Initialize Web3.py and contracts (mandatory for production)."""
        from web3 import Web3
        from eth_account import Account

        self._web3 = Web3(Web3.HTTPProvider(self._rpc_url))
        account = Account.from_key(self._private_key)
        self._address = account.address

        from ..trading.alchemy_client import AlchemyClient
        self._ctf_address = AlchemyClient.CTF_ADDRESS

        usdc_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
        ]

        ctf_abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_id", "type": "uint256"},
                ],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "id", "type": "uint256"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "data", "type": "bytes"},
                ],
                "name": "safeTransferFrom",
                "outputs": [],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "conditionId", "type": "bytes32"},
                    {"name": "parentCollectionId", "type": "bytes32"},
                    {"name": "indexSets", "type": "uint256[]"},
                ],
                "name": "redeem",
                "outputs": [{"name": "payout", "type": "uint256"}],
                "type": "function",
            },
        ]
        self._ctf_contract = self._web3.eth.contract(
            address=self._ctf_address,
            abi=ctf_abi,
        )
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        self._usdc_contract = self._web3.eth.contract(
            address=usdc_address,
            abi=usdc_abi
        )

        self._nonce: int = self._web3.eth.get_transaction_count(self._address)
        self._pending_transactions: dict[str, dict] = {}

        self._total_gas_spent: float = 0.0
        self._gas_cost_usd: float = 0.0

        log.info("Web3.py initialized for address %s", self._address)

    def _build_transaction_params(self, gas_estimate: int, to_address: str) -> dict:
        latest_block = self._web3.eth.get_block('latest')
        base_fee = latest_block.get('baseFeePerGas', 0)

        max_priority_fee_per_gas = self._web3.to_wei(2, 'gwei')
        max_fee_per_gas = base_fee + self._web3.to_wei(3, 'gwei')

        nonce = self._get_next_nonce()

        return {
            'from': self._address,
            'gas': gas_estimate,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee_per_gas,
            'nonce': nonce,
            'type': 2,
        }

    def _get_next_nonce(self) -> int:
        with self._nonce_lock:
            network_nonce = self._web3.eth.get_transaction_count(self._address)
            if self._nonce < network_nonce:
                self._nonce = network_nonce
            current_nonce = self._nonce
            self._nonce += 1
            return current_nonce

    def _track_pending_transaction(self, tx_hash: str, nonce: int) -> None:
        self._pending_transactions[tx_hash] = {
            'nonce': nonce,
            'timestamp': time.time(),
            'retry_count': 0,
        }

    def _rebroadcast_transaction(self, tx_hash: str) -> dict:
        if tx_hash not in self._pending_transactions:
            log.error("Cannot re-broadcast %s: not tracked as pending", tx_hash)
            return {'status': 0, 'error': 'Transaction not tracked'}

        tx_info = self._pending_transactions[tx_hash]
        retry_count = tx_info['retry_count']

        if retry_count >= 3:
            log.error("Transaction %s exceeded max retry attempts", tx_hash)
            return {'status': 0, 'error': 'Max retries exceeded'}

        try:
            tx = self._web3.eth.get_transaction(tx_hash)
            from eth_account import Account

            new_max_fee = int(tx['maxFeePerGas'] * 1.2)
            new_priority_fee = int(tx['maxPriorityFeePerGas'] * 1.2)

            tx_dict = {
                'to': tx['to'],
                'from': tx['from'],
                'value': tx['value'],
                'data': tx['input'],
                'gas': tx['gas'],
                'maxFeePerGas': new_max_fee,
                'maxPriorityFeePerGas': new_priority_fee,
                'nonce': tx['nonce'],
                'type': 2,
                'chainId': tx['chainId'],
            }

            signed_tx = Account.sign_transaction(tx_dict, self._private_key)
            new_tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            new_tx_hash_hex = new_tx_hash.hex()

            tx_info['retry_count'] += 1
            del self._pending_transactions[tx_hash]
            self._track_pending_transaction(new_tx_hash_hex, tx['nonce'])

            log.info("Re-broadcast transaction %s as %s (attempt %d)", tx_hash, new_tx_hash_hex, retry_count + 1)

            return self.wait_for_transaction(new_tx_hash_hex, timeout=60)

        except Exception as e:
            log.error("Failed to re-broadcast transaction %s: %s", tx_hash, e)
            raise TransactionRebroadcastError(f"Failed to re-broadcast transaction: {e}")

    def get_gas_stats(self) -> dict:
        return {
            'total_gas_spent': self._total_gas_spent,
            'gas_cost_usd': self._gas_cost_usd,
            'pending_transactions': len(self._pending_transactions),
            'current_nonce': self._nonce,
        }

    def get_address(self) -> str:
        """Get wallet address."""
        if self._address is None:
            self._init_web3()
        return self._address

    def get_balance(self) -> float:
        """Get current USDC balance."""
        if self._web3 is None:
            self._init_web3()

        try:
            balance_raw = self._usdc_contract.functions.balanceOf(
                self._address
            ).call()
            self._balance = float(balance_raw) / 1e6
        except Exception as e:
            log.error("Failed to fetch balance: %s", e)
            raise NetworkError(f"Failed to fetch balance from blockchain: {e}")

        return self._balance

    def get_allowance(self, spender_address: str) -> float:
        """Get allowance for a specific spender."""
        if self._web3 is None:
            self._init_web3()

        try:
            allowance_raw = self._usdc_contract.functions.allowance(
                self._address,
                spender_address
            ).call()
            self._allowance = float(allowance_raw) / 1e6
        except Exception as e:
            log.error("Failed to fetch allowance: %s", e)
            raise NetworkError(f"Failed to fetch allowance from blockchain: {e}")

        return self._allowance

    def approve_spender(self, spender_address: str, amount: float) -> str:
        """Approve a spender to spend USDC."""
        if self._web3 is None:
            self._init_web3()

        try:
            amount_raw = int(amount * 1e6)

            try:
                gas_estimate = self._usdc_contract.functions.approve(
                    spender_address,
                    amount_raw
                ).estimate_gas({'from': self._address})
            except Exception as e:
                log.error("Gas estimation failed for approval: %s", e)
                raise GasEstimationError(f"Failed to estimate gas for approval: {e}")

            tx_params = self._build_transaction_params(
                gas_estimate=gas_estimate,
                to_address=spender_address
            )

            tx = self._usdc_contract.functions.approve(
                spender_address,
                amount_raw
            ).build_transaction(tx_params)

            from eth_account import Account
            signed_tx = Account.sign_transaction(tx, self._private_key)
            tx_hash = self._web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            self._track_pending_transaction(tx_hash_hex, tx_params['nonce'])

            log.info("Approval transaction sent: %s", tx_hash_hex)
            return tx_hash_hex
        except GasEstimationError:
            raise
        except Exception as e:
            log.error("Failed to approve spender: %s", e)
            raise NetworkError(f"Failed to approve spender: {e}")

    def refresh_balance(self) -> None:
        """Refresh balance from blockchain."""
        self._balance = self.get_balance()
        if self._log_balance_updates:
            log.debug("Balance refreshed: $%.2f", self._balance)

    def wait_for_transaction(self, tx_hash: str, timeout: int = 120, poll_interval: float = 1.0) -> dict:
        """Wait for transaction confirmation with polling."""
        if self._web3 is None:
            self._init_web3()

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                receipt = self._web3.eth.get_transaction_receipt(tx_hash)

                if receipt is not None:
                    gas_used = receipt['gasUsed']
                    block_number = receipt['blockNumber']

                    gas_cost_wei = gas_used * receipt.get('effectiveGasPrice', 0)
                    gas_cost_matic = float(self._web3.from_wei(gas_cost_wei, 'ether'))
                    gas_cost_usd = gas_cost_matic * 0.5

                    self._total_gas_spent += float(gas_used)
                    self._gas_cost_usd += gas_cost_usd

                    if tx_hash in self._pending_transactions:
                        del self._pending_transactions[tx_hash]

                    log.info(
                        "Transaction %s confirmed in block %d. Gas used: %d, Cost: $%.4f",
                        tx_hash, block_number, gas_used, gas_cost_usd
                    )

                    return {
                        'status': receipt['status'],
                        'gas_used': int(gas_used),
                        'block_number': block_number,
                        'gas_cost_usd': gas_cost_usd,
                        'effective_gas_price': receipt.get('effectiveGasPrice', 0),
                    }

            except Exception:
                pass

            time.sleep(poll_interval)

        log.warning("Transaction %s timed out after %d seconds, attempting re-broadcast", tx_hash, timeout)
        return self._rebroadcast_transaction(tx_hash)
