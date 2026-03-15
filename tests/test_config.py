"""Tests for config module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from threedp.config import ServerConfig, get_config


class TestServerConfig:
    """Test ServerConfig dataclass."""

    def test_defaults(self, tmp_path: Path) -> None:
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove any THREEDP env vars
            for key in list(os.environ.keys()):
                if key.startswith("THREEDP_"):
                    del os.environ[key]

            config = ServerConfig(output_dir=tmp_path / "outputs", log_dir=tmp_path / "logs")

            assert config.server_name == "3dp-mcp-server"
            assert config.transport == "stdio"
            assert config.default_material == "PLA"
            assert config.default_infill_pct == 15.0
            assert config.default_layer_height_mm == 0.2
            assert config.min_wall_thickness_mm == 0.8
            assert config.build_volume_x_mm == 256
            assert config.build_volume_y_mm == 256
            assert config.build_volume_z_mm == 256

    def test_env_override(self, tmp_path: Path) -> None:
        """Test that environment variables override defaults."""
        import importlib
        import threedp.config as config_mod

        env = {
            "THREEDP_OUTPUT_DIR": str(tmp_path / "custom_outputs"),
            "THREEDP_LOG_DIR": str(tmp_path / "custom_logs"),
            "THREEDP_PRINTER": "Prusa MK4",
            "THREEDP_BUILD_X": "210",
            "THREEDP_BUILD_Y": "210",
            "THREEDP_BUILD_Z": "250",
            "THREEDP_DEFAULT_MATERIAL": "PETG",
            "THREEDP_DEFAULT_INFILL": "20",
            "THINGIVERSE_API_KEY": "test_key_123",
        }
        with patch.dict(os.environ, env, clear=False):
            importlib.reload(config_mod)
            config = config_mod.ServerConfig()

            assert config.printer_name == "Prusa MK4"
            assert config.build_volume_x_mm == 210
            assert config.build_volume_y_mm == 210
            assert config.build_volume_z_mm == 250
            assert config.default_material == "PETG"
            assert config.default_infill_pct == 20.0
            assert config.thingiverse_api_key == "test_key_123"

            # Reset for other tests
            importlib.reload(config_mod)

    def test_build_volume_tuple(self, tmp_path: Path) -> None:
        """Test build_volume property returns tuple."""
        config = ServerConfig(
            output_dir=tmp_path / "o",
            log_dir=tmp_path / "l",
            build_volume_x_mm=300,
            build_volume_y_mm=200,
            build_volume_z_mm=100,
        )
        assert config.build_volume == (300.0, 200.0, 100.0)

    def test_printer_description(self, tmp_path: Path) -> None:
        """Test printer_description returns formatted string."""
        config = ServerConfig(
            output_dir=tmp_path / "o",
            log_dir=tmp_path / "l",
            printer_name="Ender 3",
            build_volume_x_mm=220,
            build_volume_y_mm=220,
            build_volume_z_mm=250,
        )
        desc = config.printer_description()
        assert "Ender 3" in desc
        assert "220x220x250" in desc

    def test_directories_created(self, tmp_path: Path) -> None:
        """Test that __post_init__ creates required directories."""
        out = tmp_path / "test_outputs"
        log = tmp_path / "test_logs"
        config = ServerConfig(output_dir=out, log_dir=log)
        assert out.exists()
        assert log.exists()

    def test_get_config_singleton(self) -> None:
        """Test get_config returns same instance."""
        # Reset singleton for test
        import threedp.config as config_mod
        config_mod._config = None

        c1 = get_config()
        c2 = get_config()
        assert c1 is c2


class TestApiKeys:
    """Test API key loading from environment."""

    def test_all_api_keys_load(self, tmp_path: Path) -> None:
        """Test that all API key fields load from env."""
        env = {
            "THINGIVERSE_API_KEY": "tv_key",
            "THINGIVERSE_TOKEN": "tv_token",
            "GITHUB_TOKEN": "gh_token",
            "MYMINIFACTORY_TOKEN": "mmf_token",
            "CULTS3D_API_KEY": "cults_key",
        }
        with patch.dict(os.environ, env, clear=False):
            config = ServerConfig(output_dir=tmp_path / "o", log_dir=tmp_path / "l")
            assert config.thingiverse_api_key == "tv_key"
            assert config.thingiverse_token == "tv_token"
            assert config.github_token == "gh_token"
            assert config.myminifactory_token == "mmf_token"
            assert config.cults3d_api_key == "cults_key"

    def test_api_keys_default_empty(self, tmp_path: Path) -> None:
        """Test API keys default to empty strings."""
        with patch.dict(os.environ, {}, clear=False):
            for key in ["THINGIVERSE_API_KEY", "THINGIVERSE_TOKEN", "GITHUB_TOKEN", "MYMINIFACTORY_TOKEN", "CULTS3D_API_KEY"]:
                os.environ.pop(key, None)
            config = ServerConfig(output_dir=tmp_path / "o", log_dir=tmp_path / "l")
            assert config.thingiverse_api_key == ""
            assert config.github_token == ""
