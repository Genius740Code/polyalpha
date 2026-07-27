# Telegram Notifications

Polyalpha supports Telegram notifications for trading events (buy, sell, resolve). This feature allows you to receive real-time alerts when your bot executes trades or positions are resolved.

## Setup

### 1. Install Dependencies

```bash
pip install python-telegram-bot>=20.0
```

### 2. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the instructions
3. Choose a name and username for your bot
4. Copy the **bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 3. Get Your Chat ID

Use the included utility script to get your chat ID:

```bash
# Option 1: Pass bot token as argument
python -m polyalpha.notifications.get_chat_id YOUR_BOT_TOKEN

# Option 2: Set environment variable
export TELEGRAM_BOT_TOKEN=your_bot_token
python -m polyalpha.notifications.get_chat_id
```

**Important:** Send a message to your bot on Telegram first, then run the script. The script will output your chat ID.

### 4. Configure Environment Variables

Add the following to your `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## Usage

### Automatic Notifications

Telegram notifications are automatically sent for the following events when configured:

- **Buy orders** - When `ctx.buy()` is called
- **Sell orders** - When `ctx.close_position()` is called  
- **Position resolution** - When a position is resolved (win/loss)

### Single Bot Example

```python
import polyalpha

bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi > 50:
        ctx.buy("UP", 20)  # Telegram notification sent automatically

bot.run()
```

### BotHub Example (Multi-Strategy)

```python
import polyalpha

hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

@hub.strategy("momentum")
def momentum(ctx):
    if ctx.price.up > 0.9:
        ctx.buy("UP", 20)  # Notification includes strategy name "momentum"

@hub.strategy("value")
def value(ctx):
    if ctx.price.down < 0.10:
        ctx.buy("DOWN", 10)  # Notification includes strategy name "value"

hub.run()
```

### Custom Notifications

You can also send custom messages:

```python
from polyalpha.notifications import send_telegram_message

send_telegram_message("🚀 Bot started successfully!")
```

## Notification Format

### Buy Notification
```
🟢 BUY
Asset: BTC
Side: UP
Amount: $20.00
Price: 0.9500
```

### Sell Notification
```
🔴 SELL
Asset: BTC
Side: UP
Amount: $20.00
Price: 0.9500
```

### Resolve Notification
```
✅ RESOLVE
Asset: BTC
Side: UP
Outcome: YES
P&L: $15.50
```

For BotHub, notifications include the strategy name:
```
🟢 BUY [momentum]
Asset: BTC
Side: UP
Amount: $20.00
Price: 0.9500
```

## Configuration Reference

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Your Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID (use get_chat_id.py) |

### Optional: Paper Trading Configuration

Telegram notifications work with all paper trading modes:

```python
from polyalpha.trading.paper_config import PaperConfig

paper_config = PaperConfig(
    fee_mode="custom",
    custom_fee_rate=0.01,
    execution_delay_ms=2000,
    slippage_pct=0.10,
)

bot = polyalpha.Bot("BTC", "5m", mode="custom", paper_config=paper_config)
```

## Troubleshooting

### Notifications Not Sending

1. **Check environment variables are set:**
   ```bash
   echo $TELEGRAM_BOT_TOKEN
   echo $TELEGRAM_CHAT_ID
   ```

2. **Verify python-telegram-bot is installed:**
   ```bash
   pip show python-telegram-bot
   ```

3. **Test your bot token:**
   ```bash
   python -m polyalpha.notifications.get_chat_id YOUR_BOT_TOKEN
   ```

4. **Check bot logs for errors:**
   - Look for "Telegram notifications disabled" warnings
   - Check for "Failed to send Telegram message" errors

### Invalid Chat ID

- Make sure you sent a message to your bot before running `get_chat_id.py`
- The chat ID can change if you delete and recreate your bot
- For groups, use the group ID (negative number)

### Rate Limiting

Telegram has rate limits on bot messages. If you're running many strategies simultaneously, you may hit these limits. The notification system gracefully handles failures and logs errors without interrupting your bot.

## Advanced Usage

### Custom TelegramNotifier Instance

```python
from polyalpha.notifications.telegram import TelegramNotifier

# Create custom notifier with explicit credentials
notifier = TelegramNotifier(
    bot_token="your_token",
    chat_id="your_chat_id"
)

# Send notifications manually
notifier.send_buy("BTC", "UP", 20, 0.95)
notifier.send_resolve("BTC", "UP", "YES", 15.50)
```

### Conditional Notifications

You can disable notifications for specific strategies by not setting the environment variables, or by checking conditions in your strategy:

```python
@bot.on_tick
def strategy(ctx):
    # Only notify on large trades
    if should_notify:
        ctx.buy("UP", 100)  # Will send notification
    else:
        # Direct paper engine call (bypasses notification)
        ctx._client.paper.buy(market=ctx._market, side="UP", amount=10)
```

## Security Best Practices

1. **Never commit your `.env` file** to version control
2. **Use different bot tokens** for development and production
3. **Limit bot permissions** - only enable necessary features in @BotFather
4. **Monitor your bot's activity** in Telegram for unauthorized usage
5. **Rotate tokens periodically** if you suspect compromise

## Future Enhancements

The notification system is designed to be extensible. Planned features include:

- Support for additional notification channels (Discord, Slack, email)
- Custom notification templates
- Notification filtering (e.g., only notify on wins > $10)
- Notification aggregation (batch notifications)
- Webhook support for custom integrations

## API Reference

### TelegramNotifier

```python
class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None)
    def send_buy(self, asset: str, side: str, amount: float, price: float, strategy_name: Optional[str] = None) -> bool
    def send_sell(self, asset: str, side: str, amount: float, price: float, strategy_name: Optional[str] = None) -> bool
    def send_resolve(self, asset: str, side: str, outcome: str, pnl: float, strategy_name: Optional[str] = None) -> bool
    def send_custom(self, message: str) -> bool
```

### Convenience Functions

```python
def get_telegram_notifier() -> TelegramNotifier
def send_telegram_message(message: str) -> bool
```
