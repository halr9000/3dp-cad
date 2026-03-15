---
name: 3dp-cad
description: >
  3D-printable CAD modeling with build123d. Creates, analyzes, transforms, and publishes
  3D models as STL/STEP files for FDM printing (Bambu Lab X1C and similar).
  Use when: creating 3D models from parametric code, analyzing printability,
  estimating print costs, generating gears/enclosures/hinges/dovetails,
  adding threaded holes or text to models, splitting for multi-color printing,
  publishing to Thingiverse/GitHub/MyMiniFactory/Cults3D, or converting
  between 3D file formats. Also triggers on: build123d, CAD modeling, 3D printing
  analysis, STL generation, print orientation optimization.
---

# 3DP CAD Skill

A cross-platform MCP server for 3D-printable CAD modeling using [build123d](https://build123d.readthedocs.io/).

## Architecture

```
src/threedp/
├── server.py          # MCP server entry point
├── config.py          # Configuration from env vars
├── model_store.py     # Thread-safe model registry
├── constants.py       # Material/thread tables
├── helpers.py         # Shared geometry utilities
├── logging_config.py  # Structured JSON logging
└── tools/
    ├── core.py        # create, export, measure, list, import, get_code
    ├── transforms.py  # transform, combine, shell, split
    ├── analysis.py    # printability, overhangs, orientation, estimate, section, drawing
    ├── features.py    # text, threads, shrinkage, pack, convert, color_split
    ├── parametric.py  # enclosure, gear, snap_fit, hinge, dovetail, label
    └── community.py   # search, publish_github, publish_thingiverse, publish_myminifactory, publish_cults3d
```

## Quick Start

### 1. Install Dependencies

```bash
cd src/threedp
pip install "build123d>=0.7" "mcp[cli]>=1.0" "bd_warehouse" "qrcode>=7.0"
```

Or use the setup scripts:
- **macOS/Linux:** `bash setup.sh`
- **Windows:** `powershell -ExecutionPolicy Bypass -File setup.ps1`

### 2. Register with Claude Code

```bash
claude mcp add 3dp-mcp-server python src/threedp/server.py -s user
```

### 3. Use It

Ask Claude:
- "Create a 50x40x10mm box with 2mm fillets on all edges"
- "Analyze printability of my_box"
- "Suggest the best print orientation"
- "Create a 20-tooth spur gear with 5mm bore"

## Configuration

All settings configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `THREEDP_OUTPUT_DIR` | `./outputs` | Where STL/STEP files are saved |
| `THREEDP_LOG_DIR` | `./logs` | Log file directory |
| `THREEDP_LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `THREEDP_PRINTER` | `Bambu Lab X1C` | Printer name |
| `THREEDP_BUILD_X/Y/Z` | `256` | Build volume dimensions (mm) |
| `THREEDP_DEFAULT_MATERIAL` | `PLA` | Default filament material |
| `THINGIVERSE_API_KEY` | — | For model search |
| `THINGIVERSE_TOKEN` | — | For publishing to Thingiverse |
| `GITHUB_TOKEN` | — | For GitHub Releases (alternative to `gh` CLI) |
| `MYMINIFACTORY_TOKEN` | — | For publishing to MyMiniFactory |
| `CULTS3D_API_KEY` | — | For publishing to Cults3D |

## Logging

Structured JSON logs go to both stderr and rotating log files (`logs/server.log`).

Every tool call logs:
- Tool name, request ID, arguments (sanitized)
- Duration in milliseconds
- Success/failure status
- Model metadata (bbox, volume) for geometry operations
- File sizes for export operations

Example log entry:
```json
{
  "timestamp": "2026-03-15T01:23:45.678Z",
  "level": "INFO",
  "logger": "threedp",
  "message": "tool_invocation_complete",
  "request_id": "a1b2c3d4",
  "tool": "create_model",
  "duration_ms": 142.3,
  "success": true
}
```

## All 33 MCP Tools

### Core (6)
`create_model` · `export_model` · `measure_model` · `list_models` · `get_model_code` · `import_model`

### Transforms (4)
`transform_model` · `combine_models` · `shell_model` · `split_model`

### Analysis (6)
`analyze_printability` · `analyze_overhangs` · `suggest_orientation` · `estimate_print` · `section_view` · `export_drawing`

### Features (6)
`add_text` · `create_threaded_hole` · `shrinkage_compensation` · `pack_models` · `convert_format` · `split_model_by_color`

### Parametric (6)
`create_enclosure` · `create_gear` · `create_snap_fit` · `create_hinge` · `create_dovetail` · `generate_label`

### Community (5)
`search_models` · `publish_github_release` · `publish_thingiverse` · `publish_myminifactory` · `publish_cults3d`

## Design Guidelines for FDM Printing

- Minimum wall thickness: 0.8mm (prefer 1.2mm+)
- Minimum hole diameter: 2mm
- Fillet radii: 0.5–2mm for printability
- Overhangs: keep under 45° or design for supports
- Units: always millimeters
- Tolerances: add 0.2mm clearance for press-fit joints
- Always run `analyze_printability` before declaring a model done
