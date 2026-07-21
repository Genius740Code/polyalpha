"""
Tests for AlchemyClient — run with: pytest tests/unit/trading/test_alchemy_client.py
"""

import pytest
import requests
from unittest.mock import Mock, patch, call
from polyalpha.trading.alchemy_client import AlchemyClient


@pytest.fixture
def alchemy_client():
    return AlchemyClient(rpc_url="https://polygon-rpc.example.com")


@pytest.mark.unit
class TestAlchemyClientInit:
    def test_initialization(self):
        client = AlchemyClient(rpc_url="https://polygon-rpc.example.com")
        assert client.rpc_url == "https://polygon-rpc.example.com"
        assert client._session is not None


@pytest.mark.unit
class TestMakeRpcCall:
    def test_make_rpc_call_success(self, alchemy_client):
        mock_response = Mock()
        mock_response.json.return_value = {"result": {"key": "value"}}
        mock_response.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post", return_value=mock_response) as mock_post:
            result = alchemy_client._make_rpc_call("test_method", ["param1"])

            mock_post.assert_called_once_with(
                "https://polygon-rpc.example.com",
                json={"jsonrpc": "2.0", "id": 1, "method": "test_method", "params": ["param1"]},
            )
            assert result == {"result": {"key": "value"}}

    def test_make_rpc_call_http_error(self, alchemy_client):
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad request")

        with patch.object(alchemy_client._session, "post", return_value=mock_response):
            with pytest.raises(requests.exceptions.HTTPError):
                alchemy_client._make_rpc_call("test_method", [])


@pytest.mark.unit
class TestGetAssetTransfers:
    def test_get_asset_transfers_success(self, alchemy_client):
        mock_response_in = Mock()
        mock_response_in.json.return_value = {
            "result": {
                "transfers": [
                    {"hash": "0x1", "to": "0xabc", "from": "0xdef", "erc1155Metadata": []}
                ]
            }
        }
        mock_response_in.raise_for_status.return_value = None

        mock_response_out = Mock()
        mock_response_out.json.return_value = {
            "result": {
                "transfers": [
                    {"hash": "0x2", "to": "0xdef", "from": "0xabc", "erc1155Metadata": []}
                ]
            }
        }
        mock_response_out.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post") as mock_post:
            mock_post.side_effect = [mock_response_in, mock_response_out]

            transfers = alchemy_client.get_asset_transfers("0xabc")

            assert len(transfers) == 2
            assert mock_post.call_count == 2

    def test_get_asset_transfers_empty(self, alchemy_client):
        mock_response = Mock()
        mock_response.json.return_value = {"result": {"transfers": []}}
        mock_response.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post", return_value=mock_response):
            transfers = alchemy_client.get_asset_transfers("0xabc")
            assert transfers == []

    def test_get_asset_transfers_error(self, alchemy_client):
        with patch.object(alchemy_client._session, "post", side_effect=Exception("Network error")):
            transfers = alchemy_client.get_asset_transfers("0xabc")
            assert transfers == []


