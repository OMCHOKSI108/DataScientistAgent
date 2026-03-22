"""
Centralized logging configuration.
Sets up structured logging with JSON formatting and context tracking.
"""

import logging
import logging.handlers
import json
import time
import os
from datetime import datetime
from typing import Any, Dict
from pathlib import Path

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT_PLAIN = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_JSON = "%(message)s"


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_data.update(record.extra)
        
        return json.dumps(log_data, default=str)


class RequestContextFilter(logging.Filter):
    """Filter to add request context to logs."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add request context if available."""
        # This will be populated by middleware
        if not hasattr(record, "request_id"):
            record.request_id = "N/A"
        if not hasattr(record, "user_id"):
            record.user_id = "N/A"
        return True


def setup_logging():
    """Configure logging for the application."""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler (JSON)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    json_formatter = JSONFormatter(LOG_FORMAT_JSON)
    console_handler.setFormatter(json_formatter)
    console_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(console_handler)
    
    # File handler (JSON) - rotating
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOGS_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(json_formatter)
    file_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(file_handler)
    
    # Error file handler (JSON) - separate file for errors
    error_handler = logging.handlers.RotatingFileHandler(
        filename=LOGS_DIR / "error.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    error_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(error_handler)
    
    # Suppress verbose logs from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("supabase").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    request_id: str = None,
    user_id: str = None,
    extra: Dict[str, Any] = None,
):
    """
    Log a message with context.
    
    Args:
        logger: Logger instance
        level: Log level
        message: Log message
        request_id: Request ID for tracing
        user_id: User ID
        extra: Additional context data
    """
    log_data = {
        "request_id": request_id or "N/A",
        "user_id": user_id or "N/A",
    }
    
    if extra:
        log_data.update(extra)
    
    # Use a custom LogRecord
    record = logger.makeRecord(
        logger.name,
        level,
        "(unknown file)",
        0,
        message,
        args=(),
        exc_info=None,
    )
    record.extra = log_data
    logger.handle(record)


# Service-specific loggers
logger_auth = get_logger("backend.auth")
logger_chat = get_logger("backend.chat")
logger_upload = get_logger("backend.upload")
logger_agent = get_logger("backend.agent")
logger_rag = get_logger("backend.rag")
logger_tools = get_logger("backend.tools")
logger_db = get_logger("backend.db")


class ExecutionTimer:
    """Context manager for timing code execution."""
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
        self.duration = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        
        if exc_type is None:
            self.logger.info(
                f"Completed: {self.operation}",
                extra={
                    "operation": self.operation,
                    "duration_ms": round(self.duration * 1000, 2),
                }
            )
        else:
            self.logger.error(
                f"Failed: {self.operation}",
                extra={
                    "operation": self.operation,
                    "duration_ms": round(self.duration * 1000, 2),
                    "error": str(exc_val),
                },
                exc_info=(exc_type, exc_val, exc_tb),
            )
        
        return False
