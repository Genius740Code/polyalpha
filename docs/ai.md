# AI-Powered Analysis

AI integration via OpenRouter API for market analysis and trading signal generation. Access via `client.ai` or directly via `OpenRouterClient`.

```python
import polyalpha

client = polyalpha.Client()

# AI-powered market analysis
analysis = client.ai.analyze_market({"question": "Will BTC exceed $60k?", "volume": 500000})
print(analysis.sentiment, analysis.confidence)

# AI-generated trading signal
signal = client.ai.generate_trading_signal({"question": "Will BTC exceed $60k?"}, {"up": 0.85, "down": 0.15})
print(signal.action, signal.side, signal.confidence)

# General chat
response = client.ai.chat("What do you think about BTC?")
print(response.content)
```

---

## OpenRouterClient

```python
from polyalpha.ai import OpenRouterClient

client = OpenRouterClient(
    api_key="sk-or-v1-...",   # OpenRouter API key
    model="openai/gpt-4o-mini",  # default model
    timeout=30,               # request timeout in seconds
    max_retries=3,            # max retry attempts
    enable_cost_tracking=True,# track usage costs
)
```

### Constructor Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `api_key` | — | OpenRouter API key (required) |
| `model` | `"openai/gpt-4o-mini"` | Default model |
| `timeout` | `30` | Request timeout in seconds |
| `max_retries` | `3` | Maximum retry attempts on transient errors |
| `enable_cost_tracking` | `True` | Track total cost and token usage |

### Model Aliases

| Alias | Resolves To |
|-------|-------------|
| `"gpt4"` | `"openai/gpt-4o"` |
| `"gpt4-mini"` | `"openai/gpt-4o-mini"` |
| `"gpt3"` | `"openai/gpt-3.5-turbo"` |
| `"claude"` | `"anthropic/claude-3-haiku"` |
| `"default"` | `"openai/gpt-4o-mini"` |

```python
client = OpenRouterClient(api_key="...", model="claude")
# Resolves to "anthropic/claude-3-haiku"
```

### Methods

#### `chat(message, model=None, system_prompt=None, temperature=0.7, max_tokens=None, response_format=None)`

Send a chat completion request.

```python
response = client.chat(
    message="What's the current sentiment on BTC?",
    system_prompt="You are a crypto market analyst.",
    temperature=0.5,
)
print(response.content)
print(f"Tokens: {response.total_tokens}, Cost: ${response.cost}")
```

| Param | Type | Description |
|-------|------|-------------|
| `message` | `str` | User message |
| `model` | `str \| None` | Override default model |
| `system_prompt` | `str \| None` | System prompt for context |
| `temperature` | `float` | Sampling temperature (0–2) |
| `max_tokens` | `int \| None` | Max tokens to generate |
| `response_format` | `dict \| None` | e.g., `{"type": "json_object"}` |

Returns `AIResponse`.

#### `analyze_market(market_data, model=None)`

Analyze market data with structured output.

```python
market_data = {
    "question": "Will BTC exceed $60,000 by July?",
    "current_up_price": 0.72,
    "current_down_price": 0.28,
    "volume": 1250000,
    "liquidity": 500000,
    "time_remaining": "2 days 4 hours",
}

analysis = client.ai.analyze_market(market_data)
print(analysis.sentiment)    # "bullish" | "bearish" | "neutral"
print(analysis.confidence)   # 0.0–1.0
print(analysis.reasoning)    # explanation string
print(analysis.risk_factors) # list of risk strings
print(analysis.key_indicators) # dict of indicators
```

| Param | Type | Description |
|-------|------|-------------|
| `market_data` | `dict` | Market information (question, prices, volume, liquidity, etc.) |
| `model` | `str \| None` | Override default model |

Returns `MarketAnalysis`.

#### `generate_trading_signal(market_data, current_prices=None, model=None)`

Generate a structured trading signal.

```python
signal = client.ai.generate_trading_signal(
    market_data={"question": "Will BTC exceed $60k?", "volume": 500000},
    current_prices={"up": 0.85, "down": 0.15},
)
print(signal.action)       # "BUY" | "SELL" | "HOLD"
print(signal.side)         # "UP" | "DOWN" | None
print(signal.amount)       # recommended USDC amount
print(signal.confidence)   # 0.0–1.0
print(signal.entry_price)  # suggested entry
print(signal.stop_loss)    # suggested stop loss
print(signal.take_profit)  # suggested take profit
```

