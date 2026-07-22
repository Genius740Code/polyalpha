"""
Logging utilities for polyalpha with sensitive data redaction.

This module provides custom logging filters and utilities to prevent
sensitive data from being exposed in log files.
"""

import json
import logging
import re
import time
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional, Generator
import uuid


DEFAULT_LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ── Correlation ID (contextvars – flows through threads/async without explicit passing) ────

_correlation_id: ContextVar[str] = ContextVar("_correlation_id", default="")


def set_correlation_id(cid: str) -> None:
    """Set a correlation ID for the current context (thread / async task)."""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    """Return the current correlation ID, or an empty string if unset."""
    return _correlation_id.get()


def new_correlation_id() -> str:
    """Generate and set a new UUID correlation ID, returning it."""
    cid = str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current context."""
    _correlation_id.set("")


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts sensitive information from log messages.
    
    This filter automatically redacts:
    - Wallet addresses (Ethereum-style 0x...)
    - Private keys
    - API keys
    - Passwords
    - Tokens
    - Transaction hashes
    - File paths (optional)
    """

    # Patterns for sensitive data
    PATTERNS = [
        # Ethereum addresses (0x followed by 40 hex chars)
        (r'0x[a-f0-9]{40}', lambda m: f"{m.group(0)[:6]}...{m.group(0)[-4:]}"),
        # Transaction hashes (0x followed by 64 hex chars) - check this before private keys
        (r'0x[a-f0-9]{64}', lambda m: f"{m.group(0)[:10]}...{m.group(0)[-4:]}"),
        # Private keys (long hex strings, typically 64+ chars, but not starting with 0x to avoid conflict)
        # Use positive lookahead to exclude content hashes (sha256:, md5:, hash=, etc.)
        (r'\b(?!(?:sha256:|md5:|sha1:|hash=|checksum=|digest=))[a-f0-9]{64,}\b', lambda m: f"{m.group(0)[:8]}...REDACTED"),
        # API keys in common formats
        (r'api_key["\']?\s*[:=]\s*["\']?[^"\']{8,}["\']?', 'api_key=***REDACTED***'),
        (r'API[_-]?KEY["\']?\s*[:=]\s*["\']?[^"\']{8,}["\']?', 'API_KEY=***REDACTED***'),
        # Passwords
        (r'password["\']?\s*[:=]\s*["\']?[^"\']{4,}["\']?', 'password=***REDACTED***'),
        (r'PASSWORD["\']?\s*[:=]\s*["\']?[^"\']{4,}["\']?', 'PASSWORD=***REDACTED***'),
        # Tokens (Bearer, JWT, etc.)
        (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer ***REDACTED***'),
        (r'token["\']?\s*[:=]\s*["\']?[^"\']{10,}["\']?', 'token=***REDACTED***'),
        (r'TOKEN["\']?\s*[:=]\s*["\']?[^"\']{10,}["\']?', 'TOKEN=***REDACTED***'),
        # Secret keys
        (r'secret["\']?\s*[:=]\s*["\']?[^"\']{8,}["\']?', 'secret=***REDACTED***'),
        (r'SECRET["\']?\s*[:=]\s*["\']?[^"\']{8,}["\']?', 'SECRET=***REDACTED***'),
    ]

    def __init__(self, redact_file_paths: bool = False):
        """
        Initialize the filter.
        
        Parameters
        ----------
        redact_file_paths : bool
            If True, also redact file paths from logs. Default is False
            as file paths are typically less sensitive than credentials.
        """
        super().__init__()
        self.redact_file_paths = redact_file_paths
        
        if redact_file_paths:
            # Add file path pattern
            self.PATTERNS.append(
                (r'[A-Za-z]:\\[^"\']+\.(json|txt|log|pem|key)', '***REDACTED_PATH***')
            )

    def redact_string(self, text: str) -> str:
        """
        Apply redaction patterns to a string.
        
        Parameters
        ----------
        text : str
            The text to redact
            
        Returns
        -------
        str
            Redacted text
        """
        for pattern, replacement in self.PATTERNS:
            if callable(replacement):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            else:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record and redact sensitive information.
        
        Parameters
        ----------
        record : logging.LogRecord
            The log record to filter
            
        Returns
        -------
        bool
            Always returns True to allow the record to be logged
        """
        # Redact args first (these are the values passed to % formatting)
        if hasattr(record, 'args') and record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self.redact_string(arg))
                elif isinstance(arg, (bytes, bytearray)):
                    try:
                        decoded = arg.decode("utf-8", errors="replace")
                        new_args.append(self.redact_string(decoded))
                    except Exception:
                        new_args.append(arg)
                elif isinstance(arg, (int, float)):
                    new_args.append(arg)
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        
        # Don't redact the message template - it may contain format specifiers
        # The args are already redacted, so the final formatted message will be safe
        
        return True


class SensitiveDataFormatter(logging.Formatter):
    """
    Custom formatter that redacts sensitive information from log messages.
    
    This formatter applies redaction to the final formatted message,
    ensuring that sensitive data is redacted even when using complex formatting.
    """

    def __init__(self, fmt=None, datefmt=None, style='%', redact_file_paths=False, include_correlation_id=True):
        """
        Initialize the formatter.
        
        Parameters
        ----------
        fmt : str, optional
            Format string for the log message
        datefmt : str, optional
            Format string for the timestamp
        style : str
            Formatting style (%, {, or $)
        redact_file_paths : bool
            If True, also redact file paths from logs
        include_correlation_id : bool
            If True, prepend [cid=...] when a correlation ID is set
        """
        super().__init__(fmt, datefmt, style)
        self.filter = SensitiveDataFilter(redact_file_paths=redact_file_paths)
        self.include_correlation_id = include_correlation_id

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record and redact sensitive information.
        
        Parameters
        ----------
        record : logging.LogRecord
            The log record to format
            
        Returns
        -------
        str
            Formatted and redacted log message
        """
        # First apply the filter to redact args and msg
        self.filter.filter(record)
        
        # Then format normally
        formatted = super().format(record)
        
        # Prepend correlation ID if set
        cid = get_correlation_id()
        if self.include_correlation_id and cid:
            formatted = f"[cid={cid[:8]}] {formatted}"
        
        # Finally redact the formatted message to catch any remaining sensitive data
        return self.filter.redact_string(formatted)


class JSONFormatter(logging.Formatter):
    """
    JSON-structured log formatter with sensitive data redaction.

    Produces machine-parseable JSON log lines with all fields explicit.
    """

    def __init__(self, redact_file_paths: bool = False, include_correlation_id: bool = True):
        super().__init__()
        self.filter = SensitiveDataFilter(redact_file_paths=redact_file_paths)
        self.include_correlation_id = include_correlation_id

    def format(self, record: logging.LogRecord) -> str:
        self.filter.filter(record)
        formatted = super().format(record)
        safe_msg = self.filter.redact_string(formatted)
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "message": safe_msg,
            "process": record.process,
        }
        cid = get_correlation_id()
        if self.include_correlation_id and cid:
            entry["correlation_id"] = cid
        return json.dumps(entry)


def setup_sensitive_data_logging(
    logger_name: Optional[str] = None,
    redact_file_paths: bool = False,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Set up logging with sensitive data redaction.
    
    Parameters
    ----------
    logger_name : str, optional
        Name of the logger to configure. If None, configures the root logger.
    redact_file_paths : bool
        If True, also redact file paths from logs.
    level : int
        Logging level to set (default: logging.INFO)
        
    Returns
    -------
    logging.Logger
        The configured logger
    """
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Add the sensitive data filter
    sensitive_filter = SensitiveDataFilter(redact_file_paths=redact_file_paths)
    logger.addFilter(sensitive_filter)
    
    # Set the logging level
    logger.setLevel(level)
    
    return logger


def mask_address(address: str, visible_chars: int = 6) -> str:
    """
    Mask an Ethereum address for safe logging.
    
    Parameters
    ----------
    address : str
        The Ethereum address to mask
    visible_chars : int
        Number of characters to show at the beginning and end
        
    Returns
    -------
    str
        Masked address in format 0x1234...5678
    """
    if not address or len(address) < visible_chars * 2:
        return "***REDACTED***"
    return f"{address[:visible_chars]}...{address[-4:]}"


def mask_transaction_hash(tx_hash: str, visible_chars: int = 10) -> str:
    """
    Mask a transaction hash for safe logging.
    
    Parameters
    ----------
    tx_hash : str
        The transaction hash to mask
    visible_chars : int
        Number of characters to show at the beginning and end
        
    Returns
    -------
    str
        Masked transaction hash
    """
    if not tx_hash or len(tx_hash) < visible_chars + 4:
        return "***REDACTED***"
    return f"{tx_hash[:visible_chars]}...{tx_hash[-4:]}"


# ── Performance tracking ─────────────────────────────────────────────────────

@contextmanager
def track_duration(
    operation: str,
    logger: logging.Logger,
    threshold_ms: float = 1000.0,
    level: int = logging.WARNING,
) -> Generator[None, None, None]:
    """
    Context manager that logs a warning if *operation* takes longer than *threshold_ms*.

    Parameters
    ----------
    operation : str
        Human-readable operation name for the log message.
    logger : logging.Logger
        Logger to write to.
    threshold_ms : float
        Duration threshold in milliseconds (default 1000 = 1 second).
    level : int
        Log level when threshold is exceeded (default WARNING).
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= threshold_ms:
            logger.log(level, "%s took %.0fms (threshold: %.0fms)", operation, elapsed_ms, threshold_ms)
        else:
            logger.log(logging.DEBUG, "%s took %.0fms", operation, elapsed_ms)


def mask_private_key(private_key: str, visible_chars: int = 8) -> str:
    """
    Mask a private key for safe logging.
    
    Parameters
    ----------
    private_key : str
        The private key to mask
    visible_chars : int
        Number of characters to show at the beginning
        
    Returns
    -------
    str
        Masked private key
    """
    if not private_key or len(private_key) < visible_chars:
        return "***REDACTED***"
    return f"{private_key[:visible_chars]}...REDACTED"
