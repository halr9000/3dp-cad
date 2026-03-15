"""Transform tools: scale, rotate, mirror, translate, combine, shell, split."""

from __future__ import annotations

import json
from typing import Any

from threedp.config import ServerConfig
from threedp.helpers import error_response, select_face, shape_to_model_entry
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register transform tools with the MCP server."""

    @mcp.tool()
    def transform_model(name: str, source_name: str, operations: str) -> str:
        """Scale, rotate, mirror, or translate a loaded model. Apply operations in order.

        Args:
            name: Name for the new transformed model
            source_name: Name of the source model to transform
            operations: JSON string with transform operations applied in order.
                Supported keys: "scale" (float or [x,y,z]), "rotate" ([rx,ry,rz] degrees),
                "mirror" ("XY","XZ","YZ"), "translate" ([x,y,z]).
                Can be a single dict or a list of dicts for ordered operations.
        """
        rid = new_request_id()
        with log_tool_call(log, "transform_model", {"name": name, "source": source_name, "ops_len": len(operations)}, rid):
            try:
                from build123d import Mirror, Plane as B3dPlane, Pos, Rot

                entry = store.get_required(source_name)
                shape = entry["shape"]
                ops = json.loads(operations)
                if isinstance(ops, dict):
                    ops = [ops]

                for op in ops:
                    if "scale" in op:
                        s = op["scale"]
                        if isinstance(s, (int, float)):
                            shape = shape.scale(s)
                        else:
                            shape = shape.scale(s[0], s[1], s[2])
                    if "rotate" in op:
                        rx, ry, rz = op["rotate"]
                        shape = Rot(rx, ry, rz) * shape
                    if "mirror" in op:
                        plane_map = {"XY": B3dPlane.XY, "XZ": B3dPlane.XZ, "YZ": B3dPlane.YZ}
                        mirror_plane = plane_map.get(op["mirror"].upper())
                        if mirror_plane is None:
                            return json.dumps({"success": False, "error": f"Unknown mirror plane: {op['mirror']}. Use XY, XZ, or YZ."})
                        shape = Mirror(about=mirror_plane) * shape
                    if "translate" in op:
                        tx, ty, tz = op["translate"]
                        shape = Pos(tx, ty, tz) * shape

                new_entry = shape_to_model_entry(shape, code=f"transform of {source_name}: {operations}")
                store.put(name, new_entry)

                log.info("model_transformed", extra={
                    "request_id": rid, "model_name": name, "source": source_name,
                    "bbox": new_entry["bbox"],
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "bbox": new_entry["bbox"], "volume": new_entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("transform_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def combine_models(name: str, model_a: str, model_b: str, operation: str = "union") -> str:
        """Boolean combine two loaded models: union, subtract, or intersect.

        Args:
            name: Name for the resulting combined model
            model_a: Name of the first model
            model_b: Name of the second model
            operation: Boolean operation - "union", "subtract", or "intersect"
        """
        rid = new_request_id()
        with log_tool_call(log, "combine_models", {"name": name, "a": model_a, "b": model_b, "op": operation}, rid):
            try:
                entry_a = store.get_required(model_a)
                entry_b = store.get_required(model_b)
                a = entry_a["shape"]
                b = entry_b["shape"]

                op = operation.lower()
                if op == "union":
                    result = a + b
                elif op == "subtract":
                    result = a - b
                elif op == "intersect":
                    result = a & b
                else:
                    return json.dumps({"success": False, "error": f"Unknown operation: {operation}. Use union, subtract, or intersect."})

                new_entry = shape_to_model_entry(result, code=f"{model_a} {op} {model_b}")
                store.put(name, new_entry)

                log.info("models_combined", extra={
                    "request_id": rid, "model_name": name, "operation": op,
                    "bbox": new_entry["bbox"],
                })

                return json.dumps({
                    "success": True, "name": name, "operation": op,
                    "model_a": model_a, "model_b": model_b,
                    "bbox": new_entry["bbox"], "volume": new_entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("combine_models_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def shell_model(name: str, source_name: str, thickness: float = 2.0, open_faces: str = "[]") -> str:
        """Hollow out a model, optionally leaving faces open.

        Args:
            name: Name for the new shelled model
            source_name: Name of the source model to hollow
            thickness: Wall thickness in mm (default 2.0)
            open_faces: JSON list of face directions to leave open, e.g. '["top"]' or '["bottom"]'.
                Supported: "top", "bottom". Default is no open faces.
        """
        rid = new_request_id()
        with log_tool_call(log, "shell_model", {"name": name, "source": source_name, "thickness": thickness}, rid):
            try:
                entry = store.get_required(source_name)
                shape = entry["shape"]
                faces_to_open = json.loads(open_faces) if isinstance(open_faces, str) else open_faces

                openings = [select_face(shape, fd) for fd in faces_to_open]
                result = shape.shell(openings=openings, thickness=-thickness)

                new_entry = shape_to_model_entry(result, code=f"shell of {source_name}, thickness={thickness}")
                store.put(name, new_entry)

                log.info("model_shelled", extra={
                    "request_id": rid, "model_name": name, "thickness": thickness,
                    "open_faces": faces_to_open,
                })

                return json.dumps({
                    "success": True, "name": name, "source": source_name,
                    "thickness_mm": thickness, "open_faces": faces_to_open,
                    "bbox": new_entry["bbox"], "volume": new_entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("shell_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def split_model(name: str, source_name: str, plane: str = "XY", keep: str = "both") -> str:
        """Split a model along a plane.

        Args:
            name: Base name for the resulting model(s)
            source_name: Name of the source model to split
            plane: Split plane - "XY", "XZ", "YZ", or JSON like '{"axis": "Z", "offset": 10.5}'
            keep: Which half to keep - "above", "below", or "both" (default "both").
                If "both", saves as name_above and name_below.
        """
        rid = new_request_id()
        with log_tool_call(log, "split_model", {"name": name, "source": source_name, "plane": plane, "keep": keep}, rid):
            try:
                from build123d import Box, Pos

                entry = store.get_required(source_name)
                shape = entry["shape"]
                bb = shape.bounding_box()

                offset = 0.0
                if plane.startswith("{"):
                    plane_spec = json.loads(plane)
                    axis = plane_spec.get("axis", "Z").upper()
                    offset = plane_spec.get("offset", 0.0)
                else:
                    plane_axis_map = {"XY": "Z", "XZ": "Y", "YZ": "X"}
                    axis = plane_axis_map.get(plane.upper())
                    if axis is None:
                        return json.dumps({"success": False, "error": f"Unknown plane: {plane}. Use XY, XZ, YZ."})

                size = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z) * 4 + 200
                half = size / 2

                if axis == "Z":
                    above_box = Pos(0, 0, offset + half) * Box(size, size, size)
                    below_box = Pos(0, 0, offset - half) * Box(size, size, size)
                elif axis == "Y":
                    above_box = Pos(0, offset + half, 0) * Box(size, size, size)
                    below_box = Pos(0, offset - half, 0) * Box(size, size, size)
                elif axis == "X":
                    above_box = Pos(offset + half, 0, 0) * Box(size, size, size)
                    below_box = Pos(offset - half, 0, 0) * Box(size, size, size)

                results = {}
                if keep in ("above", "both"):
                    above_shape = shape & above_box
                    above_entry = shape_to_model_entry(above_shape, code=f"split {source_name} above {plane}")
                    result_name = f"{name}_above" if keep == "both" else name
                    store.put(result_name, above_entry)
                    results[result_name] = {"bbox": above_entry["bbox"], "volume": above_entry["volume"]}

                if keep in ("below", "both"):
                    below_shape = shape & below_box
                    below_entry = shape_to_model_entry(below_shape, code=f"split {source_name} below {plane}")
                    result_name = f"{name}_below" if keep == "both" else name
                    store.put(result_name, below_entry)
                    results[result_name] = {"bbox": below_entry["bbox"], "volume": below_entry["volume"]}

                log.info("model_split", extra={
                    "request_id": rid, "source": source_name, "plane": plane, "keep": keep,
                    "results": list(results.keys()),
                })

                return json.dumps({
                    "success": True, "source": source_name, "plane": plane,
                    "keep": keep, "results": results,
                }, indent=2)

            except Exception as e:
                log.error("split_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)
