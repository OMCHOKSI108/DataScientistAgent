"""
Rate limiting middleware using in-memory sliding window counters.
Implements both per-user and per-IP rate limits.
"""

import time
import threading
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from backend.logging_config import logger_chat

# In-memory rate limit storage
# Structure: {key: [(timestamp, count), ...]}
_rate_limit_store: Dict[str, list] = defaultdict(list)
_rate_limit_lock = threading.RLock()

# Rate limit configuration (requests per window)
RATE_LIMITS = {
    "auth": (10, 3600),  # 10 requests per hour
    "chat": (30, 3600),  # 30 requests per hour per user
    "upload": (20, 3600),  # 20 uploads per hour per user
    "global_ip": (100, 3600),  # 100 requests per hour per IP
}


def get_client_ip(request: Request) -> str:
    """Extract client IP, accounting for proxies."""
    if request.client:
        return request.client.host
    return "unknown"


def is_rate_limited(
    key: str,
    limit: int,
    window: int,
) -> Tuple[bool, Dict]:
    """
    Check if a request exceeds rate limit using sliding window.

    Args:
        key: Rate limit key (user_id, IP, etc.)
        limit: Max requests allowed
        window: Time window in seconds

    Returns:
        (is_limited, metadata)
    """
    now = time.time()
    window_start = now - window

    with _rate_limit_lock:
        # Get or create counter list
        if key not in _rate_limit_store:
            _rate_limit_store[key] = []

        # Remove expired entries
        _rate_limit_store[key] = [
            ts for ts in _rate_limit_store[key] if ts > window_start
        ]

        current_count = len(_rate_limit_store[key])

        if current_count >= limit:
            # Calculate retry_after
            oldest_ts = _rate_limit_store[key][0]
            retry_after = int(window + 1 - (now - oldest_ts))

            logger_chat.warning(
                f"Rate limit exceeded for {key}: {current_count}/{limit}"
            )

            return True, {
                "limit": limit,
                "window": window,
                "current": current_count,
                "retry_after": retry_after,
            }

        # Add current request
        _rate_limit_store[key].append(now)

        return False, {
            "limit": limit,
            "remaining": limit - current_count - 1,
            "window": window,
        }


def cleanup_old_entries():
    """Periodic cleanup of expired entries."""
    now = time.time()
    with _rate_limit_lock:
        for key in list(_rate_limit_store.keys()):
            # Keep entries from last 24 hours
            _rate_limit_store[key] = [
                ts for ts in _rate_limit_store[key] if now - ts < 86400
            ]
            if not _rate_limit_store[key]:
                del _rate_limit_store[key]


class RateLimitError(HTTPException):
    """Rate limit exceeded error."""

    def __init__(self, retry_after: int):
        self.status_code = 429
        self.detail = "Too many requests. Please try again later."
        self.retry_after = retry_after
        self.headers = {"Retry-After": str(retry_after)}


def rate_limit_auth(request: Request):
    """Rate limit for authentication endpoints."""
    ip = get_client_ip(request)
    is_limited, _ = is_rate_limited(f"auth:{ip}", *RATE_LIMITS["auth"])

    if is_limited:
        raise RateLimitError(retry_after=60)


def rate_limit_chat(request: Request, user_id: str):
    """Rate limit for chat endpoints (per user)."""
    is_limited, metadata = is_rate_limited(
        f"chat:{user_id}",
        *RATE_LIMITS["chat"],
    )

    if is_limited:
        raise RateLimitError(retry_after=metadata["retry_after"])


def rate_limit_upload(request: Request, user_id: str):
    """Rate limit for upload endpoints (per user)."""
    is_limited, metadata = is_rate_limited(
        f"upload:{user_id}",
        *RATE_LIMITS["upload"],
    )

    if is_limited:
        raise RateLimitError(retry_after=metadata["retry_after"])


def rate_limit_global_ip(request: Request):
    """Global rate limit per IP."""
    ip = get_client_ip(request)
    is_limited, metadata = is_rate_limited(
        f"global:{ip}",
        *RATE_LIMITS["global_ip"],
    )

    if is_limited:
        logger_chat.warning(f"Global rate limit exceeded for IP {ip}")
        raise RateLimitError(retry_after=metadata["retry_after"])
