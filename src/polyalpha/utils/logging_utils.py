"""
Logging utilities for polyalpha with sensitive data redaction.

This module provides custom logging filters and utilities to prevent
sensitive data from being exposed in log files.
"""

import logging
import re
from typing import Optional


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
        (r'0x[a-fA-F0-9]{40}', lambda m: f"{m.group(0)[:6]}...{m.group(0)[-4:]}"),
        # Transaction hashes (0x followed by 64 hex chars) - check this before private keys
        (r'0x[a-fA-F0-9]{64}', lambda m: f"{m.group(0)[:10]}...{m.group(0)[-4:]}"),
        # Private keys (long hex strings, typically 64+ chars, but not starting with 0x to avoid conflict)
        (r'\b[a-fA-F0-9]{64,}\b', lambda m: f"{m.group(0)[:8]}...REDACTED"),
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

    def __init__(self, fmt=None, datefmt=None, style='%', redact_file_paths=False):
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
        """
        super().__init__(fmt, datefmt, style)
        self.filter = SensitiveDataFilter(redact_file_paths=redact_file_paths)

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
        
        # Finally redact the formatted message to catch any remaining sensitive data
        return self.filter.redact_string(formatted)


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