| Param | Type | Description |
|-------|------|-------------|
| `market_data` | `dict` | Market information |
| `current_prices` | `dict \| None` | Current UP/DOWN prices |
| `model` | `str \| None` | Override default model |

Returns `TradingSignal`.

#### `close()`

Clean up the HTTP client.

```python
client.close()
```

Also usable as a context manager:

```python
with OpenRouterClient(api_key="...") as client:
    response = client.chat("Analyze BTC")
```

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `total_cost` | `float` | Total cost of all requests (in credits) |
| `total_tokens` | `int` | Total tokens used across all requests |

---

## Response Models

### AIResponse

Returned by `chat()`.

| Field | Type | Description |
|-------|------|-------------|
| `content` | `str` | The text content |
| `model` | `str` | Model that generated the response |
| `prompt_tokens` | `int` | Tokens in the prompt |
| `completion_tokens` | `int` | Tokens in the completion |
| `total_tokens` | `int` | Total tokens |
| `cost` | `float \| None` | Cost in credits |

### MarketAnalysis

Returned by `analyze_market()`.

| Field | Type | Description |
|-------|------|-------------|
| `sentiment` | `"bullish" \| "bearish" \| "neutral"` | Market sentiment |
| `confidence` | `float` | Confidence score (0–1) |
| `reasoning` | `str` | Explanation for the sentiment |
| `risk_factors` | `list[str]` | Identified risk factors |
| `key_indicators` | `dict` | Key technical indicators |

### TradingSignal

Returned by `generate_trading_signal()`.

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"BUY" \| "SELL" \| "HOLD"` | Recommended action |
| `side` | `"UP" \| "DOWN" \| None` | Which side to trade |
| `amount` | `float \| None` | Recommended USDC amount |
| `confidence` | `float` | Confidence score (0–1) |
| `reasoning` | `str` | Explanation for the signal |
| `entry_price` | `float \| None` | Suggested entry price |
| `stop_loss` | `float \| None` | Suggested stop loss |
| `take_profit` | `float \| None` | Suggested take profit |

### ChatMessage

| Field | Type | Description |
|-------|------|-------------|
| `role` | `"system" \| "user" \| "assistant"` | Message role |
| `content` | `str` | Message content |

---

## Prompt Injection Guards

The `chat()` method automatically scans user messages for prompt injection patterns (ignore previous instructions, reveal system prompt, jailbreak attempts, etc.). When detected, it prepends a safety prefix rather than blocking the message.

---

## Errors

All AI errors inherit from `AIError`.

| Exception | When Raised |
|-----------|-------------|
| `AIAuthenticationError` | Invalid or missing API key (401) |
| `AIModelNotFoundError` | Requested model not available (404) |
| `AIQuotaExceededError` | Rate limit or quota exceeded (429) |
| `AIResponseError` | Malformed or invalid response |
| `AITimeoutError` | Request timed out |
| `AIConnectionError` | Connection to OpenRouter failed |

```python
from polyalpha.ai import (
    AIError, AIAuthenticationError, AIQuotaExceededError,
    AITimeoutError, AIConnectionError, AIModelNotFoundError,
    AIResponseError,
)

try:
    analysis = client.ai.analyze_market(market_data)
except AIAuthenticationError:
    print("Check your API key")
except AIQuotaExceededError:
    print("Out of credits")
except AIError as e:
    print(f"AI error: {e}")
```

---

## Custom Prompts

Override the system prompt for specific tasks:

```python
response = client.ai.chat(
    message="Should I buy UP or DOWN on this BTC market?",
    system_prompt="You are a conservative trader. Only recommend trades with high conviction.",
    temperature=0.3,
)
```

Or pass custom prompts to market analysis:

```python
analysis = client.ai.chat(
    message=f"Market: BTC 5m\nUP: 0.72\nDOWN: 0.28\nVolume: 1.2M",
    system_prompt="Analyze this prediction market and return JSON with sentiment, confidence, and reasoning.",
    response_format={"type": "json_object"},
)
```

---

## Cost Tracking

```python
client = OpenRouterClient(api_key="...", enable_cost_tracking=True)

# After making requests
print(f"Total spent: ${client.total_cost:.4f}")
print(f"Total tokens: {client.total_tokens}")

# Per-request cost
response = client.chat("Analyze BTC")
if response.cost:
    print(f"This request cost: ${response.cost:.4f}")
```
