"""
Request tracking and logging middleware.
Adds request ID, latency measurement, and context to all requests.
"""

import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from backend.logging_config import logger_chat, log_with_context


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track requests and add logging context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and track metrics."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Extract client IP
        client_ip = "unknown"
        if request.client:
            client_ip = request.client.host

        # Store request ID in scope for later use
        request.scope["request_id"] = request_id
        request.scope["start_time"] = start_time

        # Log request start
        log_with_context(
            logger_chat,
            20,  # INFO level
            f"Request started: {request.method} {request.url.path}",
            request_id=request_id,
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
            },
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Log request completion
            log_with_context(
                logger_chat,
                20,  # INFO level
                f"Request completed: {request.method} {request.url.path} -> {response.status_code}",
                request_id=request_id,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "client_ip": client_ip,
                },
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000

            # Log error
            log_with_context(
                logger_chat,
                40,  # ERROR level
                f"Request failed: {request.method} {request.url.path}",
                request_id=request_id,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "latency_ms": round(latency_ms, 2),
                    "error": str(exc),
                    "client_ip": client_ip,
                },
            )

            raise
