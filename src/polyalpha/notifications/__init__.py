"""
Notifications package for polyalpha.

Provides notification channels for trading events (buy, sell, resolve, etc.).
Currently supports Telegram notifications.
"""

from .telegram import TelegramNotifier, send_telegram_message

__all__ = ["TelegramNotifier", "send_telegram_message"]
