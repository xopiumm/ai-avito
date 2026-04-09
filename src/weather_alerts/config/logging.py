"""Structured logging configuration for Weather Alerts.

Provides JSON-formatted structured logging with:
- Automatic correlation ID injection into logs
- Request/response metadata tracking
- Async context propagation (asyncio contextvars)
- Integration with Celery worker tasks
- Development (human-readable) and production (JSON) formats

Architecture:
- LogRecord factory: Enriches each log record with context (correlation_id, user_id, etc.)
- JSON Formatter: Encodes logs as JSON for machine parsing
- Handler configuration: Console and file handlers with appropriate formatting
- Context management: Thread-safe and async-safe via contextvars

Usage:

    from src.weather_alerts.config.logging import get_logger, set_correlation_id
    
    logger = get_logger(__name__)
    
    # Set correlation ID (usually done by middleware)
    set_correlation_id("req_123abc")
    
    # Logs will include correlation_id automatically
    logger.info("Processing notification", extra={"user_id": "user_1"})
    # Output: {"timestamp": "...", "level": "INFO", "correlation_id": "req_123abc", "user_id": "user_1", ...}
    
    # For Celery tasks
    set_correlation_id("task_456def")
    logger.info("Task started")
"""

import logging
import logging.config
import json
import sys
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from contextvars import ContextVar

from src.weather_alerts.config.settings import get_settings

# Context variables for async-safe correlation ID and request tracking
_correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)
_user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_request_path_var: ContextVar[Optional[str]] = ContextVar("request_path", default=None)


# ============================================================================
# CONTEXT MANAGEMENT
# ============================================================================


def set_correlation_id(correlation_id: Optional[str]) -> None:
    """Set the correlation ID for the current async context.
    
    This ID will be automatically included in all log records within this context.
    Typically set by request middleware for HTTP requests and task wrapper for Celery tasks.
    
    Args:
        correlation_id: Unique request/task identifier or None to clear
        
    Example:
        set_correlation_id("req_550e8400-e29b-41d4-a716-446655440000")
    """
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from the async context.
    
    Returns:
        Current correlation ID or None if not set
    """
    return _correlation_id_var.get()


def set_user_id(user_id: Optional[str]) -> None:
    """Set the user ID for the current async context.
    
    Included in logs for tracing user-specific actions.
    
    Args:
        user_id: User identifier or None to clear
    """
    _user_id_var.set(user_id)


def get_user_id() -> Optional[str]:
    """Get the current user ID from the async context."""
    return _user_id_var.get()


def set_request_path(path: Optional[str]) -> None:
    """Set the HTTP request path for the current context."""
    _request_path_var.set(path)


def get_request_path() -> Optional[str]:
    """Get the current request path."""
    return _request_path_var.get()


def clear_context() -> None:
    """Clear all context variables. Useful for task completion or error handling."""
    _correlation_id_var.set(None)
    _user_id_var.set(None)
    _request_path_var.set(None)


# ============================================================================
# LOGGING FORMATTERS
# ============================================================================


class JSONFormatter(logging.Formatter):
    """JSON-based structured logging formatter.
    
    Converts log records to JSON for:
    - Machine parsing and log aggregation (ELK, CloudWatch, etc.)
    - Structured querying and filtering
    - Correlation tracing across request → worker → external service chain
    
    Output format:
    {
        "timestamp": "2026-04-09T10:30:45.123Z",
        "level": "INFO",
        "logger": "src.weather_alerts.services.notification_service",
        "message": "Processing notification",
        "correlation_id": "req_550e8400...",
        "user_id": "user_123",
        "subscription_id": "sub_456",
        ...extra fields...
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON line.
        
        Args:
            record: LogRecord instance from logger
            
        Returns:
            JSON string with all relevant context
        """
        # Build base object
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add correlation context if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_obj["correlation_id"] = correlation_id
        
        user_id = get_user_id()
        if user_id:
            log_obj["user_id"] = user_id
        
        request_path = get_request_path()
        if request_path:
            log_obj["request_path"] = request_path
        
        # Add any extra fields from "extra" kwarg
        if record.args:
            # For %-formatted messages, args might be present
            pass  # getMessage() already handles this
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }
            # Format the full traceback using formatException
            traceback = self.formatException(record.exc_info)
            if traceback:
                log_obj["exception"]["traceback"] = traceback
        
        # Add all extra fields (dict-like LogRecord attributes)
        # LogRecord has standard attrs like 'name', 'msg', 'args', 'created', etc.
        # We add non-standard ones from record.__dict__
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
            "processName", "relativeCreated", "thread", "threadName", "exc_info",
            "exc_text", "stack_info", "getMessage", "asctime"
        }
        
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # Skip if already in log_obj
                if key not in log_obj and value is not None:
                    log_obj[key] = value
        
        # Serialize to JSON
        return json.dumps(log_obj, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development.
    
    Uses ANSI color codes for colored console output (not in production).
    Format: [TIME] LEVEL logger: message (context)
    """
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        """Format record with colors and context."""
        # Color codes
        level_color = self.COLORS.get(record.levelname, "")
        
        # Base format
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%H:%M:%S.%f"
        )[:-3]
        message = record.getMessage()
        
        # Build context string
        context_parts = []
        if correlation_id := get_correlation_id():
            context_parts.append(f"corr={correlation_id[:8]}")
        if user_id := get_user_id():
            context_parts.append(f"user={user_id}")
        if request_path := get_request_path():
            context_parts.append(f"path={request_path}")
        
        context_str = f" ({', '.join(context_parts)})" if context_parts else ""
        
        # Format with extra fields
        extra_parts = []
        for key, value in record.__dict__.items():
            if not key.startswith("_") and key not in {
                "name", "msg", "args", "created", "filename", "funcName", "levelname",
                "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
                "processName", "relativeCreated", "thread", "threadName", "exc_info",
                "exc_text", "stack_info", "getMessage", "asctime", "taskName"
            }:
                extra_parts.append(f"{key}={value}")
        
        extra_str = f" [{', '.join(extra_parts)}]" if extra_parts else ""
        
        result = (
            f"[{timestamp}] {level_color}{record.levelname:8}{self.RESET} "
            f"{record.name}: {message}{context_str}{extra_str}"
        )
        
        # Add exception info if present
        if record.exc_info:
            result += f"\n{self.format_exception(record.exc_info)}"
        
        return result
    
    @staticmethod
    def format_exception(exc_info) -> str:
        """Format exception traceback."""
        import traceback
        return "".join(traceback.format_exception(*exc_info))


