"""
AI client tests — run with: pytest tests/unit/ai/test_ai_client.py
"""

import json
import pytest
from unittest.mock import Mock, patch

from polyalpha.ai.client import OpenRouterClient
from polyalpha.ai.errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIModelNotFoundError,
    AIQuotaExceededError,
    AIResponseError,
    AITimeoutError,
)
from polyalpha.ai.models import AIResponse, MarketAnalysis, TradingSignal


@pytest.mark.unit
class TestOpenRouterClient:
    """Test OpenRouterClient initialization and basic functionality."""

    def test_initialization(self):
        """Test client initialization with default parameters."""
        client = OpenRouterClient(api_key="test-key")
        
        assert client.api_key == "test-key"
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client.enable_cost_tracking is True
        assert client._total_cost == 0.0
        assert client._total_tokens == 0

    def test_initialization_custom_params(self):
        """Test client initialization with custom parameters."""
        client = OpenRouterClient(
            api_key="test-key",
            model="openai/gpt-4",
            timeout=60,
            max_retries=5,
            enable_cost_tracking=False,
        )
        
        assert client.timeout == 60
        assert client.max_retries == 5
        assert client.enable_cost_tracking is False

    def test_initialization_headers(self):
        """Test that HTTP client is initialized with correct headers."""
        client = OpenRouterClient(api_key="test-key")
        
        assert "Authorization" in client._client.headers
        assert "Bearer test-key" in client._client.headers["Authorization"]
        assert "Content-Type" in client._client.headers
        assert "HTTP-Referer" in client._client.headers
        assert "X-OpenRouter-Title" in client._client.headers

    def test_close(self):
        """Test closing the client."""
        client = OpenRouterClient(api_key="test-key")
        client.close()
        # Should not raise any exception

    def test_context_manager(self):
        """Test using client as context manager."""
        with OpenRouterClient(api_key="test-key") as client:
            assert client.api_key == "test-key"
        # Client should be closed after exiting context


@pytest.mark.unit
class TestChatMethod:
    """Test chat method functionality."""

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_basic(self, mock_client_class):
        """Test basic chat request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Test response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0001
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        response = client.chat("Hello")
        
        assert isinstance(response, AIResponse)
        assert response.content == "Test response"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 5
        assert response.total_tokens == 15
        assert response.cost == 0.0001

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_with_system_prompt(self, mock_client_class):
        """Test chat with system prompt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "cost": 0.0002
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        response = client.chat("Hello", system_prompt="You are a helpful assistant")
        
        # Verify system prompt was included in the request
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]['json']
        messages = payload['messages']
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[0]['content'] == 'You are a helpful assistant'

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_with_temperature(self, mock_client_class):
        """Test chat with custom temperature."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        response = client.chat("Hello", temperature=0.5)
        
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]['json']
        assert payload['temperature'] == 0.5

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_with_max_tokens(self, mock_client_class):
        """Test chat with max tokens limit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        response = client.chat("Hello", max_tokens=100)
        
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]['json']
        assert payload['max_tokens'] == 100

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_with_response_format(self, mock_client_class):
        """Test chat with response format specification."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": '{"key": "value"}'
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        response = client.chat("Hello", response_format={"type": "json_object"})
        
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]['json']
        assert payload['response_format'] == {"type": "json_object"}

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_cost_tracking(self, mock_client_class):
        """Test that cost tracking works correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0001
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key", enable_cost_tracking=True)
        client.chat("Hello")
        client.chat("World")
        
        assert client.total_cost == 0.0002
        assert client.total_tokens == 30

    @patch('polyalpha.ai.client.httpx.Client')
    def test_chat_cost_tracking_disabled(self, mock_client_class):
        """Test that cost tracking can be disabled."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0001
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key", enable_cost_tracking=False)
        client.chat("Hello")
        
        assert client.total_cost == 0.0
        assert client.total_tokens == 0


@pytest.mark.unit
class TestAnalyzeMarket:
    """Test market analysis method."""

    @patch('polyalpha.ai.client.httpx.Client')
    def test_analyze_market_basic(self, mock_client_class):
        """Test basic market analysis."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": '{"sentiment": "bullish", "confidence": 0.8, "reasoning": "test reasoning"}'
                }
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
                "cost": 0.0005
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {
            "question": "Will BTC rise?",
            "current_price": 0.55,
            "volume": 10000,
        }
        
        analysis = client.analyze_market(market_data)
        
        assert isinstance(analysis, MarketAnalysis)
        assert analysis.sentiment == "bullish"
        assert analysis.confidence == 0.8

    @patch('polyalpha.ai.client.httpx.Client')
    def test_analyze_market_invalid_json(self, mock_client_class):
        """Test market analysis with invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Not valid JSON"
                }
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {"question": "Will BTC rise?"}
        
        with pytest.raises(AIResponseError, match="Invalid JSON"):
            client.analyze_market(market_data)

    @patch('polyalpha.ai.client.httpx.Client')
    def test_analyze_market_with_prices(self, mock_client_class):
        """Test market analysis includes current prices."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": '{"sentiment": "neutral", "confidence": 0.5, "reasoning": "test reasoning"}'
                }
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {"question": "Will BTC rise?"}
        current_prices = {"up": 0.55, "down": 0.45}
        
        analysis = client.analyze_market(market_data)
        
        assert isinstance(analysis, MarketAnalysis)


