"""Tests for logging_config module."""

from __future__ import annotations

import json
import logging
import re
from io import StringIO

import pytest

from threedp.logging_config import JsonFormatter, new_request_id, log_tool_call


class TestJsonFormatter:
    """Test JSON log formatter."""

    def test_basic_format(self) -> None:
        """Test basic JSON output."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed

    def test_extra_fields(self) -> None:
        """Test that extra fields are included."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="tool call", args=(), exc_info=None,
        )
        record.request_id = "abc123"
        record.tool = "create_model"
        record.duration_ms = 42.5

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["request_id"] == "abc123"
        assert parsed["tool"] == "create_model"
        assert parsed["duration_ms"] == 42.5

    def test_truncates_long_args(self) -> None:
        """Test that long string args are truncated."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        record.tool_args = {"code": "x" * 500}

        output = formatter.format(record)
        parsed = json.loads(output)
        assert "200" in parsed["tool_args"]["code"] or "500 chars" in parsed["tool_args"]["code"]

    def test_exception_included(self) -> None:
        """Test that exceptions are included in output."""
        formatter = JsonFormatter()
        try:
            raise ValueError("test exception")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="", lineno=0,
                msg="error", args=(), exc_info=sys.exc_info(),
            )

        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]


class TestNewRequestId:
    """Test request ID generation."""

    def test_returns_hex_string(self) -> None:
        """Test that ID is a hex string of length 8."""
        rid = new_request_id()
        assert isinstance(rid, str)
        assert len(rid) == 8
        int(rid, 16)  # Should not raise

    def test_uniqueness(self) -> None:
        """Test that IDs are unique across many calls."""
        ids = set()
        for _ in range(200):
            ids.add(new_request_id())
        assert len(ids) == 200


class TestLogToolCall:
    """Test log_tool_call context manager."""

    def test_logs_start_and_complete(self, caplog) -> None:
        """Test that start and complete are both logged."""
        logger = logging.getLogger("test_tool_call")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        stream = handler.stream
        with log_tool_call(logger, "test_tool", {"arg1": "value1"}, "req001"):
            pass

        output = stream.getvalue()
        lines = [line for line in output.strip().split("\n") if line]

        # Should have at least 2 log lines (start + complete)
        assert len(lines) >= 2

        messages = [json.loads(line)["message"] for line in lines]
        assert "tool_invocation_start" in messages
        assert "tool_invocation_complete" in messages

    def test_logs_error_on_exception(self, caplog) -> None:
        """Test that errors are logged when tool raises."""
        logger = logging.getLogger("test_tool_err")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        stream = handler.stream
        with pytest.raises(RuntimeError, match="boom"):
            with log_tool_call(logger, "failing_tool", {}, "req002"):
                raise RuntimeError("boom")

        output = stream.getvalue()
        lines = [line for line in output.strip().split("\n") if line]
        messages = [json.loads(line)["message"] for line in lines]
        assert "tool_invocation_failed" in messages

    def test_request_id_propagation(self) -> None:
        """Test that request ID is consistent across log entries."""
        logger = logging.getLogger("test_tool_id")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        stream = handler.stream
        with log_tool_call(logger, "id_test", {}, "xyz789"):
            pass

        output = stream.getvalue()
        lines = [line for line in output.strip().split("\n") if line]
        for line in lines:
            parsed = json.loads(line)
            if "request_id" in parsed:
                assert parsed["request_id"] == "xyz789"