# ============================================================================
# LOGGER FACTORY
# ============================================================================


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with structured logging configured.
    
    All loggers created via this factory will:
    - Share the same handler configuration
    - Include correlation ID and other context in logs
    - Format based on environment (JSON for production, human-readable for dev)
    
    Args:
        name: Logger name (typically __name__ in calling module)
        
    Returns:
        logging.Logger instance
        
    Example:
        from src.weather_alerts.config.logging import get_logger
        logger = get_logger(__name__)
        logger.info("User created", extra={"user_id": "123"})
    """
    logger = logging.getLogger(name)
    return logger


def configure_logging() -> None:
    """Configure logging system for application.
    
    Call once at application startup. Sets up:
    - Root logger level based on environment
    - Console handler with appropriate formatter
    - File handler for persistent logs (production)
    - Disables verbose third-party loggers (uvicorn, sqlalchemy, etc.)
    
    Should be called in main.py create_app() or worker main.
    """
    settings = get_settings()
    
    # Determine log level
    log_level = getattr(logging, settings.api.log_level, logging.INFO)
    
    # Choose formatter based on environment
    is_production = settings.environment == "production"
    formatter_class = JSONFormatter if is_production else HumanReadableFormatter
    formatter = formatter_class()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    
    # File handler for production
    if is_production:
        file_handler = logging.FileHandler("weather_alerts.log")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.WARNING)
        root_logger.addHandler(file_handler)
    
    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


# ============================================================================
# HELPER FUNCTION FOR ADDING CONTEXT TO EXTRA
# ============================================================================


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **context: Any,
) -> None:
    """Log message with automatic correlation ID and context fields.
    
    Convenience wrapper that adds correlation_id and other context vars to extra.
    
    Args:
        logger: Logger instance
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        **context: Additional fields to include in log
        
    Example:
        from src.weather_alerts.config.logging import get_logger, log_with_context
        
        logger = get_logger(__name__)
        log_with_context(logger, "INFO", "Task completed", task_id="t123", duration=5.2)
        # Output: {"timestamp": "...", "level": "INFO", "message": "Task completed",
        #          "task_id": "t123", "duration": 5.2, "correlation_id": "..."}
    """
    extra_data = dict(context)
    log_func = getattr(logger, level.lower())
    log_func(message, extra=extra_data)
