"""Structured logging configuration for the 3DP CAD server.

Provides JSON-formatted logs to both stdout and rotating log files,
with request correlation, timing, and sanitized argument logging.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# ── Log Directory ────────────────────────────────────────────────────────────

_LOG_DIR = Path(os.environ.get("THREEDP_LOG_DIR", Path(__file__).parent.parent.parent / "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_LEVEL = os.environ.get("THREEDP_LOG_LEVEL", "INFO").upper()

# ── JSON Formatter ───────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from LogRecord
        for key in ("request_id", "tool", "duration_ms", "success", "args", "model_name", "error"):
            if hasattr(record, key):
                value = getattr(record, key)
                if key == "args" and isinstance(value, dict):
                    # Sanitize: truncate large values, redact sensitive
                    value = {k: _sanitize_arg(v) for k, v in value.items()}
                log_entry[key] = value

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def _sanitize_arg(value: Any) -> Any:
    """Sanitize a log argument — truncate large strings, preserve small values."""
    if isinstance(value, str) and len(value) > 200:
        return f"{value[:200]}... ({len(value)} chars)"
    return value


# ── Logger Setup ─────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """Configure and return the application logger.

    Sets up:
    - Console handler with JSON format (stdout)
    - Rotating file handler (logs/server.log, 10MB max, 5 backups)
    """
    logger = logging.getLogger("threedp")
    logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    logger.handlers.clear()

    formatter = JsonFormatter()

    # Console handler (stdout for MCP stdio compatibility — use stderr)
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler
    log_file = _LOG_DIR / "server.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info("logging_initialized", extra={"log_file": str(log_file), "level": _LOG_LEVEL})
    return logger


# ── Request Correlation ──────────────────────────────────────────────────────

def new_request_id() -> str:
    """Generate a short unique request ID for tracing."""
    return uuid.uuid4().hex[:8]


@contextmanager
def log_tool_call(
    logger: logging.Logger,
    tool_name: str,
    args: dict[str, Any],
    request_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager for logging a tool call with timing and error capture.

    Usage:
        with log_tool_call(logger, "create_model", {"name": name, "code_len": len(code)}) as ctx:
            result = do_work()
            ctx["result_summary"] = "success"
    """
    rid = request_id or new_request_id()
    start = time.monotonic()

    logger.debug(
        "tool_invocation_start",
        extra={
            "request_id": rid,
            "tool": tool_name,
            "args": args,
        },
    )

    ctx: dict[str, Any] = {"request_id": rid}

    try:
        yield ctx
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "tool_invocation_complete",
            extra={
                "request_id": rid,
                "tool": tool_name,
                "duration_ms": elapsed_ms,
                "success": True,
            },
        )
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error(
            "tool_invocation_failed",
            extra={
                "request_id": rid,
                "tool": tool_name,
                "duration_ms": elapsed_ms,
                "success": False,
                "error": str(e),
            },
            exc_info=True,
        )
        raise


# ── Module-level logger ──────────────────────────────────────────────────────

_log = setup_logging()


def get_logger() -> logging.Logger:
    """Return the application logger."""
    return _log
