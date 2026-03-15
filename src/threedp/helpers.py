"""Shared geometry utilities for build123d operations.

These are the core helper functions used by all tool modules.
"""

from __future__ import annotations

import json
import math
import traceback
from pathlib import Path
from typing import Any

from threedp.logging_config import get_logger

log = get_logger()


# ── Shape → Model Entry ──────────────────────────────────────────────────────

def shape_to_model_entry(shape: Any, code: str = "") -> dict[str, Any]:
    """Convert a build123d shape into a model entry dict with bbox and volume.

    Args:
        shape: A build123d Shape/Part object
        code: Optional source code string that created this shape

    Returns:
        Dict with keys: shape, code, bbox, volume
    """
    bb = shape.bounding_box()
    bbox = {
        "min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
        "max": [round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3)],
        "size": [
            round(bb.max.X - bb.min.X, 3),
            round(bb.max.Y - bb.min.Y, 3),
            round(bb.max.Z - bb.min.Z, 3),
        ],
    }
    try:
        volume = round(shape.volume, 3)
    except Exception:
        volume = None

    return {"shape": shape, "code": code, "bbox": bbox, "volume": volume}


# ── Code Execution ───────────────────────────────────────────────────────────

def run_build123d_code(code: str) -> dict[str, Any]:
    """Execute build123d Python code and return the model entry.

    The code MUST assign the final shape to a variable called `result`.

    Args:
        code: Python code string that creates a build123d shape

    Returns:
        Model entry dict from shape_to_model_entry()

    Raises:
        ValueError: If code doesn't assign to `result`
    """
    local_ns: dict[str, Any] = {}
    exec_globals = {"__builtins__": __builtins__}
    exec(code, exec_globals, local_ns)

    if "result" not in local_ns:
        raise ValueError("Code must assign the final shape to a variable called `result`")

    return shape_to_model_entry(local_ns["result"], code)


# ── Face Selection ────────────────────────────────────────────────────────────

def select_face(shape: Any, direction: str) -> Any:
    """Select a face by direction name (top/bottom/front/back/left/right).

    Args:
        shape: A build123d Shape object
        direction: One of: top, bottom, front, back, left, right

    Returns:
        The selected Face object

    Raises:
        ValueError: If direction is not recognized
    """
    all_faces = shape.faces()
    selectors = {
        "top":    lambda f: f.center().Z,
        "bottom": lambda f: -f.center().Z,
        "front":  lambda f: f.center().Y,
        "back":   lambda f: -f.center().Y,
        "right":  lambda f: f.center().X,
        "left":   lambda f: -f.center().X,
    }
    key_fn = selectors.get(direction.lower())
    if key_fn is None:
        raise ValueError(f"Unknown face direction: {direction}. Use: {list(selectors.keys())}")
    return max(all_faces, key=key_fn)


# ── Overhang Computation ─────────────────────────────────────────────────────

def compute_overhangs(shape: Any, max_angle_deg: float = 45.0) -> dict[str, Any]:
    """Compute overhang statistics for a shape.

    Analyzes face normals to find faces that exceed the maximum
    unsupported overhang angle relative to vertical (Z axis).

    Args:
        shape: A build123d Shape object
        max_angle_deg: Maximum unsupported overhang angle in degrees

    Returns:
        Dict with: total_faces, total_area, overhang_faces, overhang_face_count,
                   overhang_area, overhang_pct
    """
    threshold_rad = math.radians(max_angle_deg)
    all_faces = shape.faces()
    total_area = 0.0
    overhang_faces: list[dict[str, Any]] = []
    overhang_area = 0.0

    for i, face in enumerate(all_faces):
        area = face.area
        total_area += area
        try:
            normal = face.normal_at()
        except Exception:
            continue
        if normal.Z < 0:
            cos_val = min(abs(normal.Z), 1.0)
            angle_from_vertical = math.acos(cos_val)
            if angle_from_vertical > threshold_rad:
                angle_deg = math.degrees(angle_from_vertical)
                overhang_faces.append({
                    "index": i,
                    "area": round(area, 2),
                    "angle_deg": round(angle_deg, 1),
                })
                overhang_area += area

    return {
        "total_faces": len(all_faces),
        "total_area": round(total_area, 2),
        "overhang_faces": overhang_faces,
        "overhang_face_count": len(overhang_faces),
        "overhang_area": round(overhang_area, 2),
        "overhang_pct": round(overhang_area / total_area * 100, 1) if total_area > 0 else 0,
    }


# ── Error Response Builder ───────────────────────────────────────────────────

def error_response(error: Exception, include_traceback: bool = True) -> str:
    """Build a JSON error response string.

    Args:
        error: The exception that occurred
        include_traceback: Whether to include full traceback

    Returns:
        JSON string with success=False, error message, and optional traceback
    """
    response: dict[str, Any] = {"success": False, "error": str(error)}
    if include_traceback:
        response["traceback"] = traceback.format_exc()
    return json.dumps(response, indent=2)


# ── Success Response Builder ─────────────────────────────────────────────────

def success_response(data: dict[str, Any]) -> str:
    """Build a JSON success response string.

    Args:
        data: Response data dict (success=True is added automatically)

    Returns:
        JSON string with success=True and the provided data
    """
    data["success"] = True
    return json.dumps(data, indent=2)


# ── File Path Helpers ────────────────────────────────────────────────────────

def model_dir(output_dir: Path, name: str) -> Path:
    """Return the output directory for a model, creating it if needed."""
    d = output_dir / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_size_str(path: Path) -> str:
    """Return a human-readable file size string."""
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def ensure_exported(store: Any, output_dir: Path, name: str, fmt: str = "stl") -> Path:
    """Ensure a model is exported to disk and return the file path.

    If the file already exists, returns the existing path.
    Otherwise exports it first.

    Args:
        store: ModelStore instance
        output_dir: Base output directory
        name: Model name
        fmt: Export format (stl, step)

    Returns:
        Path to the exported file
    """
    entry = store.get_required(name)
    d = model_dir(output_dir, name)
    path = d / f"{name}.{fmt}"

    if not path.exists():
        from build123d import export_stl, export_step
        if fmt == "stl":
            export_stl(entry["shape"], str(path))
        elif fmt == "step":
            export_step(entry["shape"], str(path))
        else:
            raise ValueError(f"Unsupported format for publishing: {fmt}")
        log.info("model_exported", extra={"model_name": name, "format": fmt, "path": str(path)})

    return path
