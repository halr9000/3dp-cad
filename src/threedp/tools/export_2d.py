"""2D view export tool: Export 2D model views from 3D models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from threedp.config import ServerConfig
from threedp.constants import VIEW_DIRECTIONS
from threedp.helpers import error_response, model_dir
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.metadata import (
    create_metadata,
    embed_svg_metadata,
    embed_png_metadata,
    embed_webp_metadata,
)
from threedp.model_store import ModelStore

log = get_logger()

# ── Valid Views for 2D Export ────────────────────────────────────────────────

VALID_2D_VIEWS = frozenset([
    "top", "bottom", "front", "back", "left", "right",
    "isometric", "dimetric", "trimetric", "iso"
])

# ── Export Functions ─────────────────────────────────────────────────────────

def _project_shape_to_2d(shape: Any, view_direction: tuple[float, float, float]) -> Any:
    """Project a 3D shape to 2D by sectioning along the view direction.
    
    Returns a list of Faces representing the projection.
    """
    from build123d import Plane, section, Vector
    import math
    
    dx, dy, dz = view_direction
    
    # Normalize the direction
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length > 0:
        dx, dy, dz = dx/length, dy/length, dz/length
    
    # Create a plane perpendicular to the view direction
    # Default plane is XY, we need to orient it to face the view direction
    if abs(dz) > 0.99:  # Top or bottom view
        plane = Plane.XY.offset(shape.center().Z)
    elif abs(dy) > 0.99:  # Front or back view
        plane = Plane.XZ.offset(shape.center().Y)
    elif abs(dx) > 0.99:  # Left or right view
        plane = Plane.YZ.offset(shape.center().X)
    else:  # Isometric - use XY with offset
        plane = Plane.XY.offset(shape.center().Z)
    
    # Get the cross-section of the shape at the center plane
    result = section(shape, plane)
    return result


def export_view_to_svg(
    shape: Any,
    output_path: Path,
    view_direction: tuple[float, float, float],
    view_name: str,
    metadata: dict[str, Any],
    scale: float = 1.0,
) -> bool:
    """Export a single view to SVG format.
    
    Args:
        shape: build123d Shape object
        output_path: Path to save the SVG
        view_direction: (x, y, z) vector for view direction
        view_name: Name of the view for layer naming
        metadata: Metadata dictionary to embed
        scale: SVG scale factor
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from build123d import ExportSVG
        
        # Project to 2D
        projected = _project_shape_to_2d(shape, view_direction)
        
        exporter = ExportSVG(scale=scale)
        layer_name = f"view_{view_name}"
        exporter.add_layer(layer_name)
        exporter.add_shape(projected, layer=layer_name)
        
        exporter.write(str(output_path))
        
        # Embed metadata
        embed_svg_metadata(output_path, metadata)
        
        return True
        
    except Exception as e:
        log.error("svg_export_failed", extra={"path": str(output_path), "error": str(e)})
        return False


