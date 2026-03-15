"""Configuration for the 3DP CAD MCP server.

All settings are configurable via environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    """Server configuration loaded from environment variables."""

    # ── Paths ────────────────────────────────────────────────────────────────
    output_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("THREEDP_OUTPUT_DIR", Path(__file__).parent.parent.parent / "outputs")
    ))

    log_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("THREEDP_LOG_DIR", Path(__file__).parent.parent.parent / "logs")
    ))

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = os.environ.get("THREEDP_LOG_LEVEL", "INFO")

    # ── Printer Profile ──────────────────────────────────────────────────────
    printer_name: str = os.environ.get("THREEDP_PRINTER", "Bambu Lab X1C")
    build_volume_x_mm: float = float(os.environ.get("THREEDP_BUILD_X", "256"))
    build_volume_y_mm: float = float(os.environ.get("THREEDP_BUILD_Y", "256"))
    build_volume_z_mm: float = float(os.environ.get("THREEDP_BUILD_Z", "256"))

    # ── Print Defaults ───────────────────────────────────────────────────────
    default_material: str = os.environ.get("THREEDP_DEFAULT_MATERIAL", "PLA")
    default_infill_pct: float = float(os.environ.get("THREEDP_DEFAULT_INFILL", "15"))
    default_layer_height_mm: float = float(os.environ.get("THREEDP_DEFAULT_LAYER_HEIGHT", "0.2"))
    min_wall_thickness_mm: float = float(os.environ.get("THREEDP_MIN_WALL", "0.8"))

    # ── API Keys (for publishing tools) ──────────────────────────────────────
    thingiverse_api_key: str = field(default_factory=lambda: os.environ.get("THINGIVERSE_API_KEY", ""))
    thingiverse_token: str = field(default_factory=lambda: os.environ.get("THINGIVERSE_TOKEN", ""))
    github_token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", ""))
    myminifactory_token: str = field(default_factory=lambda: os.environ.get("MYMINIFACTORY_TOKEN", ""))
    cults3d_api_key: str = field(default_factory=lambda: os.environ.get("CULTS3D_API_KEY", ""))

    # ── Server Settings ──────────────────────────────────────────────────────
    server_name: str = "3dp-mcp-server"
    transport: str = os.environ.get("THREEDP_TRANSPORT", "stdio")

    def __post_init__(self) -> None:
        """Create required directories."""
        self.output_dir = Path(self.output_dir)
        self.log_dir = Path(self.log_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def build_volume(self) -> tuple[float, float, float]:
        """Return (x, y, z) build volume in mm."""
        return (self.build_volume_x_mm, self.build_volume_y_mm, self.build_volume_z_mm)

    def printer_description(self) -> str:
        """Human-readable printer description."""
        return f"{self.printer_name} ({self.build_volume_x_mm}x{self.build_volume_y_mm}x{self.build_volume_z_mm}mm)"


# ── Singleton ────────────────────────────────────────────────────────────────

_config: ServerConfig | None = None


def get_config() -> ServerConfig:
    """Return the global server configuration (lazy singleton)."""
    global _config
    if _config is None:
        _config = ServerConfig()
    return _config
