"""
Example: Using Telegram notifications with polyalpha.

This example demonstrates how to enable Telegram notifications for buy/sell/resolve events.

Setup:
1. Create a Telegram bot via @BotFather and get your bot token
2. Get your chat ID by messaging @userinfobot
3. Set environment variables:
   export TELEGRAM_BOT_TOKEN=your_bot_token_here
   export TELEGRAM_CHAT_ID=your_chat_id_here
4. Install python-telegram-bot: pip install python-telegram-bot>=20.0
"""

import polyalpha

# Example 1: Single bot with Telegram notifications
bot = polyalpha.Bot("BTC", "5m", balance=500)

@bot.on_tick
def strategy(ctx):
    if ctx.price.up > 0.9 and ctx.rsi and ctx.rsi > 50:
        ctx.buy("UP", 20)  # This will send a Telegram notification if configured

@bot.onresolve
def on_resolve(pos):
    print(f"Resolved: {pos.side} {pos.outcome} P&L=${pos.pnl:.2f}")

# Run the bot - Telegram notifications will be sent automatically
# bot.run()


# Example 2: BotHub with Telegram notifications (includes strategy name)
hub = polyalpha.BotHub("BTC", "5m", default_balance=500)

@hub.strategy("momentum")
def momentum(ctx):
    if ctx.price.up > 0.9:
        ctx.buy("UP", 20)  # Notification will include strategy name "momentum"

@hub.strategy("value")
def value(ctx):
    if ctx.price.down < 0.10:
        ctx.buy("DOWN", 10)  # Notification will include strategy name "value"

# Run the hub - Telegram notifications will be sent for each strategy
# hub.run()


# Example 3: Manual Telegram notification (custom messages)
from polyalpha.notifications import send_telegram_message

# Send a custom message
# send_telegram_message("🚀 Bot started successfully!")
