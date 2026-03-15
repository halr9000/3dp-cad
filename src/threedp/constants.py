"""Constants and lookup tables for 3D printing."""

from __future__ import annotations

# ── Material Properties ──────────────────────────────────────────────────────

MATERIAL_PROPERTIES: dict[str, dict[str, float]] = {
    "PLA":   {"density": 1.24, "shrinkage": 0.003},
    "PETG":  {"density": 1.27, "shrinkage": 0.004},
    "ABS":   {"density": 1.04, "shrinkage": 0.007},
    "ASA":   {"density": 1.07, "shrinkage": 0.005},
    "TPU":   {"density": 1.21, "shrinkage": 0.005},
    "Nylon": {"density": 1.14, "shrinkage": 0.015},
}

# ── ISO Metric Thread Table ──────────────────────────────────────────────────

ISO_THREAD_TABLE: dict[str, dict[str, float]] = {
    "M2":   {"tap_drill": 1.6,  "insert_drill": 3.2,  "clearance_drill": 2.4},
    "M2.5": {"tap_drill": 2.05, "insert_drill": 3.5,  "clearance_drill": 2.9},
    "M3":   {"tap_drill": 2.5,  "insert_drill": 4.0,  "clearance_drill": 3.4},
    "M4":   {"tap_drill": 3.3,  "insert_drill": 5.0,  "clearance_drill": 4.5},
    "M5":   {"tap_drill": 4.2,  "insert_drill": 6.0,  "clearance_drill": 5.5},
    "M6":   {"tap_drill": 5.0,  "insert_drill": 7.0,  "clearance_drill": 6.6},
    "M8":   {"tap_drill": 6.8,  "insert_drill": 9.5,  "clearance_drill": 8.4},
    "M10":  {"tap_drill": 8.5,  "insert_drill": 12.0, "clearance_drill": 10.5},
}

# ── Print Defaults ───────────────────────────────────────────────────────────

DEFAULT_FILAMENT_DIAMETER_MM: float = 1.75
DEFAULT_COST_PER_KG_USD: float = 20.0
DEFAULT_WALL_THICKNESS_MM: float = 0.8
DEFAULT_NUM_PERIMETERS: int = 2

# ── View Directions (for SVG export) ─────────────────────────────────────────

VIEW_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "front":  (0, -1, 0),
    "back":   (0,  1, 0),
    "right":  (1,  0, 0),
    "left":   (-1, 0, 0),
    "top":    (0,  0, 1),
    "bottom": (0,  0, -1),
    "iso":    (1, -1, 1),
}
