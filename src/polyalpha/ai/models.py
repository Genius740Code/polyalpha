"""
Model configuration and response schemas for OpenRouter integration.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A message in the chat conversation."""
    role: Literal["system", "user", "assistant"]
    content: str


class MarketAnalysis(BaseModel):
    """Structured market analysis response from AI."""
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(description="Market sentiment")
    confidence: float = Field(description="Confidence score between 0 and 1", ge=0, le=1)
    reasoning: str = Field(description="Explanation for the sentiment")
    risk_factors: list[str] = Field(default_factory=list, description="Identified risk factors")
    key_indicators: dict[str, Any] = Field(default_factory=dict, description="Key technical indicators")


class TradingSignal(BaseModel):
    """Structured trading signal from AI."""
    action: Literal["BUY", "SELL", "HOLD"] = Field(description="Recommended action")
    side: Literal["UP", "DOWN"] | None = Field(default=None, description="Which side to trade")
    amount: float | None = Field(default=None, description="Recommended amount in USDC")
    confidence: float = Field(description="Confidence score between 0 and 1", ge=0, le=1)
    reasoning: str = Field(description="Explanation for the signal")
    entry_price: float | None = Field(default=None, description="Suggested entry price")
    stop_loss: float | None = Field(default=None, description="Suggested stop loss price")
    take_profit: float | None = Field(default=None, description="Suggested take profit price")


class AIResponse(BaseModel):
    """Generic AI response wrapper."""
    content: str = Field(description="The text content of the response")
    model: str = Field(description="The model that generated the response")
    prompt_tokens: int = Field(description="Number of tokens in the prompt")
    completion_tokens: int = Field(description="Number of tokens in the completion")
    total_tokens: int = Field(description="Total number of tokens")
    cost: float | None = Field(default=None, description="Cost in credits")


class ModelConfig:
    """Configuration for AI models."""
    
    DEFAULT_MODEL = "openai/gpt-4o-mini"
    FALLBACK_MODEL = "openai/gpt-3.5-turbo"
    
    # Model aliases for convenience
    MODEL_ALIASES = {
        "gpt4": "openai/gpt-4o",
        "gpt4-mini": "openai/gpt-4o-mini",
        "gpt3": "openai/gpt-3.5-turbo",
        "claude": "anthropic/claude-3-haiku",
        "default": DEFAULT_MODEL,
    }
    
    @classmethod
    def resolve_model(cls, model: str) -> str:
        """Resolve model alias to actual model ID."""
        return cls.MODEL_ALIASES.get(model.lower(), model)
    
    @classmethod
    def get_system_prompt(cls, task: str) -> str:
        """Get system prompt for specific tasks."""
        prompts = {
            "market_analysis": """You are an expert cryptocurrency market analyst specializing in prediction markets. 
Analyze the given market data and provide:
1. Market sentiment (bullish/bearish/neutral)
2. Confidence level (0-1)
3. Clear reasoning
4. Key risk factors
5. Important technical indicators

Respond in JSON format with the following structure:
{
    "sentiment": "bullish|bearish|neutral",
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation",
    "risk_factors": ["factor1", "factor2"],
    "key_indicators": {"indicator": "value"}
}""",
            
            "trading_signal": """You are an expert trading signal generator for cryptocurrency prediction markets.
Generate trading signals based on market data with:
1. Action (BUY/SELL/HOLD)
2. Side (UP/DOWN) for prediction markets
3. Recommended amount in USDC
4. Confidence level (0-1)
5. Clear reasoning
6. Entry, stop loss, and take profit suggestions if applicable

Respond in JSON format with the following structure:
{
    "action": "BUY|SELL|HOLD",
    "side": "UP|DOWN|null",
    "amount": number or null,
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation",
    "entry_price": number or null,
    "stop_loss": number or null,
    "take_profit": number or null
}""",
            
            "general": """You are a helpful AI assistant for cryptocurrency prediction market analysis.
Provide clear, accurate, and actionable insights based on the given information."""
        }
        return prompts.get(task, prompts["general"])
