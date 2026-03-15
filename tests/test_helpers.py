"""Tests for helpers module."""

from __future__ import annotations

import json

import pytest

from threedp.helpers import error_response, success_response
from threedp.logging_config import new_request_id


class TestErrorResponse:
    """Test error_response helper."""

    def test_basic_error(self) -> None:
        """Test basic error response."""
        result = json.loads(error_response(ValueError("test error")))
        assert result["success"] is False
        assert result["error"] == "test error"
        assert "traceback" in result

    def test_error_without_traceback(self) -> None:
        """Test error response without traceback."""
        result = json.loads(error_response(RuntimeError("oops"), include_traceback=False))
        assert result["success"] is False
        assert result["error"] == "oops"
        assert "traceback" not in result


class TestSuccessResponse:
    """Test success_response helper."""

    def test_basic_success(self) -> None:
        """Test basic success response."""
        result = json.loads(success_response({"name": "box", "volume": 100}))
        assert result["success"] is True
        assert result["name"] == "box"
        assert result["volume"] == 100

    def test_overwrites_success_field(self) -> None:
        """Test that success=True is always set."""
        result = json.loads(success_response({"success": False, "data": "value"}))
        assert result["success"] is True


class TestRequestId:
    """Test request ID generation."""

    def test_generates_string(self) -> None:
        """Test that request ID is a string."""
        rid = new_request_id()
        assert isinstance(rid, str)

    def test_length(self) -> None:
        """Test request ID is 8 hex chars."""
        rid = new_request_id()
        assert len(rid) == 8

    def test_unique(self) -> None:
        """Test that request IDs are unique."""
        ids = {new_request_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_hex_only(self) -> None:
        """Test that request ID contains only hex chars."""
        rid = new_request_id()
        int(rid, 16)  # Raises ValueError if not valid hex


class TestFileHelpers:
    """Test file path helpers."""

    def test_model_dir_creates_directory(self, tmp_path) -> None:
        """Test model_dir creates the output directory."""
        from threedp.helpers import model_dir
        d = model_dir(tmp_path, "my_model")
        assert d.exists()
        assert d.is_dir()
        assert d.name == "my_model"

    def test_file_size_str(self, tmp_path) -> None:
        """Test file_size_str formatting."""
        from threedp.helpers import file_size_str

        # Create test files
        small = tmp_path / "small.txt"
        small.write_bytes(b"x" * 500)
        assert "500 B" in file_size_str(small)

        medium = tmp_path / "medium.bin"
        medium.write_bytes(b"x" * (2 * 1024))
        assert "KB" in file_size_str(medium)
