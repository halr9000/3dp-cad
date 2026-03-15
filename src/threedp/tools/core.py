"""Core model tools: create, export, measure, list, import, get code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from threedp.config import ServerConfig
from threedp.helpers import (
    error_response,
    model_dir,
    run_build123d_code,
    shape_to_model_entry,
)
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.metadata import (
    create_metadata,
    embed_stl_metadata,
    embed_step_metadata,
    embed_3mf_metadata,
)
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register core tools with the MCP server.

    Args:
        mcp: FastMCP server instance
        store: Model store instance
        config: Server configuration
    """

    @mcp.tool()
    def create_model(name: str, code: str) -> str:
        """Create a 3D model by executing build123d Python code.

        The code MUST assign the final shape to a variable called `result`.
        All build123d imports are available automatically.

        Args:
            name: A short name for the model (used for file naming)
            code: build123d Python code that creates a shape and assigns it to `result`

        Returns:
            JSON with success status, geometry info (bounding box, volume), and output paths.
        """
        rid = new_request_id()
        with log_tool_call(log, "create_model", {"name": name, "code_len": len(code)}, rid):
            try:
                if "from build123d" not in code and "import build123d" not in code:
                    code = "from build123d import *\n" + code

                result = run_build123d_code(code)
                store.put(name, result)

                d = model_dir(config.output_dir, name)
                from build123d import export_stl, export_step
                stl_path = d / f"{name}.stl"
                step_path = d / f"{name}.step"
                export_stl(result["shape"], str(stl_path))
                export_step(result["shape"], str(step_path))

                # Embed metadata in 3D files
                metadata = create_metadata(
                    model_name=name,
                    source_code=code,
                    view_angle="3d",
                    export_format="stl",
                )
                embed_stl_metadata(stl_path, metadata)
                metadata["export_format"] = "step"
                embed_step_metadata(step_path, metadata)

                log.info("model_created", extra={
                    "request_id": rid, "model_name": name,
                    "bbox": result["bbox"], "volume": result["volume"],
                    "stl_path": str(stl_path), "step_path": str(step_path),
                })

                return json.dumps({
                    "success": True,
                    "name": name,
                    "bbox": result["bbox"],
                    "volume": result["volume"],
                    "outputs": {"stl": str(stl_path), "step": str(step_path)},
                }, indent=2)

            except Exception as e:
                log.error("create_model_failed", extra={"request_id": rid, "model_name": name, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def export_model(name: str, format: str = "stl") -> str:
        """Export a model to STL, STEP, or 3MF format.

        Args:
            name: Name of a previously created model
            format: Export format - "stl", "step", or "3mf"
        """
        rid = new_request_id()
        with log_tool_call(log, "export_model", {"name": name, "format": format}, rid):
            try:
                entry = store.get_required(name)
                d = model_dir(config.output_dir, name)

                fmt = format.lower().strip(".")
                out_path = d / f"{name}.{fmt}"

                source_code = entry.get("code", "")
                if fmt == "stl":
                    from build123d import export_stl
                    export_stl(entry["shape"], str(out_path))
                    metadata = create_metadata(
                        model_name=name,
                        source_code=source_code,
                        view_angle="3d",
                        export_format="stl",
                    )
                    embed_stl_metadata(out_path, metadata)
                elif fmt == "step":
                    from build123d import export_step
                    export_step(entry["shape"], str(out_path))
                    metadata = create_metadata(
                        model_name=name,
                        source_code=source_code,
                        view_angle="3d",
                        export_format="step",
                    )
                    embed_step_metadata(out_path, metadata)
                elif fmt == "3mf":
                    from build123d import Mesher
                    with Mesher() as mesher:
                        mesher.add_shape(entry["shape"])
                        mesher.write(str(out_path))
                    metadata = create_metadata(
                        model_name=name,
                        source_code=source_code,
                        view_angle="3d",
                        export_format="3mf",
                    )
                    embed_3mf_metadata(out_path, metadata)
                else:
                    return json.dumps({"success": False, "error": f"Unsupported format: {fmt}"})

                log.info("model_exported", extra={
                    "request_id": rid, "model_name": name, "format": fmt,
                    "path": str(out_path), "file_size": out_path.stat().st_size,
                })

                return json.dumps({"success": True, "path": str(out_path)})

            except Exception as e:
                log.error("export_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def measure_model(name: str) -> str:
        """Measure a model's geometry: bounding box, volume, surface area, and face/edge counts.

        Args:
            name: Name of a previously created model
        """
        rid = new_request_id()
        with log_tool_call(log, "measure_model", {"name": name}, rid):
            try:
                entry = store.get_required(name)
                shape = entry["shape"]
                bb = entry["bbox"]
                measurements: dict[str, Any] = {"name": name, "bbox": bb}

                try:
                    measurements["volume_mm3"] = round(shape.volume, 3)
                except Exception:
                    measurements["volume_mm3"] = None

                try:
                    measurements["area_mm2"] = round(shape.area, 3)
                except Exception:
                    measurements["area_mm2"] = None

                try:
                    measurements["faces"] = len(shape.faces())
                except Exception:
                    measurements["faces"] = None

                try:
                    measurements["edges"] = len(shape.edges())
                except Exception:
                    measurements["edges"] = None

                log.info("model_measured", extra={
                    "request_id": rid, "model_name": name,
                    "volume": measurements.get("volume_mm3"),
                    "faces": measurements.get("faces"),
                })

                return json.dumps(measurements, indent=2)

            except Exception as e:
                log.error("measure_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def list_models() -> str:
        """List all models currently loaded in this session."""
        rid = new_request_id()
        with log_tool_call(log, "list_models", {}, rid):
            models = store.list_models()
            if not models:
                return json.dumps({"models": [], "message": "No models yet. Use create_model to make one."})
            return json.dumps({"models": models}, indent=2)

    @mcp.tool()
    def get_model_code(name: str) -> str:
        """Retrieve the build123d code used to create a model.

        Args:
            name: Name of a previously created model
        """
        rid = new_request_id()
        with log_tool_call(log, "get_model_code", {"name": name}, rid):
            try:
                entry = store.get_required(name)
                return json.dumps({"name": name, "code": entry["code"]})
            except Exception as e:
                log.error("get_model_code_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)

    @mcp.tool()
    def import_model(name: str, file_path: str) -> str:
        """Import an STL or STEP file from disk into the server as a loaded model.

        Args:
            name: Name for the imported model
            file_path: Absolute path to the STL or STEP file
        """
        rid = new_request_id()
        with log_tool_call(log, "import_model", {"name": name, "file_path": file_path}, rid):
            try:
                from pathlib import Path as P
                ext = P(file_path).suffix.lower()

                if ext == ".stl":
                    from build123d import import_stl
                    shape = import_stl(file_path)
                elif ext in (".step", ".stp"):
                    from build123d import import_step
                    shape = import_step(file_path)
                else:
                    return json.dumps({"success": False, "error": f"Unsupported file type: {ext}. Use .stl, .step, or .stp."})

                entry = shape_to_model_entry(shape, code=f"imported from {file_path}")
                store.put(name, entry)

                log.info("model_imported", extra={
                    "request_id": rid, "model_name": name,
                    "file_path": file_path, "bbox": entry["bbox"],
                })

                return json.dumps({
                    "success": True,
                    "name": name,
                    "file": file_path,
                    "bbox": entry["bbox"],
                    "volume": entry["volume"],
                }, indent=2)

            except Exception as e:
                log.error("import_model_failed", extra={"request_id": rid, "error": str(e)})
                return error_response(e)
