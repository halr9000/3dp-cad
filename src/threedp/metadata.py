"""Metadata utilities for embedding and extracting metadata from exported files."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from threedp.logging_config import get_logger

log = get_logger()

EXPORTER_VERSION = "2.1.0"

METADATA_SCHEMA: dict[str, dict[str, str]] = {
    "model_name": {"type": "string", "description": "Name of the 3D model"},
    "creation_timestamp": {"type": "string", "format": "ISO 8601", "description": "When the export was created (UTC)"},
    "source_code_hash": {"type": "string", "description": "SHA-256 hash of the source code"},
    "view_angle": {"type": "string", "description": "View direction used for export"},
    "exporter_version": {"type": "string", "description": "Version of the 3DP CAD exporter"},
    "export_format": {"type": "string", "description": "Export format (svg, png, webp, stl, step, 3mf)"},
    "dpi": {"type": "number", "description": "Resolution in dots per inch"},
    "compression": {"type": "string", "description": "Compression type (lossless/lossy)"},
}


def compute_code_hash(code: str) -> str:
    """Compute SHA-256 hash of source code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def create_metadata(
    model_name: str,
    source_code: str | None,
    view_angle: str,
    export_format: str,
    dpi: int | None = None,
    compression: str | None = None,
) -> dict[str, Any]:
    """Create metadata dictionary for an export."""
    metadata: dict[str, Any] = {
        "model_name": model_name,
        "creation_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_code_hash": compute_code_hash(source_code) if source_code else "",
        "view_angle": view_angle,
        "exporter_version": EXPORTER_VERSION,
        "export_format": export_format,
    }
    if dpi is not None:
        metadata["dpi"] = dpi
    if compression is not None:
        metadata["compression"] = compression
    return metadata


