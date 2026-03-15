"""Tests for 2D export functionality."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from threedp.metadata import (
    compute_code_hash,
    create_metadata,
    embed_svg_metadata,
    extract_svg_metadata,
    embed_png_metadata,
    extract_png_metadata,
    embed_stl_metadata,
    extract_stl_metadata,
)
from threedp.tools.export_2d import (
    VALID_2D_VIEWS,
    export_view_to_svg,
    _rasterize_svg,
)


class TestMetadata:
    """Test metadata creation and embedding."""

    def test_compute_code_hash(self):
        """Test code hash computation."""
        code = "result = Box(10, 10, 10)"
        hash1 = compute_code_hash(code)
        hash2 = compute_code_hash(code)
        hash3 = compute_code_hash(code + " ")

        assert len(hash1) == 16
        assert hash1 == hash2  # Deterministic
        assert hash1 != hash3  # Different code = different hash

    def test_create_metadata(self):
        """Test metadata dictionary creation."""
        metadata = create_metadata(
            model_name="test_box",
            source_code="result = Box(10, 10, 10)",
            view_angle="top",
            export_format="svg",
        )

        assert metadata["model_name"] == "test_box"
        assert metadata["view_angle"] == "top"
        assert metadata["export_format"] == "svg"
        assert "creation_timestamp" in metadata
        assert "source_code_hash" in metadata
        assert "exporter_version" in metadata
        assert "dpi" not in metadata  # Not provided
        assert "compression" not in metadata

    def test_create_metadata_with_bitmap_options(self):
        """Test metadata with bitmap-specific options."""
        metadata = create_metadata(
            model_name="test_box",
            source_code="result = Box(10, 10, 10)",
            view_angle="isometric",
            export_format="png",
            dpi=300,
            compression="lossless",
        )

        assert metadata["dpi"] == 300
        assert metadata["compression"] == "lossless"


class TestSvgMetadata:
    """Test SVG metadata embedding and extraction."""

    def test_embed_and_extract_svg_metadata(self, tmp_path):
        """Test round-trip SVG metadata."""
        svg_path = tmp_path / "test.svg"
        svg_content = '''<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect width="100" height="100"/>
</svg>'''
        svg_path.write_text(svg_content)

        metadata = {
            "model_name": "test_model",
            "view_angle": "top",
            "export_format": "svg",
        }

        # Embed
        result = embed_svg_metadata(svg_path, metadata)
        assert result is True

        # Extract
        extracted = extract_svg_metadata(svg_path)
        assert extracted is not None
        assert extracted["model_name"] == "test_model"
        assert extracted["view_angle"] == "top"

    def test_extract_svg_metadata_not_found(self, tmp_path):
        """Test extraction when no metadata present."""
        svg_path = tmp_path / "test.svg"
        svg_path.write_text('<svg></svg>')

        extracted = extract_svg_metadata(svg_path)
        assert extracted is None


class TestPngMetadata:
    """Test PNG metadata embedding and extraction."""

    @pytest.mark.skipif(
        not __import__("importlib.util").util.find_spec("PIL"),
        reason="PIL not installed",
    )
    def test_embed_and_extract_png_metadata(self, tmp_path):
        """Test round-trip PNG metadata."""
        from PIL import Image

        png_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(png_path)

        metadata = {
            "model_name": "test_model",
            "view_angle": "isometric",
            "export_format": "png",
            "dpi": 150,
        }

        # Embed
        result = embed_png_metadata(png_path, metadata)
        assert result is True

        # Extract
        extracted = extract_png_metadata(png_path)
        assert extracted is not None
        assert extracted["model_name"] == "test_model"
        assert extracted["dpi"] == 150


class TestStlMetadata:
    """Test STL metadata embedding and extraction."""

    def test_embed_and_extract_binary_stl_metadata(self, tmp_path):
        """Test round-trip binary STL metadata."""
        stl_path = tmp_path / "test.stl"
        # Binary STL header + minimal triangle
        header = b" " * 80  # 80-byte header
        triangles = (1).to_bytes(4, 'little')  # 1 triangle
        # Triangle: normal(3f), vertices(9f), attribute(2b)
        triangle_data = b"\x00" * (12 * 4 + 2)
        stl_path.write_bytes(header + triangles + triangle_data)

        metadata = {
            "model_name": "test_model",
            "view_angle": "3d",
            "export_format": "stl",
        }

        # Embed
        result = embed_stl_metadata(stl_path, metadata)
        assert result is True

        # Extract
        extracted = extract_stl_metadata(stl_path)
        assert extracted is not None
        assert extracted["model_name"] == "test_model"

    def test_embed_and_extract_ascii_stl_metadata(self, tmp_path):
        """Test round-trip ASCII STL metadata."""
        stl_path = tmp_path / "test.stl"
        stl_content = """solid test
  facet normal 0 0 0
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid test"""
        stl_path.write_text(stl_content)

        metadata = {
            "model_name": "ascii_model",
            "view_angle": "3d",
            "export_format": "stl",
        }

        # Embed
        result = embed_stl_metadata(stl_path, metadata)
        assert result is True

        # Extract
        extracted = extract_stl_metadata(stl_path)
        assert extracted is not None
        assert extracted["model_name"] == "ascii_model"


class TestExport2DViews:
    """Test 2D view export functionality."""

    def test_valid_2d_views(self):
        """Test that all expected views are valid."""
        expected_views = {
            "top", "bottom", "front", "back",
            "left", "right", "isometric", "dimetric", "trimetric", "iso"
        }
        assert VALID_2D_VIEWS == expected_views

    @patch("threedp.tools.export_2d.log")
    def test_export_view_to_svg_logs_on_failure(self, mock_log, tmp_path):
        """Test SVG export logs error when build123d is not available."""
        mock_shape = MagicMock()
        output_path = tmp_path / "test_top.svg"
        metadata = {"model_name": "test", "view_angle": "top"}

        # When build123d is not available, export should fail gracefully
        result = export_view_to_svg(
            mock_shape, output_path, (0, 0, 1), "top", metadata
        )

        # Should return False when build123d.ExportSVG fails (ImportError)
        assert result is False
        mock_log.error.assert_called_once()


class TestExport2DToolRegistration:
    """Test the export_2d_view tool registration."""

    @patch("threedp.tools.export_2d.log")
    @patch("threedp.tools.export_2d.new_request_id")
    @patch("threedp.tools.export_2d.log_tool_call")
    def test_export_2d_view_invalid_view(self, mock_log_tool, mock_rid, mock_log):
        """Test export_2d_view with invalid view name."""
        from threedp.tools.export_2d import register_tools

        mock_mcp = MagicMock()
        mock_store = MagicMock()
        mock_config = MagicMock()

        # Capture the registered tool
        registered_tools = {}
        def capture_tool(fn):
            registered_tools[fn.__name__] = fn
            return fn
        mock_mcp.tool = lambda: capture_tool

        register_tools(mock_mcp, mock_store, mock_config)

        # The tool should reject invalid views
        result = registered_tools["export_2d_view"]("test", "invalid_view")
        data = json.loads(result)

        assert data["success"] is False
        assert "Invalid view" in data["error"]

    @patch("threedp.tools.export_2d.log")
    @patch("threedp.tools.export_2d.new_request_id")
    @patch("threedp.tools.export_2d.log_tool_call")
    def test_export_2d_view_invalid_format(self, mock_log_tool, mock_rid, mock_log):
        """Test export_2d_view with invalid format."""
        from threedp.tools.export_2d import register_tools

        mock_mcp = MagicMock()
        mock_store = MagicMock()
        mock_config = MagicMock()

        registered_tools = {}
        def capture_tool(fn):
            registered_tools[fn.__name__] = fn
            return fn
        mock_mcp.tool = lambda: capture_tool

        register_tools(mock_mcp, mock_store, mock_config)

        result = registered_tools["export_2d_view"]("test", "top", "pdf")
        data = json.loads(result)

        assert data["success"] is False
        assert "Invalid format" in data["error"]