def export_view_to_png(
    shape: Any,
    output_path: Path,
    view_direction: tuple[float, float, float],
    metadata: dict[str, Any],
    dpi: int = 150,
    compression: str = "lossless",
) -> bool:
    """Export a single view to PNG format.
    
    Args:
        shape: build123d Shape object
        output_path: Path to save the PNG
        view_direction: (x, y, z) vector for view direction
        metadata: Metadata dictionary to embed
        dpi: Resolution in dots per inch
        compression: "lossless" or "lossy"
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # First export to SVG, then rasterize
        from build123d import ExportSVG
        
        temp_svg = output_path.with_suffix('.temp.svg')
        
        # Project to 2D
        projected = _project_shape_to_2d(shape, view_direction)
        
        exporter = ExportSVG(scale=1.0)
        exporter.add_layer("view")
        exporter.add_shape(projected, layer="view")
        exporter.write(str(temp_svg))
        
        # Rasterize SVG to PNG using available libraries
        success = _rasterize_svg(temp_svg, output_path, dpi, compression)
        
        # Cleanup temp SVG
        if temp_svg.exists():
            temp_svg.unlink()
        
        if success:
            # Embed metadata
            embed_png_metadata(output_path, metadata)
            return True
        return False
        
    except Exception as e:
        log.error("png_export_failed", extra={"path": str(output_path), "error": str(e)})
        return False


def export_view_to_webp(
    shape: Any,
    output_path: Path,
    view_direction: tuple[float, float, float],
    metadata: dict[str, Any],
    dpi: int = 150,
    compression: str = "lossless",
) -> bool:
    """Export a single view to WebP format.
    
    Args:
        shape: build123d Shape object
        output_path: Path to save the WebP
        view_direction: (x, y, z) vector for view direction
        metadata: Metadata dictionary to embed
        dpi: Resolution in dots per inch
        compression: "lossless" or "lossy"
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from build123d import ExportSVG
        
        temp_svg = output_path.with_suffix('.temp.svg')
        
        # Project to 2D
        projected = _project_shape_to_2d(shape, view_direction)
        
        exporter = ExportSVG(scale=1.0)
        exporter.add_layer("view")
        exporter.add_shape(projected, layer="view")
        exporter.write(str(temp_svg))
        
        # Rasterize SVG to WebP
        success = _rasterize_svg_to_webp(temp_svg, output_path, dpi, compression)
        
        # Cleanup
        if temp_svg.exists():
            temp_svg.unlink()
        
        if success:
            embed_webp_metadata(output_path, metadata)
            return True
        return False
        
    except Exception as e:
        log.error("webp_export_failed", extra={"path": str(output_path), "error": str(e)})
        return False


