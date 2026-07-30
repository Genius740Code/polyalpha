"""
Telegram notification module for polyalpha.

Provides simple Telegram notification support for trading events.
Designed to be extensible for future notification types.
"""

import asyncio
import logging
import os
from typing import Optional

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

log = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Simple Telegram notifier for trading events.
    
    Parameters
    ----------
    bot_token : str, optional
        Telegram bot token. If not provided, reads from TELEGRAM_BOT_TOKEN env var.
    chat_id : str, optional
        Telegram chat ID to send messages to. If not provided, reads from 
        TELEGRAM_CHAT_ID env var.
    
    Usage
    -----
        notifier = TelegramNotifier()
        notifier.send_buy("BTC", "UP", 20, 0.95)
        notifier.send_resolve("BTC", "UP", "YES", 15.50)
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self._bot: Optional[Bot] = None
        
        if not TELEGRAM_AVAILABLE:
            log.warning("python-telegram-bot not installed. Telegram notifications disabled.")
            return
        
        if not self._bot_token or not self._chat_id:
            log.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Telegram notifications disabled.")
            return
        
        try:
            self._bot = Bot(token=self._bot_token)
            log.info("Telegram notifier initialized")
        except Exception as e:
            log.error("Failed to initialize Telegram bot: %s", e)
    
    def _is_enabled(self) -> bool:
        """Check if Telegram notifications are properly configured."""
        return TELEGRAM_AVAILABLE and self._bot is not None and self._chat_id is not None
    
    def _send_message(self, message: str) -> bool:
        """
        Send a message to Telegram.
        
        Returns
        -------
        bool
            True if message sent successfully, False otherwise.
        """
        if not self._is_enabled():
            return False
        
        async def _async_send() -> bool:
            try:
                await self._bot.send_message(chat_id=self._chat_id, text=message, parse_mode="HTML")
                return True
            except TelegramError as e:
                log.error("Failed to send Telegram message: %s", e)
                return False
            except Exception:
                log.exception("Unexpected error sending Telegram message")
                return False
        
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(_async_send())
            return True
        except RuntimeError:
            try:
                return asyncio.run(_async_send())
            except RuntimeError as e:
                log.error("Failed to send Telegram message: %s", e)
                return False
    
    def send_buy(
        self,
        asset: str,
        side: str,
        amount: float,
        price: float,
        strategy_name: Optional[str] = None
    ) -> bool:
        """
        Send a buy notification.
        
        Parameters
        ----------
        asset : str
            Asset being traded (e.g., "BTC").
        side : str
            Side of the trade ("UP" or "DOWN").
        amount : float
            Amount in USDC spent.
        price : float
            Price at which the buy was executed.
        strategy_name : str, optional
            Name of the strategy that made the trade.
        
        Returns
        -------
        bool
            True if notification sent successfully.
        """
        strategy_suffix = f" [{strategy_name}]" if strategy_name else ""
        message = (
            f"🟢 <b>BUY{strategy_suffix}</b>\n"
            f"Asset: {asset}\n"
            f"Side: {side}\n"
            f"Amount: ${amount:.2f}\n"
            f"Price: {price:.4f}"
        )
        return self._send_message(message)
    
    def send_sell(
        self,
        asset: str,
        side: str,
        amount: float,
        price: float,
        strategy_name: Optional[str] = None
    ) -> bool:
        """
        Send a sell notification.
        
        Parameters
        ----------
        asset : str
            Asset being traded (e.g., "BTC").
        side : str
            Side of the trade ("UP" or "DOWN").
        amount : float
            Amount in USDC received.
        price : float
            Price at which the sell was executed.
        strategy_name : str, optional
            Name of the strategy that made the trade.
        
        Returns
        -------
        bool
            True if notification sent successfully.
        """
        strategy_suffix = f" [{strategy_name}]" if strategy_name else ""
        message = (
            f"🔴 <b>SELL{strategy_suffix}</b>\n"
            f"Asset: {asset}\n"
            f"Side: {side}\n"
            f"Amount: ${amount:.2f}\n"
            f"Price: {price:.4f}"
        )
        return self._send_message(message)
    
    def send_resolve(
        self,
        asset: str,
        side: str,
        outcome: str,
        pnl: float,
        strategy_name: Optional[str] = None
    ) -> bool:
        """
        Send a position resolution notification.
        
        Parameters
        ----------
        asset : str
            Asset being traded (e.g., "BTC").
        side : str
            Side of the position ("UP" or "DOWN").
        outcome : str
            Resolution outcome ("YES" or "NO").
        pnl : float
            Profit or loss from the position.
        strategy_name : str, optional
            Name of the strategy that held the position.
        
        Returns
        -------
        bool
            True if notification sent successfully.
        """
        emoji = "✅" if pnl >= 0 else "❌"
        strategy_suffix = f" [{strategy_name}]" if strategy_name else ""
        message = (
            f"{emoji} <b>RESOLVE{strategy_suffix}</b>\n"
            f"Asset: {asset}\n"
            f"Side: {side}\n"
            f"Outcome: {outcome}\n"
            f"P&L: ${pnl:+.2f}"
        )
        return self._send_message(message)
    
    def send_custom(self, message: str) -> bool:
        """
        Send a custom message.
        
        Parameters
        ----------
        message : str
            Custom message to send. Supports HTML formatting.
        
        Returns
        -------
        bool
            True if notification sent successfully.
        """
        return self._send_message(message)


# Global notifier instance for convenience
_global_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    """
    Get or create the global Telegram notifier instance.
    
    Returns
    -------
    TelegramNotifier
        The global notifier instance.
    """
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = TelegramNotifier()
    return _global_notifier


def send_telegram_message(message: str) -> bool:
    """
    Convenience function to send a custom Telegram message using the global notifier.
    
    Parameters
    ----------
    message : str
        Message to send. Supports HTML formatting.
    
    Returns
    -------
    bool
        True if message sent successfully.
    """
    return get_telegram_notifier().send_custom(message)
