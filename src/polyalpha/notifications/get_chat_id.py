"""
Utility to get your Telegram chat ID.

This script helps you find your Telegram chat ID for setting up notifications.

Usage:
    python -m polyalpha.notifications.get_chat_id YOUR_BOT_TOKEN
    
Or set environment variable:
    export TELEGRAM_BOT_TOKEN=your_bot_token
    python -m polyalpha.notifications.get_chat_id

Steps:
1. Create a bot via @BotFather on Telegram and get your bot token
2. Run this script with your bot token
3. Send a message to your bot on Telegram (any message like "hello")
4. This script will print your chat ID
5. Use the chat ID in your .env file as TELEGRAM_CHAT_ID
"""

import asyncio
import os
import sys


async def get_chat_id(bot_token: str) -> str:
    """
    Get the latest chat ID from Telegram bot updates.
    
    Parameters
    ----------
    bot_token : str
        Your Telegram bot token from @BotFather
    
    Returns
    -------
    str
        The chat ID or error message
    """
    try:
        from telegram import Bot
        from telegram.error import TelegramError
    except ImportError:
        return "Error: python-telegram-bot not installed. Run: pip install python-telegram-bot>=20.0"
    
    try:
        bot = Bot(token=bot_token)
        updates = await bot.get_updates()
        
        if not updates:
            return "No updates found. Please send a message to your bot first, then run this script again."
        
        # Get the most recent update
        latest_update = updates[-1]
        chat_id = latest_update.effective_chat.id
        
        # Also get username if available
        username = latest_update.effective_chat.username or "N/A"
        
        return f"Chat ID: {chat_id}\nUsername: @{username}"
        
    except TelegramError as e:
        return f"Telegram API error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


async def main_async():
    """Async main entry point."""
    # Get bot token from command line or environment variable
    if len(sys.argv) > 1:
        bot_token = sys.argv[1]
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not bot_token:
        print("Error: No bot token provided.")
        print("\nUsage:")
        print("  python -m polyalpha.notifications.get_chat_id YOUR_BOT_TOKEN")
        print("\nOr set environment variable:")
        print("  export TELEGRAM_BOT_TOKEN=your_bot_token")
        print("  python -m polyalpha.notifications.get_chat_id")
        sys.exit(1)
    
    print("Fetching chat ID...")
    print("-" * 50)
    result = await get_chat_id(bot_token)
    print(result)
    print("-" * 50)
    
    if result.startswith("Chat ID:"):
        print("\n✅ Success! Add this to your .env file:")
        print(f"TELEGRAM_CHAT_ID={result.split(':')[1].split()[0]}")


def main():
    """Main entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
