"""
OpenRouter API client for AI-powered market analysis and trading signals.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx

from .errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIModelNotFoundError,
    AIQuotaExceededError,
    AIResponseError,
    AITimeoutError,
)
from .models import (
    AIResponse,
    ChatMessage,
    MarketAnalysis,
    ModelConfig,
    TradingSignal,
)


class OpenRouterClient:
    """
    Client for interacting with OpenRouter API.
    
    Parameters
    ----------
    api_key : OpenRouter API key
    model : Default model to use (default: "openai/gpt-4o-mini")
    timeout : Request timeout in seconds (default: 30)
    max_retries : Maximum number of retries (default: 3)
    enable_cost_tracking : Track usage and costs (default: True)
    
    Example
    -------
    >>> client = OpenRouterClient(api_key="your-key")
    >>> response = client.chat("Analyze BTC market")
    >>> print(response.content)
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(
        self,
        api_key: str,
        model: str = ModelConfig.DEFAULT_MODEL,
        timeout: int = 30,
        max_retries: int = 3,
        enable_cost_tracking: bool = True,
    ):
        self.api_key = api_key
        self.model = ModelConfig.resolve_model(model)
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_cost_tracking = enable_cost_tracking
        
        self._log = logging.getLogger("polyalpha.ai")
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://polyalpha.dev",
                "X-OpenRouter-Title": "PolyAlpha SDK",
            },
        )
        
        # Track total usage
        self._total_cost = 0.0
        self._total_tokens = 0
    
    def close(self) -> None:
        """Clean up HTTP client."""
        self._client.close()
    
    def chat(
        self,
        message: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> AIResponse:
        """
        Send a chat completion request.
        
        Parameters
        ----------
        message : User message to send
        model : Override default model
        system_prompt : System prompt for context
        temperature : Sampling temperature (0-2)
        max_tokens : Maximum tokens to generate
        response_format : Response format specification (e.g., {"type": "json_object"})
        
        Returns
        -------
        AIResponse with content and usage info
        """
        messages = []
        
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        messages.append(ChatMessage(role="user", content=message))
        
        payload = {
            "model": model or self.model,
            "messages": [msg.model_dump() for msg in messages],
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if response_format:
            payload["response_format"] = response_format
        
        response_data = self._make_request(payload)
        
        # Extract response
        choice = response_data["choices"][0]
        content = choice["message"]["content"]
        
        # Extract usage
        usage = response_data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cost = usage.get("cost")
        
        # Update tracking
        if self.enable_cost_tracking and cost:
            self._total_cost += cost
            self._total_tokens += total_tokens
        
        return AIResponse(
            content=content,
            model=response_data["model"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
        )
    
    def analyze_market(
        self,
        market_data: dict[str, Any],
        model: str | None = None,
    ) -> MarketAnalysis:
        """
        Analyze market data using AI.
        
        Parameters
        ----------
        market_data : Dictionary containing market information
            Should include: question, current prices, volume, liquidity, etc.
        model : Override default model
        
        Returns
        -------
        MarketAnalysis with structured analysis
        """
        system_prompt = ModelConfig.get_system_prompt("market_analysis")
        
        # Format market data for AI
        market_description = self._format_market_data(market_data)
        
        response = self.chat(
            message=market_description,
            model=model,
            system_prompt=system_prompt,
            temperature=0.3,  # Lower temperature for more consistent analysis
            response_format={"type": "json_object"},
        )
        
        try:
            # Parse JSON response
            analysis_data = json.loads(response.content)
            return MarketAnalysis(**analysis_data)
        except (json.JSONDecodeError, Exception) as e:
            self._log.error(f"Failed to parse market analysis: {e}")
            raise AIResponseError(f"Invalid JSON response: {e}")
    
    def generate_trading_signal(
        self,
        market_data: dict[str, Any],
        current_prices: dict[str, float] | None = None,
        model: str | None = None,
    ) -> TradingSignal:
        """
        Generate trading signal using AI.
        
        Parameters
        ----------
        market_data : Dictionary containing market information
        current_prices : Current UP/DOWN prices
        model : Override default model
        
        Returns
        -------
        TradingSignal with structured signal
        """
        system_prompt = ModelConfig.get_system_prompt("trading_signal")
        
        # Format market data for AI
        description = self._format_market_data(market_data)
        
        if current_prices:
            description += f"\n\nCurrent Prices:\n"
            description += f"UP: {current_prices.get('up', 'N/A')}\n"
            description += f"DOWN: {current_prices.get('down', 'N/A')}\n"
        
        response = self.chat(
            message=description,
            model=model,
            system_prompt=system_prompt,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        
        try:
            signal_data = json.loads(response.content)
            return TradingSignal(**signal_data)
        except (json.JSONDecodeError, Exception) as e:
            self._log.error(f"Failed to parse trading signal: {e}")
            raise AIResponseError(f"Invalid JSON response: {e}")
    
    def _format_market_data(self, market_data: dict[str, Any]) -> str:
        """Format market data into readable text for AI."""
        lines = ["Market Analysis Request:"]
        
        for key, value in market_data.items():
            if value is not None:
                lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make HTTP request with retry logic."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self._client.post(
                    f"{self.BASE_URL}/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Check for API errors in response
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    error_type = data["error"].get("type", "")
                    
                    if "authentication" in error_type.lower() or response.status_code == 401:
                        raise AIAuthenticationError(f"Authentication failed: {error_msg}")
                    elif "quota" in error_type.lower() or response.status_code == 429:
                        raise AIQuotaExceededError(f"Quota exceeded: {error_msg}")
                    elif "model" in error_type.lower():
                        raise AIModelNotFoundError(f"Model not found: {error_msg}")
                    else:
                        raise AIResponseError(f"API error: {error_msg}")
                
                return data
                
            except httpx.TimeoutException as e:
                last_error = AITimeoutError(f"Request timeout: {e}")
                self._log.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries}")
                
            except httpx.ConnectError as e:
                last_error = AIConnectionError(f"Connection failed: {e}")
                self._log.warning(f"Connection error on attempt {attempt + 1}/{self.max_retries}")
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise AIAuthenticationError("Invalid API key")
                elif e.response.status_code == 429:
                    last_error = AIQuotaExceededError("Rate limit exceeded")
                    self._log.warning(f"Rate limit on attempt {attempt + 1}/{self.max_retries}")
                elif e.response.status_code == 404:
                    raise AIModelNotFoundError("Model not found")
                else:
                    last_error = AIResponseError(f"HTTP error {e.response.status_code}")
                    self._log.warning(f"HTTP error on attempt {attempt + 1}/{self.max_retries}")
                
            except (AIAuthenticationError, AIModelNotFoundError):
                # Don't retry auth or model errors
                raise
                
            except Exception as e:
                last_error = AIResponseError(f"Unexpected error: {e}")
                self._log.warning(f"Unexpected error on attempt {attempt + 1}/{self.max_retries}")
        
        # All retries exhausted
        raise last_error or AIResponseError("Max retries exceeded")
    
    @property
    def total_cost(self) -> float:
        """Total cost of all requests made."""
        return self._total_cost
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used across all requests."""
        return self._total_tokens
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
