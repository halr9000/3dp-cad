"""Tests for constants module."""

from __future__ import annotations

import pytest

from threedp.constants import (
    MATERIAL_PROPERTIES,
    ISO_THREAD_TABLE,
    DEFAULT_FILAMENT_DIAMETER_MM,
    DEFAULT_COST_PER_KG_USD,
    VIEW_DIRECTIONS,
)


class TestMaterialProperties:
    """Test MATERIAL_PROPERTIES constant."""

    def test_all_materials_have_required_fields(self) -> None:
        """Test that every material has density and shrinkage."""
        for mat, props in MATERIAL_PROPERTIES.items():
            assert "density" in props, f"{mat} missing density"
            assert "shrinkage" in props, f"{mat} missing shrinkage"
            assert props["density"] > 0, f"{mat} density must be positive"
            assert 0 < props["shrinkage"] < 1, f"{mat} shrinkage must be between 0 and 1"

    def test_pla_values(self) -> None:
        """Test PLA material properties."""
        pla = MATERIAL_PROPERTIES["PLA"]
        assert pla["density"] == pytest.approx(1.24, abs=0.01)
        assert pla["shrinkage"] == pytest.approx(0.003, abs=0.001)

    def test_expected_materials(self) -> None:
        """Test that expected materials are present."""
        expected = {"PLA", "PETG", "ABS", "ASA", "TPU", "Nylon"}
        assert set(MATERIAL_PROPERTIES.keys()) == expected


class TestThreadTable:
    """Test ISO_THREAD_TABLE constant."""

    def test_all_sizes_have_drills(self) -> None:
        """Test that every thread size has all three drill sizes."""
        for size, drills in ISO_THREAD_TABLE.items():
            assert "tap_drill" in drills, f"{size} missing tap_drill"
            assert "insert_drill" in drills, f"{size} missing insert_drill"
            assert "clearance_drill" in drills, f"{size} missing clearance_drill"

    def test_drill_ordering(self) -> None:
        """Test that tap < clearance < insert for all sizes."""
        for size, drills in ISO_THREAD_TABLE.items():
            tap = drills["tap_drill"]
            clear = drills["clearance_drill"]
            insert = drills["insert_drill"]
            assert tap < clear < insert, f"{size}: tap({tap}) < clearance({clear}) < insert({insert})"

    def test_m3_values(self) -> None:
        """Test M3 thread drill values."""
        m3 = ISO_THREAD_TABLE["M3"]
        assert m3["tap_drill"] == 2.5
        assert m3["insert_drill"] == 4.0
        assert m3["clearance_drill"] == 3.4

    def test_expected_sizes(self) -> None:
        """Test that expected thread sizes are present."""
        expected = {"M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10"}
        assert set(ISO_THREAD_TABLE.keys()) == expected


class TestDefaults:
    """Test default constants."""

    def test_filament_diameter(self) -> None:
        """Test standard filament diameter."""
        assert DEFAULT_FILAMENT_DIAMETER_MM == 1.75

    def test_cost_per_kg(self) -> None:
        """Test cost per kg is reasonable."""
        assert DEFAULT_COST_PER_KG_USD > 0


class TestViewDirections:
    """Test VIEW_DIRECTIONS constant."""

    def test_all_standard_views(self) -> None:
        """Test that standard orthographic views are present."""
        expected = {"front", "back", "right", "left", "top", "bottom", "iso"}
        assert set(VIEW_DIRECTIONS.keys()) == expected

    def test_directions_are_3tuples(self) -> None:
        """Test that all directions are 3-tuples."""
        for name, direction in VIEW_DIRECTIONS.items():
            assert len(direction) == 3, f"{name} should be a 3-tuple"

    def test_orthographic_views_are_unit_vectors(self) -> None:
        """Test that standard views have magnitude 1."""
        import math
        for name, (x, y, z) in VIEW_DIRECTIONS.items():
            if name == "iso":  # iso is diagonal, skip
                continue
            magnitude = math.sqrt(x**2 + y**2 + z**2)
            assert magnitude == pytest.approx(1.0, abs=0.01), f"{name} magnitude should be 1"
