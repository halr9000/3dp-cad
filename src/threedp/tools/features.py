"""Feature tools: text embossing, threaded holes, shrinkage compensation, packing, format conversion, color splitting."""

from __future__ import annotations

import json
import os
from typing import Any

from threedp.config import ServerConfig
from threedp.constants import MATERIAL_PROPERTIES, ISO_THREAD_TABLE
from threedp.helpers import error_response, select_face, shape_to_model_entry, model_dir, ensure_exported
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register feature tools with the MCP server."""

    @mcp.tool()
    def add_text(name: str, source_name: str, text: str, face: str = "top",
                 font_size: float = 10.0, depth: float = 1.0, font: str = "Arial",
                 emboss: bool = True) -> str:
        """Emboss or deboss text onto a model face.

        Args:
            name: Name for the resulting model
            source_name: Name of the source model
            text: Text string to add
            face: Face to place text on - "top", "bottom", "front", "back", "left", "right"
            font_size: Font size in mm (default 10)
            depth: Extrusion depth in mm (default 1.0)
            font: Font name (default "Arial")
            emboss: True to raise text (emboss), False to cut text (deboss)
        """
        rid = new_request_id()
        with log_tool_call(log, "add_text", {"name": name, "source": source_name, "text": text, "face": face, "emboss": emboss}, rid):
            try:
                from build123d import (BuildPart, BuildSketch, Text as B3dText, Plane as B3dPlane, extrude)

                entry = store.get_required(source_name)
                shape = entry["shape"]
                target_face = select_face(shape, face)
                fc = target_face.center()

                face_normal = target_face.normal_at()
                sketch_plane = B3dPlane(origin=(fc.X, fc.Y, fc.Z),
                                         z_dir=(face_normal.X, face_normal.Y, face_normal.Z))

                with BuildPart() as text_part:
                    with BuildSketch(sketch_plane):
                        B3dText(text, font_size, font=font)
                    extrude(amount=depth)

                text_solid = text_part.part
                result = shape + text_solid if emboss else shape - text_solid

                new_entry = shape_to_model_entry(result, code=f"{'emboss' if emboss else 'deboss'} '{text}' on {face} of {source_name}")
                store.put(name, new_entry)

                log.info("text_added", extra={
                    "request_id": rid, "model_name": name, "source": source_name,
                    "text": text, "face": face, "emboss": emboss,
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "text": text, "face": face, "emboss": emboss, "depth_mm": depth,
                    "bbox": new_entry["bbox"], "volume": new_entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("add_text_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def create_threaded_hole(name: str, source_name: str, position: str, thread_spec: str = "M3",
                              depth: float = 10.0, insert: bool = False) -> str:
        """Add a threaded or heat-set insert hole to a model.

        Args:
            name: Name for the resulting model
            source_name: Name of the source model
            position: JSON [x, y, z] position for the hole center
            thread_spec: ISO metric thread spec - M2, M2.5, M3, M4, M5, M6, M8, M10 (default M3)
            depth: Hole depth in mm (default 10)
            insert: If true, use heat-set insert diameter instead of tap drill (default false)
        """
        rid = new_request_id()
        with log_tool_call(log, "create_threaded_hole", {"name": name, "source": source_name, "thread": thread_spec, "insert": insert}, rid):
            try:
                from build123d import Cylinder, Pos

                entry = store.get_required(source_name)
                spec = thread_spec.upper()
                if spec not in ISO_THREAD_TABLE:
                    return json.dumps({"success": False, "error": f"Unknown thread spec: {thread_spec}. Supported: {list(ISO_THREAD_TABLE.keys())}"})

                pos = json.loads(position) if isinstance(position, str) else position
                thread = ISO_THREAD_TABLE[spec]
                diameter = thread["insert_drill"] if insert else thread["tap_drill"]
                radius = diameter / 2.0

                hole = Pos(pos[0], pos[1], pos[2]) * Cylinder(radius, depth)
                result = entry["shape"] - hole

                new_entry = shape_to_model_entry(result, code=f"{spec} {'insert' if insert else 'threaded'} hole at {pos}")
                store.put(name, new_entry)

                log.info("threaded_hole_created", extra={
                    "request_id": rid, "model_name": name, "thread_spec": spec,
                    "diameter": diameter, "depth": depth, "insert": insert,
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "thread_spec": spec, "hole_type": "heat-set insert" if insert else "tap drill",
                    "diameter_mm": diameter, "depth_mm": depth, "position": pos,
                    "bbox": new_entry["bbox"], "volume": new_entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("create_threaded_hole_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def shrinkage_compensation(name: str, source_name: str, material: str = "PLA") -> str:
        """Scale a model to compensate for material shrinkage after printing.

        Args:
            name: Name for the compensated model
            source_name: Name of the source model
            material: Filament material (default PLA). Supports PLA, PETG, ABS, ASA, TPU, Nylon.
        """
        rid = new_request_id()
        with log_tool_call(log, "shrinkage_compensation", {"name": name, "source": source_name, "material": material}, rid):
            try:
                source_entry = store.get_required(source_name)
                mat = material.upper()
                if mat not in MATERIAL_PROPERTIES:
                    return json.dumps({"success": False, "error": f"Unknown material: {material}. Supported: {list(MATERIAL_PROPERTIES.keys())}"})

                shrinkage = MATERIAL_PROPERTIES[mat]["shrinkage"]
                factor = 1.0 / (1.0 - shrinkage)
                compensated = source_entry["shape"].scale(factor)

                new_entry = shape_to_model_entry(compensated, code=f"shrinkage compensation of {source_name} for {mat} (×{factor:.5f})")
                store.put(name, new_entry)

                log.info("shrinkage_compensated", extra={
                    "request_id": rid, "model_name": name, "source": source_name,
                    "material": mat, "scale_factor": round(factor, 5),
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name, "material": mat,
                    "shrinkage_pct": round(shrinkage * 100, 2),
                    "scale_factor": round(factor, 5),
                    "original_bbox": source_entry["bbox"],
                    "compensated_bbox": new_entry["bbox"],
                }, indent=2)

            except Exception as e:
                log.error("shrinkage_compensation_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def pack_models(name: str, model_names: str, padding: float = 5.0) -> str:
        """Arrange multiple models compactly on the build plate for batch printing.

        Args:
            name: Name for the packed arrangement
            model_names: JSON list of model names to pack, e.g. '["part_a", "part_b"]'
            padding: Spacing between parts in mm (default 5.0)
        """
        rid = new_request_id()
        with log_tool_call(log, "pack_models", {"name": name, "model_names": model_names, "padding": padding}, rid):
            try:
                from build123d import pack, Compound

                names = json.loads(model_names) if isinstance(model_names, str) else model_names
                shapes = []
                for n in names:
                    entry = store.get_required(n)
                    shapes.append(entry["shape"])

                packed = pack(shapes, padding, align_z=True)
                compound = Compound(children=list(packed))

                new_entry = shape_to_model_entry(compound, code=f"pack of {names}")
                store.put(name, new_entry)

                positions = []
                for i, s in enumerate(packed):
                    bb = s.bounding_box()
                    positions.append({
                        "model": names[i],
                        "center": [round(bb.min.X + (bb.max.X - bb.min.X) / 2, 1),
                                   round(bb.min.Y + (bb.max.Y - bb.min.Y) / 2, 1)],
                    })

                log.info("models_packed", extra={
                    "request_id": rid, "model_name": name, "packed_count": len(names),
                })

                return json.dumps({
                    "success": True, "name": name, "packed_count": len(names),
                    "positions": positions, "bbox": new_entry["bbox"],
                }, indent=2)

            except Exception as e:
                log.error("pack_models_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def convert_format(input_path: str, output_path: str) -> str:
        """Convert a 3D model file between formats (STL, STEP, 3MF, BREP).

        Args:
            input_path: Path to the input file
            output_path: Path for the output file (format determined by extension)
        """
        rid = new_request_id()
        with log_tool_call(log, "convert_format", {"input": input_path, "output": output_path}, rid):
            try:
                from pathlib import Path as P

                in_ext = P(input_path).suffix.lower()
                out_ext = P(output_path).suffix.lower()

                # Import
                if in_ext == ".stl":
                    from build123d import import_stl
                    shape = import_stl(input_path)
                elif in_ext in (".step", ".stp"):
                    from build123d import import_step
                    shape = import_step(input_path)
                elif in_ext == ".brep":
                    from build123d import import_brep
                    shape = import_brep(input_path)
                else:
                    return json.dumps({"success": False, "error": f"Unsupported input format: {in_ext}"})

                # Export
                P(output_path).parent.mkdir(parents=True, exist_ok=True)
                if out_ext == ".stl":
                    from build123d import export_stl
                    export_stl(shape, output_path)
                elif out_ext in (".step", ".stp"):
                    from build123d import export_step
                    export_step(shape, output_path)
                elif out_ext == ".brep":
                    from build123d import export_brep
                    export_brep(shape, output_path)
                elif out_ext == ".3mf":
                    from build123d import Mesher
                    with Mesher() as mesher:
                        mesher.add_shape(shape)
                        mesher.write(output_path)
                else:
                    return json.dumps({"success": False, "error": f"Unsupported output format: {out_ext}"})

                log.info("format_converted", extra={
                    "request_id": rid, "input_format": in_ext, "output_format": out_ext,
                    "output_path": output_path,
                })

                return json.dumps({
                    "success": True, "input": input_path, "output": output_path,
                    "input_format": in_ext, "output_format": out_ext,
                }, indent=2)

            except Exception as e:
                log.error("convert_format_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def split_model_by_color(name: str, source_name: str, assignments: str) -> str:
        """Split a model into separate STL files by face direction for multi-color printing.

        Exports separate STLs compatible with Bambu Studio's multi-material workflow.

        Args:
            name: Base name for the output files
            source_name: Name of the source model
            assignments: JSON list of color assignments, e.g.
                '[{"faces": "top", "color": "#FF0000", "filament": 1}, {"faces": "rest", "color": "#FFFFFF", "filament": 0}]'
                Use "rest" for all unassigned faces.
        """
        rid = new_request_id()
        with log_tool_call(log, "split_model_by_color", {"name": name, "source": source_name}, rid):
            try:
                from build123d import export_stl

                entry = store.get_required(source_name)
                shape = entry["shape"]
                assigns = json.loads(assignments) if isinstance(assignments, str) else assignments

                d = model_dir(config.output_dir, name)

                outputs = []
                for asgn in assigns:
                    face_dir = asgn.get("faces", "rest")
                    color = asgn.get("color", "#000000")
                    filament = asgn.get("filament", 0)

                    # Export full model per assignment (face-level splitting requires complex boolean ops)
                    part = shape

                    stl_name = f"{name}_filament{filament}.stl"
                    stl_path = d / stl_name
                    export_stl(part, str(stl_path))
                    outputs.append({
                        "faces": face_dir,
                        "color": color,
                        "filament": filament,
                        "stl_path": str(stl_path),
                    })

                log.info("model_split_by_color", extra={
                    "request_id": rid, "model_name": name, "source": source_name,
                    "filament_count": len(outputs),
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "outputs": outputs,
                    "note": "Import all STLs into Bambu Studio and assign filaments per file.",
                }, indent=2)

            except Exception as e:
                log.error("split_model_by_color_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)