@pytest.mark.unit
class TestGetTokenBalances:
    def test_get_token_balances_received(self, alchemy_client):
        mock_response_in = Mock()
        mock_response_in.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xabc",
                        "from": "0xdef",
                        "erc1155Metadata": [{"tokenId": "0x1", "value": "0xa"}],
                    }
                ]
            }
        }
        mock_response_in.raise_for_status.return_value = None

        mock_response_out = Mock()
        mock_response_out.json.return_value = {"result": {"transfers": []}}
        mock_response_out.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post") as mock_post:
            mock_post.side_effect = [mock_response_in, mock_response_out]

            balances = alchemy_client.get_token_balances("0xabc")

            assert "0x1" in balances
            assert balances["0x1"] == 10  # 0xa = 10

    def test_get_token_balances_sent(self, alchemy_client):
        mock_response_in = Mock()
        mock_response_in.json.return_value = {"result": {"transfers": []}}
        mock_response_in.raise_for_status.return_value = None

        mock_response_out = Mock()
        mock_response_out.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xdef",
                        "from": "0xabc",
                        "erc1155Metadata": [{"tokenId": "0x1", "value": "0x5"}],
                    }
                ]
            }
        }
        mock_response_out.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post") as mock_post:
            mock_post.side_effect = [mock_response_in, mock_response_out]

            balances = alchemy_client.get_token_balances("0xabc")

            assert balances == {}

    def test_get_token_balances_net(self, alchemy_client):
        mock_response_in = Mock()
        mock_response_in.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xabc",
                        "from": "0xdef",
                        "erc1155Metadata": [{"tokenId": "0x1", "value": "0xa"}],
                    }
                ]
            }
        }
        mock_response_in.raise_for_status.return_value = None

        mock_response_out = Mock()
        mock_response_out.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xghi",
                        "from": "0xabc",
                        "erc1155Metadata": [{"tokenId": "0x1", "value": "0x3"}],
                    }
                ]
            }
        }
        mock_response_out.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post") as mock_post:
            mock_post.side_effect = [mock_response_in, mock_response_out]

            balances = alchemy_client.get_token_balances("0xabc")

            assert balances["0x1"] == 7  # 10 - 3

    def test_get_token_balances_no_metadata(self, alchemy_client):
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xabc",
                        "from": "0xdef",
                        "erc1155Metadata": None,
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post", return_value=mock_response):
            balances = alchemy_client.get_token_balances("0xabc")
            assert balances == {}

    def test_get_token_balances_zero_filtered(self, alchemy_client):
        mock_response_in = Mock()
        mock_response_in.json.return_value = {
            "result": {
                "transfers": [
                    {
                        "to": "0xabc",
                        "from": "0xdef",
                        "erc1155Metadata": [{"tokenId": "0x1", "value": "0x0"}],
                    }
                ]
            }
        }
        mock_response_in.raise_for_status.return_value = None

        mock_response_out = Mock()
        mock_response_out.json.return_value = {"result": {"transfers": []}}
        mock_response_out.raise_for_status.return_value = None

        with patch.object(alchemy_client._session, "post") as mock_post:
            mock_post.side_effect = [mock_response_in, mock_response_out]

            balances = alchemy_client.get_token_balances("0xabc")
            assert balances == {}


@pytest.mark.unit
class TestFetchPolymarketMetadata:
    def test_fetch_metadata_success(self, alchemy_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"question": "Will BTC go up?", "outcomes": ["Yes", "No"]}

        with patch.object(alchemy_client._session, "get", return_value=mock_response) as mock_get:
            metadata = alchemy_client.fetch_polymarket_metadata(["0x1", "0x2"])

            assert len(metadata) == 2
            assert metadata["0x1"]["question"] == "Will BTC go up?"
            assert mock_get.call_count == 2

    def test_fetch_metadata_not_found(self, alchemy_client):
        mock_response = Mock()
        mock_response.status_code = 404

        with patch.object(alchemy_client._session, "get", return_value=mock_response):
            metadata = alchemy_client.fetch_polymarket_metadata(["0x1"])
            assert metadata == {}

    def test_fetch_metadata_hex_to_dec(self, alchemy_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"question": "Test"}

        with patch.object(alchemy_client._session, "get", return_value=mock_response) as mock_get:
            alchemy_client.fetch_polymarket_metadata(["0xa"])

            expected_dec = str(int("0xa", 16))
            call_url = mock_get.call_args[0][0]
            assert expected_dec in call_url

    def test_fetch_metadata_already_decimal(self, alchemy_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"question": "Test"}

        with patch.object(alchemy_client._session, "get", return_value=mock_response) as mock_get:
            alchemy_client.fetch_polymarket_metadata(["42"])

            call_url = mock_get.call_args[0][0]
            assert call_url.endswith("/42")

    def test_fetch_metadata_exception(self, alchemy_client):
        with patch.object(alchemy_client._session, "get", side_effect=Exception("API error")):
            metadata = alchemy_client.fetch_polymarket_metadata(["0x1"])
            assert metadata == {}
