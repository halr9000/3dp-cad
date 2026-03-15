#!/usr/bin/env python3
"""3DP CAD MCP Server — Entry point.

A modular, cross-platform MCP server for 3D-printable CAD modeling
with build123d, featuring robust logging and configuration.

Usage:
    python server.py              # stdio transport (default)
    THREEDP_LOG_LEVEL=DEBUG python server.py  # with debug logging
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from threedp.config import get_config
from threedp.logging_config import get_logger
from threedp.model_store import get_store

# ── Initialization ───────────────────────────────────────────────────────────

config = get_config()
store = get_store()
log = get_logger()

log.info("server_initializing", extra={
    "server_name": config.server_name,
    "output_dir": str(config.output_dir),
    "log_level": config.log_level,
    "printer": config.printer_description(),
})

# ── MCP Server ───────────────────────────────────────────────────────────────

mcp = FastMCP(config.server_name)

# ── Register Tools ───────────────────────────────────────────────────────────

from threedp.tools import core, transforms, analysis, features, parametric, community, export_2d

core.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "core", "count": 6})

transforms.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "transforms", "count": 4})

analysis.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "analysis", "count": 6})

features.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "features", "count": 6})

parametric.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "parametric", "count": 6})

community.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "community", "count": 5})

export_2d.register_tools(mcp, store, config)
log.info("tools_registered", extra={"module": "export_2d", "count": 1})

log.info("server_ready", extra={"total_tools": 34, "transport": config.transport})

# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport=config.transport)