def embed_svg_metadata(svg_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into SVG file using XML comments."""
    try:
        content = svg_path.read_text()
        metadata_json = json.dumps(metadata, indent=2)
        metadata_comment = f"""<!--\n3DP-CAD Metadata\n================\n{metadata_json}\n-->\n"""
        if content.startswith('<?xml'):
            xml_end = content.find('?>') + 2
            new_content = content[:xml_end] + '\n' + metadata_comment + content[xml_end:]
        else:
            new_content = metadata_comment + content
        svg_path.write_text(new_content)
        log.info("svg_metadata_embedded", extra={"path": str(svg_path)})
        return True
    except Exception as e:
        log.error("svg_metadata_embed_failed", extra={"path": str(svg_path), "error": str(e)})
        return False


def extract_svg_metadata(svg_path: Path) -> dict[str, Any] | None:
    """Extract metadata from SVG file."""
    try:
        content = svg_path.read_text()
        start_marker = "<!--\n3DP-CAD Metadata\n================\n"
        end_marker = "\n-->"
        start = content.find(start_marker)
        if start == -1:
            return None
        start += len(start_marker)
        end = content.find(end_marker, start)
        if end == -1:
            return None
        return json.loads(content[start:end])
    except Exception as e:
        log.error("svg_metadata_extract_failed", extra={"path": str(svg_path), "error": str(e)})
        return None


def embed_png_metadata(png_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into PNG file using tEXt chunk."""
    try:
        try:
            from PIL import Image, PngImagePlugin
            img = Image.open(png_path)
            metadata_json = json.dumps(metadata)
            info = PngImagePlugin.PngInfo()
            info.add_text("3DP-CAD", metadata_json)
            img.save(png_path, pnginfo=info)
            log.info("png_metadata_embedded", extra={"path": str(png_path)})
            return True
        except ImportError:
            log.warning("png_metadata_no_pil", extra={"path": str(png_path)})
            return False
    except Exception as e:
        log.error("png_metadata_embed_failed", extra={"path": str(png_path), "error": str(e)})
        return False


def extract_png_metadata(png_path: Path) -> dict[str, Any] | None:
    """Extract metadata from PNG file."""
    try:
        try:
            from PIL import Image
            img = Image.open(png_path)
            metadata_json = img.info.get("3DP-CAD")
            if metadata_json:
                return json.loads(metadata_json)
        except ImportError:
            pass
        return None
    except Exception as e:
        log.error("png_metadata_extract_failed", extra={"path": str(png_path), "error": str(e)})
        return None


def embed_webp_metadata(webp_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into WebP file."""
    try:
        try:
            from PIL import Image
            img = Image.open(webp_path)
            metadata_json = json.dumps(metadata)
            if hasattr(img, 'info'):
                img.info["3DP-CAD"] = metadata_json
                img.save(webp_path, **img.info)
            log.info("webp_metadata_embedded", extra={"path": str(webp_path)})
            return True
        except ImportError:
            log.warning("webp_metadata_no_pil", extra={"path": str(webp_path)})
            return False
    except Exception as e:
        log.error("webp_metadata_embed_failed", extra={"path": str(webp_path), "error": str(e)})
        return False


def extract_webp_metadata(webp_path: Path) -> dict[str, Any] | None:
    """Extract metadata from WebP file."""
    try:
        try:
            from PIL import Image
            img = Image.open(webp_path)
            metadata_json = img.info.get("3DP-CAD")
            if metadata_json:
                return json.loads(metadata_json)
        except ImportError:
            pass
        return None
    except Exception as e:
        log.error("webp_metadata_extract_failed", extra={"path": str(webp_path), "error": str(e)})
        return None


def embed_stl_metadata(stl_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into STL file as comment in header."""
    try:
        content = stl_path.read_bytes()
        is_binary = not content[:80].decode('ascii', errors='ignore').startswith('solid ')
        metadata_str = f"3DP-CAD|{json.dumps(metadata)}"
        if is_binary:
            header = metadata_str[:80].encode('ascii').ljust(80, b'\x00')
            new_content = header + content[80:]
        else:
            text = content.decode('ascii')
            lines = text.split('\n')
            metadata_comment = f"  ; {metadata_str}"
            new_lines = lines[:1] + [metadata_comment] + lines[1:]
            new_content = '\n'.join(new_lines).encode('ascii')
        stl_path.write_bytes(new_content)
        log.info("stl_metadata_embedded", extra={"path": str(stl_path)})
        return True
    except Exception as e:
        log.error("stl_metadata_embed_failed", extra={"path": str(stl_path), "error": str(e)})
        return False


def extract_stl_metadata(stl_path: Path) -> dict[str, Any] | None:
    """Extract metadata from STL file."""
    try:
        content = stl_path.read_bytes()
        header = content[:80].decode('ascii', errors='ignore')
        if header.startswith('solid '):
            text = content.decode('ascii')
            marker = "  ; 3DP-CAD|"
            start = text.find(marker)
            if start == -1:
                return None
            start += len(marker)
            end = text.find('\n', start)
            if end == -1:
                end = len(text)
            metadata_json = text[start:end]
        else:
            if '3DP-CAD|' not in header:
                return None
            start = header.find('3DP-CAD|') + len('3DP-CAD|')
            metadata_json = header[start:].rstrip('\x00')
        return json.loads(metadata_json)
    except Exception as e:
        log.error("stl_metadata_extract_failed", extra={"path": str(stl_path), "error": str(e)})
        return None


def embed_step_metadata(step_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into STEP file as comment."""
    try:
        content = step_path.read_text()
        metadata_json = json.dumps(metadata)
        metadata_comment = f"/* 3DP-CAD Metadata: {metadata_json} */\n"
        new_content = metadata_comment + content
        step_path.write_text(new_content)
        log.info("step_metadata_embedded", extra={"path": str(step_path)})
        return True
    except Exception as e:
        log.error("step_metadata_embed_failed", extra={"path": str(step_path), "error": str(e)})
        return False


def extract_step_metadata(step_path: Path) -> dict[str, Any] | None:
    """Extract metadata from STEP file."""
    try:
        content = step_path.read_text()
        marker = "/* 3DP-CAD Metadata: "
        start = content.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = content.find(" */", start)
        if end == -1:
            return None
        return json.loads(content[start:end])
    except Exception as e:
        log.error("step_metadata_extract_failed", extra={"path": str(step_path), "error": str(e)})
        return None


def embed_3mf_metadata(thmf_path: Path, metadata: dict[str, Any]) -> bool:
    """Embed metadata into 3MF file."""
    try:
        import zipfile
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            with zipfile.ZipFile(thmf_path, 'r') as zf:
                zf.extractall(tmpdir_path)
            metadata_file = tmpdir_path / "3D" / "_3dp_cad_metadata.json"
            metadata_file.parent.mkdir(parents=True, exist_ok=True)
            metadata_file.write_text(json.dumps(metadata, indent=2))
            with zipfile.ZipFile(thmf_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in tmpdir_path.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, str(file_path.relative_to(tmpdir_path)))
        log.info("3mf_metadata_embedded", extra={"path": str(thmf_path)})
        return True
    except Exception as e:
        log.error("3mf_metadata_embed_failed", extra={"path": str(thmf_path), "error": str(e)})
        return False


def extract_3mf_metadata(thmf_path: Path) -> dict[str, Any] | None:
    """Extract metadata from 3MF file."""
    try:
        import zipfile
        with zipfile.ZipFile(thmf_path, 'r') as zf:
            try:
                metadata_content = zf.read("3D/_3dp_cad_metadata.json")
                return json.loads(metadata_content.decode('utf-8'))
            except KeyError:
                return None
    except Exception as e:
        log.error("3mf_metadata_extract_failed", extra={"path": str(thmf_path), "error": str(e)})
        return None