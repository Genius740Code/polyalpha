import logging
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

log = logging.getLogger(__name__)

class AlchemyClient:
    """
    Client for interacting with Alchemy RPC to fetch real Polymarket positions
    and transaction history (when bought and sold).
    """

    # Conditional Tokens Framework (CTF) contract on Polygon
    CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097CAe4754ad2F2E"

    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self._session = requests.Session()

    def _make_rpc_call(self, method: str, params: list) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        response = self._session.post(self.rpc_url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_asset_transfers(self, address: str) -> List[Dict[str, Any]]:
        """
        Fetch ERC1155 transfers for the user's address using Alchemy's enhanced API.
        This provides history of when tokens were bought and sold.
        """
        try:
            params = [{
                "fromBlock": "0x0",
                "toBlock": "latest",
                "toAddress": address,
                "category": ["erc1155"],
                "contractAddresses": [self.CTF_ADDRESS],
                "withMetadata": True
            }]
            data = self._make_rpc_call("alchemy_getAssetTransfers", params)
            transfers_in = data.get("result", {}).get("transfers", [])

            params[0].pop("toAddress")
            params[0]["fromAddress"] = address
            data = self._make_rpc_call("alchemy_getAssetTransfers", params)
            transfers_out = data.get("result", {}).get("transfers", [])

            return transfers_in + transfers_out
        except Exception as e:
            log.error(f"Failed to fetch asset transfers from Alchemy: {e}")
            return []

    def get_token_balances(self, address: str) -> Dict[str, int]:
        """
        Fetch current ERC1155 token balances for the user's address.
        """
        transfers = self.get_asset_transfers(address)
        balances = {}
        for t in transfers:
            erc1155_metadata = t.get("erc1155Metadata")
            if not erc1155_metadata:
                continue

            for token in erc1155_metadata:
                token_id = token.get("tokenId")
                val = int(token.get("value", "0"), 16) if isinstance(token.get("value"), str) else token.get("value", 0)

                if t.get("to", "").lower() == address.lower():
                    balances[token_id] = balances.get(token_id, 0) + val
                elif t.get("from", "").lower() == address.lower():
                    balances[token_id] = balances.get(token_id, 0) - val

        # Filter out zero balances
        return {k: v for k, v in balances.items() if v > 0}

    def fetch_polymarket_metadata(self, token_ids: List[str]) -> Dict[str, Any]:
        """
        Fetch market metadata from Polymarket Gamma API for given token IDs.
        """
        metadata = {}
        for token_id in token_ids:
            try:
                # Convert token_id from hex string to decimal string if needed
                if token_id.startswith("0x"):
                    token_id_dec = str(int(token_id, 16))
                else:
                    token_id_dec = token_id
                    
                res = self._session.get(f"https://gamma-api.polymarket.com/tokens/{token_id_dec}")
                if res.status_code == 200:
                    metadata[token_id] = res.json()
            except Exception as e:
                log.warning(f"Failed to fetch metadata for token {token_id}: {e}")
        return metadata
