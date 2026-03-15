"""Parametric component tools: enclosures, gears, snap-fits, hinges, dovetails, labels."""

from __future__ import annotations

import json
import math
from typing import Any

from threedp.config import ServerConfig
from threedp.helpers import error_response, shape_to_model_entry, model_dir
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register parametric component tools with the MCP server."""

    @mcp.tool()
    def create_enclosure(name: str, inner_width: float, inner_depth: float, inner_height: float,
                          wall: float = 2.0, lid_type: str = "snap", features: str = "[]") -> str:
        """Generate a parametric electronics enclosure with lid.

        Creates two models: name_body and name_lid.

        Args:
            name: Base name for the enclosure parts
            inner_width: Interior width (X) in mm
            inner_depth: Interior depth (Y) in mm
            inner_height: Interior height (Z) in mm
            wall: Wall thickness in mm (default 2.0)
            lid_type: "snap" for snap-fit lid, "screw" for screw-post lid (default "snap")
            features: JSON list of features, e.g. '["vent_slots", "screw_posts"]'.
                Supported: "vent_slots", "screw_posts", "cable_hole"
        """
        rid = new_request_id()
        with log_tool_call(log, "create_enclosure", {"name": name, "dims": [inner_width, inner_depth, inner_height], "lid_type": lid_type}, rid):
            try:
                from build123d import Box, Cylinder, Pos, Rot

                feat_list = json.loads(features) if isinstance(features, str) else features

                ow = inner_width + 2 * wall
                od = inner_depth + 2 * wall
                oh = inner_height + wall

                # Body
                outer = Pos(0, 0, oh / 2) * Box(ow, od, oh)
                cavity = Pos(0, 0, wall + inner_height / 2) * Box(inner_width, inner_depth, inner_height)
                body = outer - cavity

                # Lip for lid alignment
                lip_h = 2.0
                lip_w = wall / 2
                lip_outer = Pos(0, 0, oh + lip_h / 2) * Box(ow, od, lip_h)
                lip_inner = Pos(0, 0, oh + lip_h / 2) * Box(ow - 2 * lip_w, od - 2 * lip_w, lip_h)
                lip = lip_outer - lip_inner
                body = body + lip

                if "screw_posts" in feat_list:
                    post_r = 3.0
                    post_h = inner_height - 1.0
                    hole_r = 1.25
                    for sx, sy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        px = sx * (inner_width / 2 - post_r - 1)
                        py = sy * (inner_depth / 2 - post_r - 1)
                        post = Pos(px, py, wall + post_h / 2) * Cylinder(post_r, post_h)
                        hole = Pos(px, py, wall + post_h / 2) * Cylinder(hole_r, post_h)
                        body = body + post - hole

                if "vent_slots" in feat_list:
                    slot_w = 1.5
                    slot_h = inner_height * 0.6
                    slot_spacing = 4.0
                    n_slots = int(inner_width * 0.6 / slot_spacing)
                    start_x = -(n_slots - 1) * slot_spacing / 2
                    for i in range(n_slots):
                        sx = start_x + i * slot_spacing
                        slot = Pos(sx, od / 2, wall + inner_height * 0.3 + slot_h / 2) * Box(slot_w, wall + 1, slot_h)
                        body = body - slot

                if "cable_hole" in feat_list:
                    cable_r = 3.0
                    cable_hole = Pos(0, -od / 2, wall + inner_height / 2) * (Rot(90, 0, 0) * Cylinder(cable_r, wall + 1))
                    body = body - cable_hole

                # Lid
                lid_clearance = 0.2
                lid = Pos(0, 0, wall / 2) * Box(ow, od, wall)
                if lid_type == "snap":
                    ridge_h = lip_h - lid_clearance
                    ridge_outer = Pos(0, 0, wall + ridge_h / 2) * Box(
                        ow - 2 * lip_w - lid_clearance, od - 2 * lip_w - lid_clearance, ridge_h)
                    ridge_inner = Pos(0, 0, wall + ridge_h / 2) * Box(
                        ow - 2 * lip_w - lid_clearance - 2 * lip_w, od - 2 * lip_w - lid_clearance - 2 * lip_w, ridge_h)
                    lid = lid + (ridge_outer - ridge_inner)
                elif lid_type == "screw":
                    hole_r = 1.5
                    for sx, sy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        px = sx * (inner_width / 2 - 3.0 - 1)
                        py = sy * (inner_depth / 2 - 3.0 - 1)
                        screw_hole = Pos(px, py, 0) * Cylinder(hole_r, wall + 1)
                        lid = lid - screw_hole

                body_entry = shape_to_model_entry(body, code=f"enclosure body {inner_width}x{inner_depth}x{inner_height}")
                lid_entry = shape_to_model_entry(lid, code=f"enclosure lid for {name}")
                store.put(f"{name}_body", body_entry)
                store.put(f"{name}_lid", lid_entry)

                log.info("enclosure_created", extra={
                    "request_id": rid, "name": name, "lid_type": lid_type, "features": feat_list,
                })

                return json.dumps({
                    "success": True,
                    "body": {"name": f"{name}_body", "bbox": body_entry["bbox"], "volume": body_entry["volume"]},
                    "lid": {"name": f"{name}_lid", "bbox": lid_entry["bbox"], "volume": lid_entry["volume"]},
                    "inner_dimensions": [inner_width, inner_depth, inner_height],
                    "outer_dimensions": [ow, od, oh],
                    "wall_thickness": wall, "lid_type": lid_type, "features": feat_list,
                }, indent=2)

            except Exception as e:
                log.error("create_enclosure_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def create_snap_fit(name: str, snap_type: str = "cantilever", params: str = "{}") -> str:
        """Generate a snap-fit joint component for assembly.

        Args:
            name: Name for the snap-fit model
            snap_type: Joint type - "cantilever" (default)
            params: JSON parameters. For cantilever:
                beam_length (10), beam_width (5), beam_thickness (1.5),
                hook_depth (1.0), hook_length (2.0), clearance (0.2)
        """
        rid = new_request_id()
        with log_tool_call(log, "create_snap_fit", {"name": name, "snap_type": snap_type}, rid):
            try:
                from build123d import Box, Pos

                p = json.loads(params) if isinstance(params, str) else params

                if snap_type == "cantilever":
                    bl = p.get("beam_length", 10.0)
                    bw = p.get("beam_width", 5.0)
                    bt = p.get("beam_thickness", 1.5)
                    hd = p.get("hook_depth", 1.0)
                    hl = p.get("hook_length", 2.0)

                    beam = Pos(bt / 2, 0, bl / 2) * Box(bt, bw, bl)
                    hook = Pos(bt / 2 + hd / 2, 0, bl - hl / 2) * Box(hd, bw, hl)
                    base_tab = Pos(bt / 2, 0, -bt / 2) * Box(bt + hd, bw, bt)
                    result = beam + hook + base_tab
                else:
                    return json.dumps({"success": False, "error": f"Unknown snap_type: {snap_type}. Supported: cantilever"})

                entry = shape_to_model_entry(result, code=f"snap_fit {snap_type}")
                store.put(name, entry)

                log.info("snap_fit_created", extra={"request_id": rid, "name": name, "type": snap_type})

                return json.dumps({
                    "success": True, "name": name, "type": snap_type, "params": p,
                    "bbox": entry["bbox"], "volume": entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("create_snap_fit_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def create_gear(name: str, module: float = 1.0, teeth: int = 20, pressure_angle: float = 20.0,
                    thickness: float = 5.0, bore: float = 0.0) -> str:
        """Generate an involute spur gear.

        Args:
            name: Name for the gear model
            module: Gear module in mm — tooth size (default 1.0)
            teeth: Number of teeth (default 20)
            pressure_angle: Pressure angle in degrees (default 20)
            thickness: Gear thickness in mm (default 5)
            bore: Center bore diameter in mm, 0 for solid (default 0)
        """
        rid = new_request_id()
        with log_tool_call(log, "create_gear", {"name": name, "module": module, "teeth": teeth}, rid):
            try:
                from build123d import BuildPart, BuildSketch, Circle, Plane as B3dPlane, Pos, extrude

                # Try bd_warehouse first
                try:
                    from bd_warehouse.gear import SpurGear
                    result = SpurGear(module=module, tooth_count=teeth, thickness=thickness,
                                      pressure_angle=pressure_angle)
                except ImportError:
                    # Fallback: simplified gear generation
                    pa_rad = math.radians(pressure_angle)
                    pitch_r = module * teeth / 2
                    addendum = module
                    dedendum = 1.25 * module
                    outer_r = pitch_r + addendum

                    with BuildPart() as part:
                        with BuildSketch(B3dPlane.XY):
                            Circle(outer_r)
                        extrude(amount=thickness)
                    result = part.part

                    # Simplified tooth notches
                    notch_r = module * 0.8
                    for i in range(teeth):
                        angle = 2 * math.pi * i / teeth + math.pi / teeth
                        nx = pitch_r * math.cos(angle)
                        ny = pitch_r * math.sin(angle)
                        from build123d import Cylinder
                        notch = Pos(nx, ny, thickness / 2) * Cylinder(notch_r, thickness)
                        result = result - notch

                if bore > 0:
                    from build123d import Cylinder
                    bore_hole = Pos(0, 0, thickness / 2) * Cylinder(bore / 2, thickness)
                    result = result - bore_hole

                entry = shape_to_model_entry(result, code=f"spur gear m={module} z={teeth} pa={pressure_angle}")
                store.put(name, entry)

                log.info("gear_created", extra={
                    "request_id": rid, "name": name, "teeth": teeth, "module": module,
                })

                return json.dumps({
                    "success": True, "name": name, "module": module, "teeth": teeth,
                    "pressure_angle": pressure_angle,
                    "pitch_diameter": round(module * teeth, 2),
                    "outer_diameter": round(module * teeth + 2 * module, 2),
                    "thickness": thickness, "bore": bore,
                    "bbox": entry["bbox"], "volume": entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("create_gear_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def create_hinge(name: str, hinge_type: str = "pin", params: str = "{}") -> str:
        """Generate a two-part hinge assembly.

        Creates two models: name_leaf_a and name_leaf_b.

        Args:
            name: Base name for the hinge parts
            hinge_type: Hinge type - "pin" (default)
            params: JSON parameters:
                width (30), leaf_length (20), leaf_thickness (2),
                pin_diameter (3), clearance (0.3), barrel_count (3)
        """
        rid = new_request_id()
        with log_tool_call(log, "create_hinge", {"name": name, "hinge_type": hinge_type}, rid):
            try:
                from build123d import Box, Cylinder, Pos, Rot

                p = json.loads(params) if isinstance(params, str) else params
                width = p.get("width", 30.0)
                leaf_len = p.get("leaf_length", 20.0)
                leaf_t = p.get("leaf_thickness", 2.0)
                pin_d = p.get("pin_diameter", 3.0)
                clearance = p.get("clearance", 0.3)
                barrel_count = p.get("barrel_count", 3)

                barrel_r = pin_d / 2 + leaf_t
                total_segments = barrel_count * 2 + 1
                seg_width = width / total_segments

                leaf_a = Pos(0, -leaf_len / 2, leaf_t / 2) * Box(width, leaf_len, leaf_t)
                leaf_b = Pos(0, leaf_len / 2, leaf_t / 2) * Box(width, leaf_len, leaf_t)

                for i in range(total_segments):
                    bx = -width / 2 + seg_width * (i + 0.5)
                    barrel = Pos(bx, 0, barrel_r) * (Rot(0, 90, 0) * Cylinder(barrel_r, seg_width))
                    if i % 2 == 0:
                        leaf_a = leaf_a + barrel
                    else:
                        leaf_b = leaf_b + barrel

                pin_hole = Pos(0, 0, barrel_r) * (Rot(0, 90, 0) * Cylinder(pin_d / 2 + clearance / 2, width + 2))
                leaf_a = leaf_a - pin_hole
                leaf_b = leaf_b - pin_hole

                entry_a = shape_to_model_entry(leaf_a, code="hinge leaf A")
                entry_b = shape_to_model_entry(leaf_b, code="hinge leaf B")
                store.put(f"{name}_leaf_a", entry_a)
                store.put(f"{name}_leaf_b", entry_b)

                log.info("hinge_created", extra={"request_id": rid, "name": name, "type": hinge_type})

                return json.dumps({
                    "success": True,
                    "leaf_a": {"name": f"{name}_leaf_a", "bbox": entry_a["bbox"], "volume": entry_a["volume"]},
                    "leaf_b": {"name": f"{name}_leaf_b", "bbox": entry_b["bbox"], "volume": entry_b["volume"]},
                    "params": {"width": width, "leaf_length": leaf_len, "pin_diameter": pin_d,
                               "barrel_count": barrel_count, "clearance": clearance},
                }, indent=2)

            except Exception as e:
                log.error("create_hinge_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def create_dovetail(name: str, dovetail_type: str = "male", width: float = 20.0, height: float = 10.0,
                         depth: float = 15.0, angle: float = 10.0, clearance: float = 0.2) -> str:
        """Generate a dovetail joint (male or female) for multi-part assemblies.

        Args:
            name: Name for the dovetail model
            dovetail_type: "male" or "female" (default "male")
            width: Base width in mm (default 20)
            height: Height in mm (default 10)
            depth: Extrusion depth in mm (default 15)
            angle: Dovetail angle in degrees (default 10)
            clearance: Fit clearance in mm, applied to female only (default 0.2)
        """
        rid = new_request_id()
        with log_tool_call(log, "create_dovetail", {"name": name, "type": dovetail_type, "width": width, "height": height}, rid):
            try:
                from build123d import Box, Pos, BuildPart, BuildSketch, BuildLine, Plane as B3dPlane, Line, make_face, extrude

                angle_rad = math.radians(angle)
                taper = height * math.tan(angle_rad)
                top_half = width / 2 + taper
                bot_half = width / 2

                if dovetail_type == "female":
                    bot_half += clearance
                    top_half += clearance
                    height += clearance

                with BuildPart() as part:
                    with BuildSketch(B3dPlane.XY):
                        with BuildLine():
                            Line((-bot_half, 0), (-top_half, height))
                            Line((-top_half, height), (top_half, height))
                            Line((top_half, height), (bot_half, 0))
                            Line((bot_half, 0), (-bot_half, 0))
                        make_face()
                    extrude(amount=depth)

                if dovetail_type == "female":
                    block_w = width + 2 * taper + 4 * clearance + 4
                    block_h = height + clearance + 2
                    block = Pos(0, block_h / 2, depth / 2) * Box(block_w, block_h, depth)
                    result = block - part.part
                else:
                    result = part.part

                entry = shape_to_model_entry(result, code=f"dovetail {dovetail_type} {width}x{height}x{depth}")
                store.put(name, entry)

                log.info("dovetail_created", extra={
                    "request_id": rid, "name": name, "type": dovetail_type,
                    "width": width, "height": height, "angle": angle,
                })

                return json.dumps({
                    "success": True, "name": name, "type": dovetail_type,
                    "width": width, "height": height, "depth": depth,
                    "angle": angle, "clearance": clearance,
                    "bbox": entry["bbox"], "volume": entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("create_dovetail_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def generate_label(name: str, text: str, size: str = "[60, 20, 2]", font_size: float = 8.0,
                        qr_data: str = "") -> str:
        """Generate a 3D-printable label with embossed text and optional QR code.

        Args:
            name: Name for the label model
            text: Text to emboss on the label
            size: JSON [width, height, thickness] in mm (default [60, 20, 2])
            font_size: Font size in mm (default 8)
            qr_data: Data to encode as QR code (optional, empty string to skip)
        """
        rid = new_request_id()
        with log_tool_call(log, "generate_label", {"name": name, "text": text, "has_qr": bool(qr_data)}, rid):
            try:
                from build123d import Box, Pos, BuildPart, BuildSketch, Text as B3dText, Plane as B3dPlane, extrude, export_stl

                dims = json.loads(size) if isinstance(size, str) else size
                w, h, t = dims[0], dims[1], dims[2]
                text_depth = 0.6

                plate = Pos(0, 0, t / 2) * Box(w, h, t)

                with BuildPart() as text_part:
                    with BuildSketch(B3dPlane.XY.offset(t)):
                        B3dText(text, font_size)
                    extrude(amount=text_depth)
                result = plate + text_part.part

                if qr_data:
                    try:
                        import qrcode
                        qr = qrcode.QRCode(box_size=1, border=1)
                        qr.add_data(qr_data)
                        qr.make(fit=True)
                        matrix = qr.get_matrix()
                        qr_rows = len(matrix)
                        qr_cols = len(matrix[0]) if qr_rows > 0 else 0

                        qr_area = min(h * 0.8, w * 0.3)
                        module_size = qr_area / max(qr_rows, qr_cols)
                        qr_origin_x = w / 2 - qr_area / 2 - 2
                        qr_origin_y = -qr_area / 2

                        for row in range(qr_rows):
                            for col in range(qr_cols):
                                if matrix[row][col]:
                                    mx = qr_origin_x + col * module_size
                                    my = qr_origin_y + (qr_rows - 1 - row) * module_size
                                    mod = Pos(mx, my, t + text_depth / 2) * Box(module_size, module_size, text_depth)
                                    result = result + mod
                    except ImportError:
                        pass

                entry = shape_to_model_entry(result, code=f"label '{text}'")
                store.put(name, entry)

                d = model_dir(config.output_dir, name)
                stl_path = d / f"{name}.stl"
                export_stl(result, str(stl_path))

                log.info("label_generated", extra={
                    "request_id": rid, "name": name, "text": text, "has_qr": bool(qr_data),
                })

                return json.dumps({
                    "success": True, "name": name, "text": text, "size_mm": dims,
                    "has_qr": bool(qr_data), "stl_path": str(stl_path),
                    "bbox": entry["bbox"], "volume": entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("generate_label_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)