def _rasterize_svg(svg_path: Path, png_path: Path, dpi: int, compression: str) -> bool:
    """Rasterize SVG to PNG using available libraries."""
    # Try cairosvg first (best quality)
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), dpi=dpi)
        return True
    except ImportError:
        pass
    
    # Try svglib + reportlab + PIL
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        from PIL import Image
        
        drawing = svg2rlg(str(svg_path))
        # Scale based on DPI (default is 72)
        scale = dpi / 72.0
        drawing.width = drawing.width * scale
        drawing.height = drawing.height * scale
        drawing.scale(scale, scale)
        
        # Render to PIL Image
        pil_img = renderPM.drawToPIL(drawing, dpi=dpi)
        
        # Save with appropriate compression
        if compression == "lossy":
            pil_img.save(png_path, format="PNG", compress_level=6)
        else:
            pil_img.save(png_path, format="PNG", compress_level=9)
        
        return True
    except ImportError:
        pass
    
    # Try Inkscape as fallback
    try:
        import subprocess
        width_px = int(1000 * dpi / 150)  # Scale based on DPI
        cmd = [
            "inkscape",
            str(svg_path),
            "--export-type=png",
            f"--export-filename={png_path}",
            f"--export-dpi={dpi}",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except (ImportError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    log.error("no_rasterizer_available", extra={"svg": str(svg_path)})
    return False


def _rasterize_svg_to_webp(svg_path: Path, webp_path: Path, dpi: int, compression: str) -> bool:
    """Rasterize SVG to WebP using available libraries."""
    # Try PIL/Pillow first
    try:
        from PIL import Image
        
        # First convert to PNG in memory, then to WebP
        import io
        
        # Use cairosvg if available for best quality
        try:
            import cairosvg
            png_data = cairosvg.svg2png(url=str(svg_path), dpi=dpi)
            img = Image.open(io.BytesIO(png_data))
        except ImportError:
            # Fallback to svglib
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPM
                
                drawing = svg2rlg(str(svg_path))
                scale = dpi / 72.0
                drawing.width = drawing.width * scale
                drawing.height = drawing.height * scale
                drawing.scale(scale, scale)
                img = renderPM.drawToPIL(drawing, dpi=dpi)
            except ImportError:
                return False
        
        # Save as WebP
        quality = 85 if compression == "lossy" else 100
        method = 6 if compression == "lossless" else 4
        img.save(webp_path, format="WEBP", quality=quality, method=method)
        return True
        
    except ImportError:
        pass
    
    log.error("no_webp_encoder_available", extra={"svg": str(svg_path)})
    return False


# ── Tool Registration ─────────────────────────────────────────────────────────

def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register 2D view export tools with the MCP server."""

    @mcp.tool()
    def export_2d_view(
        name: str,
        view: str,
        format: str = "svg",
        dpi: int = 150,
        compression: str = "lossless",
    ) -> str:
        """Export a 2D view of a 3D model.
        
        Supports friendly view names: top, bottom, front, back, left, right,
        isometric, dimetric, trimetric.
        
        Supported formats:
        - "svg": Vector format with embedded metadata (default)
        - "png": Bitmap format with EXIF metadata
        - "webp": Modern bitmap format with metadata
        
        For bitmap formats (PNG, WebP):
        - dpi: Resolution in dots per inch (default 150, use 300 for high quality)
        - compression: "lossless" (default) or "lossy"
        
        Metadata is embedded in all exports and includes:
        - model_name: Name of the 3D model
        - creation_timestamp: ISO 8601 timestamp (UTC)
        - source_code_hash: SHA-256 hash of the source code
        - view_angle: The view direction used
        - exporter_version: Version of the exporter
        - export_format: The output format
        - dpi: Resolution (for bitmap formats)
        - compression: Compression type (for bitmap formats)
        
        Args:
            name: Name of the previously created model
            view: View direction - "top", "bottom", "front", "back", "left", "right",
                  "isometric", "dimetric", "trimetric"
            format: Export format - "svg", "png", or "webp"
            dpi: Resolution in dots per inch (default 150)
            compression: "lossless" or "lossy" (bitmap formats only)
            
        Returns:
            JSON with success status, output path, and metadata
        """
        rid = new_request_id()
        with log_tool_call(log, "export_2d_view", {"name": name, "view": view, "format": format}, rid):
            try:
                # Validate inputs
                view_lower = view.lower()
                if view_lower not in VALID_2D_VIEWS:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid view: '{view}'. Supported views: {sorted(VALID_2D_VIEWS)}"
                    })
                
                format_lower = format.lower()
                if format_lower not in ("svg", "png", "webp"):
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid format: '{format}'. Supported formats: svg, png, webp"
                    })
                
                if compression not in ("lossless", "lossy"):
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid compression: '{compression}'. Use 'lossless' or 'lossy'"
                    })
                
                # Get model
                entry = store.get_required(name)
                shape = entry["shape"]
                source_code = entry.get("code", "")
                
                # Get view direction
                view_direction = VIEW_DIRECTIONS.get(view_lower)
                if view_direction is None:
                    return json.dumps({
                        "success": False,
                        "error": f"View '{view}' not configured in VIEW_DIRECTIONS"
                    })
                
                # Create output directory and path
                d = model_dir(config.output_dir, name)
                output_path = d / f"{name}_{view_lower}.{format_lower}"
                
                # Create metadata
                metadata = create_metadata(
                    model_name=name,
                    source_code=source_code,
                    view_angle=view_lower,
                    export_format=format_lower,
                    dpi=dpi if format_lower in ("png", "webp") else None,
                    compression=compression if format_lower in ("png", "webp") else None,
                )
                
                # Export based on format
                success = False
                if format_lower == "svg":
                    success = export_view_to_svg(shape, output_path, view_direction, view_lower, metadata)
                elif format_lower == "png":
                    success = export_view_to_png(shape, output_path, view_direction, metadata, dpi, compression)
                elif format_lower == "webp":
                    success = export_view_to_webp(shape, output_path, view_direction, metadata, dpi, compression)
                
                if not success:
                    return json.dumps({
                        "success": False,
                        "error": f"Failed to export {view} view to {format}"
                    })
                
                # Get file size
                file_size = output_path.stat().st_size
                
                log.info("2d_view_exported", extra={
                    "request_id": rid,
                    "model_name": name,
                    "view": view_lower,
                    "format": format_lower,
                    "path": str(output_path),
                    "file_size": file_size,
                })
                
                return json.dumps({
                    "success": True,
                    "name": name,
                    "view": view_lower,
                    "format": format_lower,
                    "path": str(output_path),
                    "file_size_bytes": file_size,
                    "metadata": metadata,
                }, indent=2)
                
            except Exception as e:
                log.error("export_2d_view_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)


# Register additional exports in core module
from threedp.tools import core as core_module

def patch_core_export_model():
    """Patch core.export_model to add metadata support."""
    # This will be called from server.py after all modules are loaded
    pass