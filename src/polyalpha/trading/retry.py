"""
Retry Decorator — Generic retry logic for transient errors.

This module provides a decorator for retrying failed operations with
exponential backoff, useful for handling transient network errors and
temporary API failures.

Usage
-----
    from polyalpha.trading.retry import retry_on_error

    @retry_on_error(max_attempts=3, delay=1.0)
    def place_order():
        # Order placement logic
        pass
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, Type, Union

from ..core import TransientError, NetworkError

log = logging.getLogger(__name__)


def retry_on_error(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[Type[Exception], ...] = (TransientError, NetworkError, TimeoutError),
    ignore_on: tuple[Type[Exception], ...] = (),
) -> Callable:
    """
    Decorator for retrying failed operations with exponential backoff.

    Parameters
    ----------
    max_attempts : int
        Maximum number of retry attempts (default: 3)
    delay : float
        Initial delay between retries in seconds (default: 1.0)
    backoff_factor : float
        Multiplier for exponential backoff (default: 2.0)
    retry_on : tuple[Type[Exception], ...]
        Exception types that should trigger a retry
    ignore_on : tuple[Type[Exception], ...]
        Exception types that should not be retried (will raise immediately)

    Returns
    -------
    Callable
        Decorated function with retry logic

    Example
    -------
    >>> @retry_on_error(max_attempts=5, delay=2.0)
    >>> def fetch_orderbook():
    ...     # May fail due to network issues
    ...     return api.get_orderbook()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except ignore_on as e:
                    # Don't retry on these exceptions
                    log.error("Non-retryable error in %s: %s", func.__name__, e)
                    raise
                except retry_on as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        # Calculate delay with exponential backoff
                        current_delay = delay * (backoff_factor ** attempt)
                        log.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                            attempt + 1, max_attempts, func.__name__, e, current_delay
                        )
                        time.sleep(current_delay)
                    else:
                        log.error(
                            "All %d attempts failed for %s",
                            max_attempts, func.__name__
                        )
                        raise
                except Exception as e:
                    # Unexpected exception - don't retry
                    log.error("Unexpected error in %s: %s", func.__name__, e)
                    raise
            
            # This should never be reached, but just in case
            if last_error:
                raise last_error
            raise RuntimeError(f"Function {func.__name__} failed without exception")
        
        return wrapper
    return decorator


def retry_with_jitter(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    retry_on: tuple[Type[Exception], ...] = (TransientError, NetworkError, TimeoutError),
) -> Callable:
    """
    Decorator for retrying with jitter to avoid thundering herd problems.

    Similar to retry_on_error but adds random jitter to retry delays to
    prevent synchronized retries from multiple clients.

    Parameters
    ----------
    max_attempts : int
        Maximum number of retry attempts
    delay : float
        Initial delay between retries in seconds
    backoff_factor : float
        Multiplier for exponential backoff
    jitter : float
        Jitter factor as percentage (0.1 = ±10% random variation)
    retry_on : tuple[Type[Exception], ...]
        Exception types that should trigger a retry

    Returns
    -------
    Callable
        Decorated function with retry logic and jitter

    Example
    -------
    >>> @retry_with_jitter(max_attempts=3, jitter=0.2)
    >>> def place_order():
    ...     return api.place_order()
    """
    import random

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        # Calculate delay with exponential backoff and jitter
                        base_delay = delay * (backoff_factor ** attempt)
                        jitter_amount = base_delay * jitter * (random.random() * 2 - 1)
                        current_delay = base_delay + jitter_amount
                        current_delay = max(0, current_delay)  # Ensure non-negative
                        
                        log.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.1fs (with jitter)",
                            attempt + 1, max_attempts, func.__name__, e, current_delay
                        )
                        time.sleep(current_delay)
                    else:
                        log.error(
                            "All %d attempts failed for %s",
                            max_attempts, func.__name__
                        )
                        raise
                except Exception as e:
                    log.error("Unexpected error in %s: %s", func.__name__, e)
                    raise
            
            if last_error:
                raise last_error
            raise RuntimeError(f"Function {func.__name__} failed without exception")
        
        return wrapper
    return decorator
