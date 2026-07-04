"""
AI-powered market analysis and trading signals using OpenRouter API.
"""

from .client import OpenRouterClient
from .errors import (
    AIAuthenticationError,
    AIConnectionError,
    AIError,
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

__all__ = [
    "OpenRouterClient",
    "AIError",
    "AIAuthenticationError",
    "AIModelNotFoundError",
    "AIQuotaExceededError",
    "AIResponseError",
    "AITimeoutError",
    "AIConnectionError",
    "AIResponse",
    "ChatMessage",
    "MarketAnalysis",
    "TradingSignal",
    "ModelConfig",
]