@pytest.mark.unit
class TestGenerateTradingSignal:
    """Test trading signal generation method."""

    @patch('polyalpha.ai.client.httpx.Client')
    def test_generate_trading_signal_basic(self, mock_client_class):
        """Test basic trading signal generation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": '{"action": "BUY", "confidence": 0.75, "side": "UP", "reasoning": "test reasoning"}'
                }
            }],
            "usage": {
                "prompt_tokens": 60,
                "completion_tokens": 25,
                "total_tokens": 85,
                "cost": 0.0006
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {"question": "Will BTC rise?"}
        
        signal = client.generate_trading_signal(market_data)
        
        assert isinstance(signal, TradingSignal)
        assert signal.action == "BUY"
        assert signal.confidence == 0.75
        assert signal.side == "UP"

    @patch('polyalpha.ai.client.httpx.Client')
    def test_generate_trading_signal_with_prices(self, mock_client_class):
        """Test trading signal with current prices."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": '{"action": "HOLD", "confidence": 0.5, "reasoning": "test reasoning"}'
                }
            }],
            "usage": {
                "prompt_tokens": 60,
                "completion_tokens": 25,
                "total_tokens": 85,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {"question": "Will BTC rise?"}
        current_prices = {"up": 0.55, "down": 0.45}
        
        signal = client.generate_trading_signal(market_data, current_prices)
        
        assert isinstance(signal, TradingSignal)
        assert signal.action == "HOLD"

    @patch('polyalpha.ai.client.httpx.Client')
    def test_generate_trading_signal_invalid_json(self, mock_client_class):
        """Test trading signal with invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "openai/gpt-4o-mini",
            "choices": [{
                "message": {
                    "content": "Not valid JSON"
                }
            }],
            "usage": {
                "prompt_tokens": 60,
                "completion_tokens": 25,
                "total_tokens": 85,
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        market_data = {"question": "Will BTC rise?"}
        
        with pytest.raises(AIResponseError, match="Invalid JSON"):
            client.generate_trading_signal(market_data)


@pytest.mark.unit
class TestFormatMarketData:
    """Test market data formatting."""

    def test_format_market_data_basic(self):
        """Test basic market data formatting."""
        client = OpenRouterClient(api_key="test-key")
        market_data = {
            "question": "Will BTC rise?",
            "current_price": 0.55,
            "volume": 10000,
        }
        
        formatted = client._format_market_data(market_data)
        
        assert "Market Analysis Request:" in formatted
        assert "question: Will BTC rise?" in formatted
        assert "current_price: 0.55" in formatted
        assert "volume: 10000" in formatted

    def test_format_market_data_with_none(self):
        """Test formatting with None values."""
        client = OpenRouterClient(api_key="test-key")
        market_data = {
            "question": "Will BTC rise?",
            "current_price": None,
            "volume": 10000,
        }
        
        formatted = client._format_market_data(market_data)
        
        assert "question: Will BTC rise?" in formatted
        assert "volume: 10000" in formatted
        # None values should be skipped
        assert "current_price:" not in formatted


@pytest.mark.unit
class TestMakeRequestErrors:
    """Test error handling in _make_request."""

    @patch('polyalpha.ai.client.httpx.Client')
    def test_authentication_error_401(self, mock_client_class):
        """Test 401 authentication error."""
        import httpx
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("401", request=Mock(), response=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        
        with pytest.raises(AIAuthenticationError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_quota_exceeded_error_429(self, mock_client_class):
        """Test 429 quota exceeded error."""
        import httpx
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=Mock(), response=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        
        with pytest.raises(AIQuotaExceededError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_model_not_found_error_404(self, mock_client_class):
        """Test 404 model not found error."""
        import httpx
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("404", request=Mock(), response=mock_response)
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        
        with pytest.raises(AIModelNotFoundError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_timeout_error(self, mock_client_class):
        """Test timeout error handling."""
        import httpx
        mock_client_instance = Mock()
        mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key", max_retries=1)
        
        with pytest.raises(AITimeoutError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_connection_error(self, mock_client_class):
        """Test connection error handling."""
        import httpx
        mock_client_instance = Mock()
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection failed")
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key", max_retries=1)
        
        with pytest.raises(AIConnectionError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_api_error_in_response(self, mock_client_class):
        """Test API error returned in response body."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": {
                "type": "authentication_error",
                "message": "Invalid API key"
            }
        }
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key")
        
        with pytest.raises(AIAuthenticationError):
            client._make_request({})

    @patch('polyalpha.ai.client.httpx.Client')
    def test_retry_logic(self, mock_client_class):
        """Test that retry logic works correctly."""
        import httpx
        mock_client_instance = Mock()
        mock_client_instance.post.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.TimeoutException("Timeout"),
            Mock(status_code=200, json=lambda: {
                "model": "openai/gpt-4o-mini",
                "choices": [{"message": {"content": "Success"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            })
        ]
        mock_client_instance.post.return_value.raise_for_status = Mock()
        mock_client_class.return_value = mock_client_instance
        
        client = OpenRouterClient(api_key="test-key", max_retries=3)
        
        result = client._make_request({})
        
        assert result["choices"][0]["message"]["content"] == "Success"
        assert mock_client_instance.post.call_count == 3


@pytest.mark.unit
class TestProperties:
    """Test client properties."""

    def test_total_cost_property(self):
        """Test total_cost property."""
        client = OpenRouterClient(api_key="test-key")
        client._total_cost = 0.005
        
        assert client.total_cost == 0.005

    def test_total_tokens_property(self):
        """Test total_tokens property."""
        client = OpenRouterClient(api_key="test-key")
        client._total_tokens = 1000
        
        assert client.total_tokens == 1000
