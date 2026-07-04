# OpenRouter API Integration Plan

## Overview
Add easy-to-use OpenRouter API integration to the polyalpha SDK, enabling AI-powered features with JSON responses and structured outputs for market analysis, trading signals, and automated decision-making.

## Key Features
- **Simple API Connection**: Easy authentication and configuration
- **JSON Responses**: Structured AI outputs for programmatic use
- **Model Flexibility**: Support for any OpenRouter-hosted model
- **Streaming Support**: Real-time AI responses
- **Cost Tracking**: Built-in usage and cost monitoring
- **Error Handling**: Robust error management and retry logic

## Architecture Design

### New Module Structure
```
src/polyalpha/
├── ai/
│   ├── __init__.py
│   ├── client.py           # OpenRouterClient - main AI client
│   ├── models.py           # Model configuration and helpers
│   └── errors.py           # AI-specific exceptions
```

### Core Components

#### 1. OpenRouterClient (`src/polyalpha/ai/client.py`)
- Handles authentication via Bearer token
- Manages HTTP requests to OpenRouter API
- Supports both streaming and non-streaming responses
- Implements retry logic and rate limiting
- Tracks usage and costs

#### 2. Model Configuration (`src/polyalpha/ai/models.py`)
- Model selection helpers
- Default model configurations
- Response format validators
- JSON schema definitions for structured outputs

#### 3. AI Exceptions (`src/polyalpha/ai/errors.py`)
- `AIAuthenticationError`: Invalid API key
- `AIModelNotFoundError`: Model not available
- `AIQuotaExceededError`: Rate limit or quota exceeded
- `AIResponseError`: Malformed or invalid responses

### Integration with Existing Client

Add AI client to main `Client` class:
```python
class Client:
    def __init__(self, ..., openrouter_api_key: str | None = None):
        # ... existing code ...
        self.ai = OpenRouterClient(api_key=openrouter_api_key) if openrouter_api_key else None
```

## API Design

### Basic Usage
```python
import polyalpha

# Initialize with OpenRouter API key
client = polyalpha.Client(openrouter_api_key="your-api-key")

# Simple chat completion
response = client.ai.chat("Analyze this BTC market")
print(response.content)

# Structured JSON response
analysis = client.ai.analyze_market(
    market=market,
    format="json"
)
print(analysis.signals)  # Access structured data
```

### Advanced Features

#### Market Analysis
```python
# AI-powered market analysis
analysis = client.ai.analyze_market(
    market=market,
    include=["sentiment", "technical_indicators", "risk_factors"],
    response_format={"type": "json_object"}
)

# Access structured results
print(analysis.sentiment)  # "bullish" | "bearish" | "neutral"
print(analysis.confidence)  # 0.85
print(analysis.recommendation)  # {"side": "UP", "amount": 25.0}
```

#### Trading Signals
```python
# Generate trading signals
signals = client.ai.generate_signals(
    markets=[btc_market, eth_market],
    timeframe="5m",
    risk_tolerance="medium"
)

for signal in signals:
    print(f"{signal.market}: {signal.action} @ {signal.price}")
```

#### Streaming Responses
```python
# Real-time AI analysis
async for chunk in client.ai.stream_chat("Monitor BTC price movements"):
    print(chunk.content)
```

## Implementation Phases

### Phase 1: Core Infrastructure (Priority: High)
1. Create `src/polyalpha/ai/` module structure
2. Implement `OpenRouterClient` with basic chat completion
3. Add authentication and error handling
4. Write unit tests for core functionality

### Phase 2: JSON & Structured Outputs (Priority: High)
1. Implement response format validation
2. Add JSON schema support for structured outputs
3. Create market-specific analysis templates
4. Add examples and documentation

### Phase 3: Integration & Features (Priority: Medium)
1. Integrate AI client into main `Client` class
2. Implement market analysis methods
3. Add trading signal generation
4. Create streaming support

### Phase 4: Advanced Features (Priority: Low)
1. Add cost tracking and budget controls
2. Implement caching for repeated queries
3. Add multi-model comparison
4. Create custom prompt templates

## Dependencies
- **httpx** (already in project): HTTP client
- **pydantic** (new): For response validation and structured outputs
- Add to `pyproject.toml`:
  ```toml
  dependencies = [
      "httpx>=0.24.0",
      "websocket-client>=1.0.0",
      "pydantic>=2.0.0",  # New
  ]
  ```

## Configuration Options

```python
client = polyalpha.Client(
    openrouter_api_key="your-key",
    openrouter_config={
        "default_model": "openai/gpt-4o",
        "timeout": 30,
        "max_retries": 3,
        "enable_cost_tracking": True,
        "budget_limit": 10.0,  # USD
    }
)
```

## Error Handling Strategy
- Invalid API keys → Clear authentication error
- Rate limits → Automatic retry with exponential backoff
- Invalid responses → Validation error with details
- Model unavailability → Fallback to alternative model
- Cost overruns → Configurable hard/soft limits

## Testing Strategy
1. **Unit Tests**: Mock OpenRouter API responses
2. **Integration Tests**: Test with real API key (optional)
3. **Response Validation**: Test JSON schema validation
4. **Error Scenarios**: Test all error conditions
5. **Cost Tracking**: Verify usage calculations

## Documentation
- Add AI section to README.md
- Create examples/ai.py with usage examples
- Document all AI methods in docstrings
- Add API reference in docs/api-reference.md

## Examples

### Example 1: Basic Market Analysis
```python
import polyalpha

client = polyalpha.Client(openrouter_api_key="your-key")
market = client.markets.latest("BTC", "5m")

analysis = client.ai.analyze_market(market)
print(f"Sentiment: {analysis.sentiment}")
print(f"Recommendation: {analysis.recommendation}")
```

### Example 2: Trading Bot with AI
```python
import polyalpha

client = polyalpha.Client(
    openrouter_api_key="your-key",
    balance=1000.0
)

market = client.markets.latest("ETH", "15m")
stream = client.stream(market)

@stream.on("price")
def on_price(up, down):
    # Get AI recommendation
    signal = client.ai.get_trading_signal(market, up, down)
    
   if signal.action == "BUY" and signal.confidence > 0.8:
        client.paper.buy(market, side=signal.side, amount=signal.amount)

stream.start(background=True)
```

### Example 3: Batch Analysis
```python
import polyalpha

client = polyalpha.Client(openrouter_api_key="your-key")

markets = client.markets.available("5m")
analyses = client.ai.batch_analyze(markets)

for market, analysis in zip(markets, analyses):
    if analysis.sentiment == "bullish" and analysis.confidence > 0.7:
        print(f"Consider {market.slug}: {analysis.recommendation}")
```

## Security Considerations
- API keys should be stored in environment variables
- Never log API keys or sensitive request data
- Implement request signing for production use
- Add rate limiting to prevent accidental overages
- Validate all user inputs before sending to AI

## Performance Considerations
- Implement request caching for identical queries
- Use connection pooling for HTTP requests
- Add timeout configurations to prevent hanging
- Consider async support for high-volume usage
- Monitor and optimize token usage

## Backward Compatibility
- AI features are optional (api_key parameter)
- Existing functionality remains unchanged
- No breaking changes to existing API
- Graceful degradation when AI is unavailable

## Success Metrics
- Easy integration (< 5 lines of code)
- Reliable JSON responses (99%+ success rate)
- Accurate cost tracking (within 1%)
- Comprehensive error handling
- Well-documented with examples

## Future Enhancements
- Multi-model comparison and ensemble
- Custom fine-tuning support
- Image analysis for chart patterns
- Voice/audio input support
- Advanced tool calling for external data
