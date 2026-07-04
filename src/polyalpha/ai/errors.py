"""
AI-specific exceptions for OpenRouter integration.
"""


class AIError(Exception):
    """Base exception for all AI-related errors."""
    pass


class AIAuthenticationError(AIError):
    """Raised when API key is invalid or authentication fails."""
    pass


class AIModelNotFoundError(AIError):
    """Raised when the requested model is not available."""
    pass


class AIQuotaExceededError(AIError):
    """Raised when rate limit or quota is exceeded."""
    pass


class AIResponseError(AIError):
    """Raised when the response is malformed or invalid."""
    pass


class AITimeoutError(AIError):
    """Raised when the request times out."""
    pass


class AIConnectionError(AIError):
    """Raised when connection to OpenRouter fails."""
    pass
