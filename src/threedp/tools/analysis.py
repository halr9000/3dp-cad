"""Analysis tools: printability, overhangs, orientation, print estimation, visualization."""

from __future__ import annotations

import json
import math
from typing import Any

from threedp.config import ServerConfig
from threedp.constants import MATERIAL_PROPERTIES, DEFAULT_FILAMENT_DIAMETER_MM, DEFAULT_COST_PER_KG_USD, DEFAULT_WALL_THICKNESS_MM, DEFAULT_NUM_PERIMETERS, VIEW_DIRECTIONS
from threedp.helpers import error_response, compute_overhangs, model_dir, shape_to_model_entry
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register analysis tools with the MCP server."""

    @mcp.tool()
    def analyze_printability(name: str, min_wall_mm: float = 0.8) -> str:
        """Check if a model is suitable for FDM 3D printing (e.g. Bambu Lab X1C).

        Args:
            name: Name of a previously created model
            min_wall_mm: Minimum wall thickness in mm (default 0.8)
        """
        rid = new_request_id()
        with log_tool_call(log, "analyze_printability", {"name": name, "min_wall_mm": min_wall_mm}, rid):
            try:
                entry = store.get_required(name)
                shape = entry["shape"]
                issues: list[str] = []
                checks: dict[str, Any] = {}

                try:
                    vol = shape.volume
                    checks["volume_mm3"] = round(vol, 3)
                    if vol <= 0:
                        issues.append("Model has zero or negative volume")
                except Exception as e:
                    issues.append(f"Cannot compute volume: {e}")

                try:
                    solids = shape.solids()
                    checks["solid_count"] = len(solids)
                    if len(solids) == 0:
                        issues.append("No solids found — not printable")
                except Exception:
                    pass

                bb = entry["bbox"]
                dims = bb["size"]
                checks["dimensions_mm"] = dims
                bv = config.build_volume
                if any(d < 1.0 for d in dims):
                    issues.append(f"Very small dimension ({min(dims):.1f}mm)")
                if any(d > max(bv) for d in dims):
                    issues.append(f"Exceeds {max(bv):.0f}mm ({max(dims):.1f}mm) — may not fit bed")

                try:
                    faces = shape.faces()
                    checks["face_count"] = len(faces)
                    if len(faces) < 4:
                        issues.append("Too few faces for a valid solid")
                except Exception:
                    pass

                try:
                    area = shape.area
                    vol = shape.volume
                    if vol > 0:
                        ratio = area / vol
                        checks["area_volume_ratio"] = round(ratio, 4)
                        if ratio > 7.5:
                            issues.append(f"High area/volume ratio ({ratio:.2f}) — possible thin walls < {min_wall_mm}mm")
                except Exception:
                    pass

                verdict = "PRINTABLE" if not issues else "REVIEW NEEDED"

                log.info("printability_analyzed", extra={
                    "request_id": rid, "model_name": name, "verdict": verdict,
                    "issue_count": len(issues),
                })

                return json.dumps({
                    "verdict": verdict,
                    "issues": issues,
                    "checks": checks,
                    "printer": config.printer_description(),
                }, indent=2)

            except Exception as e:
                log.error("analyze_printability_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def analyze_overhangs(name: str, max_angle: float = 45.0) -> str:
        """Analyze overhang faces that may need support material.

        Args:
            name: Name of a previously created model
            max_angle: Maximum unsupported overhang angle in degrees (default 45)
        """
        rid = new_request_id()
        with log_tool_call(log, "analyze_overhangs", {"name": name, "max_angle": max_angle}, rid):
            try:
                entry = store.get_required(name)
                result = compute_overhangs(entry["shape"], max_angle)
                result["success"] = True
                result["name"] = name
                result["max_angle"] = max_angle
                result["worst_overhangs"] = sorted(
                    result.pop("overhang_faces"), key=lambda f: f["angle_deg"], reverse=True
                )[:10]

                log.info("overhangs_analyzed", extra={
                    "request_id": rid, "model_name": name,
                    "overhang_count": result["overhang_face_count"],
                    "overhang_pct": result["overhang_pct"],
                })

                return json.dumps(result, indent=2)

            except Exception as e:
                log.error("analyze_overhangs_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def suggest_orientation(name: str) -> str:
        """Suggest optimal print orientation to minimize supports and maximize bed adhesion.

        Tests 24 orientations (90-degree increments around X and Y)
        and scores each by overhang area, bed contact, and height.

        Args:
            name: Name of a previously created model
        """
        rid = new_request_id()
        with log_tool_call(log, "suggest_orientation", {"name": name}, rid):
            try:
                from build123d import Rot

                entry = store.get_required(name)
                shape = entry["shape"]
                candidates = []

                for rx in [0, 90, 180, 270]:
                    for ry in [0, 90, 180, 270]:
                        rotated = Rot(rx, ry, 0) * shape
                        bb = rotated.bounding_box()
                        height = bb.max.Z - bb.min.Z

                        ovh = compute_overhangs(rotated, 45.0)
                        overhang_area = ovh["overhang_area"]

                        bed_area = 0.0
                        min_z = bb.min.Z
                        for face in rotated.faces():
                            try:
                                n = face.normal_at()
                                if n.Z < -0.95 and abs(face.center().Z - min_z) < 0.5:
                                    bed_area += face.area
                            except Exception:
                                continue

                        score = overhang_area - bed_area * 2 + height * 0.5
                        candidates.append({
                            "rotation": [rx, ry, 0],
                            "overhang_area": round(overhang_area, 1),
                            "bed_contact_area": round(bed_area, 1),
                            "height_mm": round(height, 1),
                            "score": round(score, 1),
                        })

                candidates.sort(key=lambda c: c["score"])
                seen_scores = set()
                unique = []
                for c in candidates:
                    key = round(c["score"], 0)
                    if key not in seen_scores:
                        seen_scores.add(key)
                        unique.append(c)
                    if len(unique) >= 5:
                        break

                log.info("orientation_suggested", extra={
                    "request_id": rid, "model_name": name,
                    "best_rotation": unique[0]["rotation"] if unique else None,
                })

                return json.dumps({
                    "success": True, "name": name,
                    "best": unique[0] if unique else None,
                    "top_candidates": unique,
                }, indent=2)

            except Exception as e:
                log.error("suggest_orientation_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def estimate_print(name: str, infill_percent: float = 15.0, layer_height: float = 0.2, material: str = "PLA") -> str:
        """Estimate filament usage, weight, and cost for printing a model.

        Args:
            name: Name of a previously created model
            infill_percent: Infill percentage (default 15)
            layer_height: Layer height in mm (default 0.2)
            material: Filament material - PLA, PETG, ABS, TPU, or ASA (default PLA)
        """
        rid = new_request_id()
        with log_tool_call(log, "estimate_print", {"name": name, "material": material, "infill": infill_percent}, rid):
            try:
                entry = store.get_required(name)
                shape = entry["shape"]
                mat = material.upper()
                if mat not in MATERIAL_PROPERTIES:
                    return json.dumps({"success": False, "error": f"Unknown material: {material}. Supported: {list(MATERIAL_PROPERTIES.keys())}"})

                density = MATERIAL_PROPERTIES[mat]["density"]
                total_volume_mm3 = shape.volume
                surface_area_mm2 = shape.area

                shell_volume_mm3 = surface_area_mm2 * DEFAULT_WALL_THICKNESS_MM * DEFAULT_NUM_PERIMETERS
                interior_volume_mm3 = max(0, total_volume_mm3 - shell_volume_mm3)
                infill_volume_mm3 = interior_volume_mm3 * (infill_percent / 100.0)
                used_volume_mm3 = shell_volume_mm3 + infill_volume_mm3
                used_volume_cm3 = used_volume_mm3 / 1000.0

                weight_g = used_volume_cm3 * density
                filament_cross_section = math.pi * (DEFAULT_FILAMENT_DIAMETER_MM / 2.0) ** 2
                filament_length_m = (used_volume_mm3 / filament_cross_section) / 1000.0
                cost = (weight_g / 1000.0) * DEFAULT_COST_PER_KG_USD

                layers = entry["bbox"]["size"][2] / layer_height
                est_minutes = (layers * 2.0 + used_volume_mm3 / 500.0) / 60.0

                log.info("print_estimated", extra={
                    "request_id": rid, "model_name": name, "material": mat,
                    "weight_g": round(weight_g, 1), "cost_usd": round(cost, 2),
                })

                return json.dumps({
                    "success": True, "name": name, "material": mat,
                    "infill_percent": infill_percent, "layer_height_mm": layer_height,
                    "model_volume_mm3": round(total_volume_mm3, 1),
                    "shell_volume_mm3": round(shell_volume_mm3, 1),
                    "infill_volume_mm3": round(infill_volume_mm3, 1),
                    "total_filament_volume_mm3": round(used_volume_mm3, 1),
                    "weight_g": round(weight_g, 1),
                    "filament_length_m": round(filament_length_m, 2),
                    "estimated_cost_usd": round(cost, 2),
                    "estimated_time_min": round(est_minutes, 0),
                    "density_g_cm3": density,
                }, indent=2)

            except Exception as e:
                log.error("estimate_print_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def section_view(name: str, source_name: str, plane: str = "XY", offset: float = 0.0) -> str:
        """Generate a 2D cross-section of a model and export as SVG.

        Args:
            name: Name for the cross-section result
            source_name: Name of the source model to section
            plane: Section plane - "XY", "XZ", or "YZ" (default "XY")
            offset: Position along the plane normal axis (default 0.0)
        """
        rid = new_request_id()
        with log_tool_call(log, "section_view", {"name": name, "source": source_name, "plane": plane, "offset": offset}, rid):
            try:
                from build123d import Plane as B3dPlane, ExportSVG

                entry = store.get_required(source_name)
                shape = entry["shape"]

                plane_map = {"XY": B3dPlane.XY, "XZ": B3dPlane.XZ, "YZ": B3dPlane.YZ}
                section_plane = plane_map.get(plane.upper())
                if section_plane is None:
                    return json.dumps({"success": False, "error": f"Unknown plane: {plane}. Use XY, XZ, or YZ."})

                if offset != 0.0:
                    section_plane = section_plane.offset(offset)

                section = shape.section(section_plane)
                new_entry = shape_to_model_entry(section, code=f"section of {source_name} at {plane} offset={offset}")
                store.put(name, new_entry)

                d = model_dir(config.output_dir, name)
                svg_path = d / f"{name}.svg"

                exporter = ExportSVG(scale=2.0)
                exporter.add_layer("section")
                exporter.add_shape(section, layer="section")
                exporter.write(str(svg_path))

                log.info("section_created", extra={
                    "request_id": rid, "model_name": name, "source": source_name,
                    "plane": plane, "svg_path": str(svg_path),
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "plane": plane, "offset": offset, "svg_path": str(svg_path),
                    "bbox": new_entry["bbox"],
                }, indent=2)

            except Exception as e:
                log.error("section_view_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def export_drawing(name: str, views: str = '["front", "top", "right"]', page_size: str = "A4") -> str:
        """Generate a 2D technical drawing as SVG with multiple view projections.

        Args:
            name: Name of a previously created model
            views: JSON list of view directions, e.g. '["front", "top", "right", "iso"]'
            page_size: Page size - "A4" or "A3" (default "A4")
        """
        rid = new_request_id()
        with log_tool_call(log, "export_drawing", {"name": name, "views": views}, rid):
            try:
                from build123d import ExportSVG, Vector

                entry = store.get_required(name)
                shape = entry["shape"]
                view_list = json.loads(views) if isinstance(views, str) else views

                d = model_dir(config.output_dir, name)
                svg_path = d / f"{name}_drawing.svg"

                exporter = ExportSVG(scale=1.0)
                for view_name in view_list:
                    vn = view_name.lower()
                    direction_tuple = VIEW_DIRECTIONS.get(vn)
                    if direction_tuple is None:
                        return json.dumps({"success": False, "error": f"Unknown view: {view_name}. Supported: {list(VIEW_DIRECTIONS.keys())}"})

                    direction = Vector(*direction_tuple)
                    layer_name = f"view_{vn}"
                    exporter.add_layer(layer_name)
                    exporter.add_shape(shape, layer=layer_name, line_type=ExportSVG.LineType.VISIBLE,
                                       view_port_origin=direction)

                exporter.write(str(svg_path))

                log.info("drawing_exported", extra={
                    "request_id": rid, "model_name": name,
                    "views": view_list, "svg_path": str(svg_path),
                })

                return json.dumps({
                    "success": True, "name": name, "views": view_list, "svg_path": str(svg_path),
                }, indent=2)

            except Exception as e:
                log.error("export_drawing_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)
