"""
Error handling utilities with retry logic and error taxonomy.
Provides standardized error responses and exponential backoff retries.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorType(Enum):
    """Error classification taxonomy."""
    VALIDATION = ("validation", 400)
    AUTHENTICATION = ("authentication", 401)
    AUTHORIZATION = ("authorization", 403)
    NOT_FOUND = ("not_found", 404)
    RATE_LIMIT = ("rate_limit", 429)
    CONFLICT = ("conflict", 409)
    UPSTREAM = ("upstream", 502)
    INTERNAL = ("internal", 500)
    SERVICE_UNAVAILABLE = ("service_unavailable", 503)
    TIMEOUT = ("timeout", 504)

    def __init__(self, code: str, status_code: int):
        self.code = code
        self.status_code = status_code


class AppError(Exception):
    """Base application error with error type."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.INTERNAL,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.error_type = error_type
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to API response dict."""
        return {
            "error": {
                "type": self.error_type.code,
                "message": self.message,
                "status": self.error_type.status_code,
                **(self.details if self.error_type != ErrorType.INTERNAL else {}),
            }
        }


class RetryConfig:
    """Configuration for retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 32.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            import random

            delay *= random.uniform(0.8, 1.0)

        return delay


def retry_on_error(
    config: Optional[RetryConfig] = None,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator to add retry logic with exponential backoff.

    Args:
        config: RetryConfig instance
        retryable_exceptions: Tuple of exceptions to retry on
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        retry_cfg = config or RetryConfig()

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_error = None

            for attempt in range(retry_cfg.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e

                    if attempt < retry_cfg.max_retries:
                        delay = retry_cfg.get_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{retry_cfg.max_retries} "
                            f"after {delay:.2f}s: {type(e).__name__}"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {retry_cfg.max_retries + 1} retries exhausted: {e}"
                        )

            raise last_error

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_error = None

            for attempt in range(retry_cfg.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e

                    if attempt < retry_cfg.max_retries:
                        delay = retry_cfg.get_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{retry_cfg.max_retries} "
                            f"after {delay:.2f}s: {type(e).__name__}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {retry_cfg.max_retries + 1} retries exhausted: {e}"
                        )

            raise last_error

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Default retry configurations
RETRY_EXTERNAL_API = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=10.0,
)

RETRY_DATABASE = RetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=5.0,
)

RETRY_EMBEDDING = RetryConfig(
    max_retries=2,
    base_delay=2.0,
    max_delay=15.0,
)


def classify_error(exception: Exception) -> ErrorType:
    """Classify an exception to an ErrorType."""
    exc_name = type(exception).__name__
    exc_msg = str(exception).lower()

    # Timeout errors
    if "timeout" in exc_msg or "timed out" in exc_msg:
        return ErrorType.TIMEOUT

    # Rate limit errors
    if "429" in exc_msg or "rate limit" in exc_msg or "quota" in exc_msg:
        return ErrorType.RATE_LIMIT

    # Authentication errors
    if "401" in exc_msg or "unauthorized" in exc_msg or "auth" in exc_msg:
        return ErrorType.AUTHENTICATION

    # Validation errors
    if "validation" in exc_msg or "invalid" in exc_msg:
        return ErrorType.VALIDATION

    # Upstream/service errors
    if any(code in exc_msg for code in ["502", "503", "504"]):
        if "502" in exc_msg:
            return ErrorType.UPSTREAM
        elif "503" in exc_msg:
            return ErrorType.SERVICE_UNAVAILABLE
        elif "504" in exc_msg:
            return ErrorType.TIMEOUT

    return ErrorType.INTERNAL


def safe_error_message(exception: Exception, reveal_details: bool = False) -> str:
    """
    Create a safe error message, hiding sensitive details.

    Args:
        exception: The exception
        reveal_details: Whether to reveal full details (for logging)

    Returns:
        Safe error message for user
    """
    if reveal_details:
        return str(exception)

    error_type = classify_error(exception)

    if error_type == ErrorType.TIMEOUT:
        return "Operation timed out. Please try again."
    elif error_type == ErrorType.RATE_LIMIT:
        return "Too many requests. Please wait a moment and try again."
    elif error_type == ErrorType.UPSTREAM:
        return "Service temporarily unavailable. Please try again later."
    elif error_type == ErrorType.SERVICE_UNAVAILABLE:
        return "Service is temporarily down. Please try again later."
    elif error_type == ErrorType.AUTHENTICATION:
        return "Authentication failed. Please log in again."
    else:
        return "An error occurred. Please try again."
