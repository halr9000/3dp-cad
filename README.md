# 3DP CAD MCP Server

MCP server for 3D-printable CAD modeling with build123d, targeting STL export for FDM 3D printers.

## Features

- **33 MCP tools** for complete CAD workflow
- **Cross-platform**: macOS, Linux, Windows
- **Structured logging**: JSON logs with request correlation, timing, and file rotation
- **Modular architecture**: Clean separation of concerns across 6 tool domains
- **Parametric components**: Enclosures, gears, snap-fits, hinges, dovetails, labels
- **Multi-platform publishing**: Thingiverse, GitHub Releases, MyMiniFactory, Cults3D
- **Print analysis**: Overhang detection, orientation optimization, cost estimation

## Quick Start

```bash
# Clone
git clone https://github.com/brs077/3dp-mcp-server.git
cd 3dp-mcp-server

# Setup (pick your platform)
bash setup.sh           # macOS / Linux
# OR
powershell -ExecutionPolicy Bypass -File setup.ps1   # Windows
```

That's it. Start a new Claude Code session and ask it to create a model.

## Architecture

```
src/threedp/
├── server.py          # Entry point, wires everything together
├── config.py          # Configuration from environment variables
├── model_store.py     # Thread-safe in-memory model registry
├── constants.py       # Material properties, thread tables, view directions
├── helpers.py         # Shared geometry utilities (face selection, overhang analysis)
├── logging_config.py  # Structured JSON logging with request correlation
└── tools/
    ├── core.py        # create, export, measure, list, import, get_code
    ├── transforms.py  # transform, combine, shell, split
    ├── analysis.py    # printability, overhangs, orientation, estimate, section, drawing
    ├── features.py    # text, threads, shrinkage, pack, convert, color_split
    ├── parametric.py  # enclosure, gear, snap_fit, hinge, dovetail, label
    └── community.py   # search, publish_github, publish_thingiverse, publish_myminifactory, publish_cults3d
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `THREEDP_OUTPUT_DIR` | `./outputs` | Output directory for STL/STEP files |
| `THREEDP_LOG_DIR` | `./logs` | Log file directory |
| `THREEDP_LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |
| `THREEDP_PRINTER` | `Bambu Lab X1C` | Target printer name |
| `THREEDP_BUILD_X/Y/Z` | `256` | Build volume dimensions (mm) |
| `THINGIVERSE_API_KEY` | — | For model search |
| `THINGIVERSE_TOKEN` | — | For publishing to Thingiverse |
| `GITHUB_TOKEN` | — | For GitHub Releases (alternative to `gh` CLI) |
| `MYMINIFACTORY_TOKEN` | — | For publishing to MyMiniFactory |
| `CULTS3D_API_KEY` | — | For publishing to Cults3D |

## Tool Reference

### Core Tools
- `create_model(name, code)` — Execute build123d code, auto-exports STL. Code must assign final shape to `result`.
- `export_model(name, format)` — Export to STL, STEP, or 3MF
- `measure_model(name)` — Bounding box, volume, face/edge counts
- `list_models()` — All models in current session
- `get_model_code(name)` — Retrieve the code used to create a model
- `import_model(name, file_path)` — Import STL or STEP from disk

### Transform Tools
- `transform_model(name, source, operations)` — Scale, rotate, mirror, or translate
- `combine_models(name, a, b, operation)` — Boolean union/subtract/intersect
- `shell_model(name, source, thickness, open_faces)` — Hollow out with wall thickness
- `split_model(name, source, plane, keep)` — Split along XY/XZ/YZ plane

### Analysis Tools
- `analyze_printability(name, min_wall_mm)` — Watertight check, thin wall detection
- `analyze_overhangs(name, max_angle)` — Find overhang faces needing support
- `suggest_orientation(name)` — Optimal print orientation (minimize supports)
- `estimate_print(name, infill, layer_height, material)` — Filament usage, weight, cost
- `section_view(name, source, plane, offset)` — 2D cross-section as SVG
- `export_drawing(name, views, page_size)` — Multi-view technical drawing as SVG

### Feature Tools
- `add_text(name, source, text, face, ...)` — Emboss or deboss text onto a face
- `create_threaded_hole(name, source, position, thread_spec, depth, insert)` — Threaded/insert holes (M2–M10)
- `shrinkage_compensation(name, source, material)` — Scale for material shrinkage
- `pack_models(name, model_names, padding)` — Arrange on build plate for batch printing
- `convert_format(input, output)` — Convert between STL, STEP, 3MF, BREP
- `split_model_by_color(name, source, assignments)` — Split for multi-color printing

### Parametric Components
- `create_enclosure(name, w, d, h, wall, lid_type, features)` — Electronics enclosure with lid
- `create_gear(name, module, teeth, pressure_angle, thickness, bore)` — Involute spur gear
- `create_snap_fit(name, type, params)` — Cantilever snap-fit joints
- `create_hinge(name, type, params)` — Two-part pin hinge assembly
- `create_dovetail(name, type, width, height, depth, angle, clearance)` — Male/female dovetail joints
- `generate_label(name, text, size, font_size, qr_data)` — 3D-printable label with optional QR code

### Community & Publishing
- `search_models(query, source, max_results)` — Search Thingiverse for 3D models
- `publish_github_release(name, repo, tag, description, formats, draft)` — Upload to GitHub Releases
- `publish_thingiverse(name, title, description, tags, category, is_wip)` — Publish to Thingiverse
- `publish_myminifactory(name, title, description, tags, category_id)` — Publish to MyMiniFactory
- `publish_cults3d(name, title, description, tags, license, free, price_cents)` — Publish to Cults3D

## build123d Coding Patterns

All code runs with `from build123d import *` pre-imported. Assign the final shape to `result`.

```python
# Basic shapes
result = Box(width, depth, height)
result = Cylinder(radius, height)

# Boolean operations
result = Box(50, 40, 10) - Cylinder(5, 10)  # subtract

# Positioning
hole = Pos(10, 0, 0) * Cylinder(3, 10)
result = Box(50, 40, 10) - hole

# Fillets and chamfers
result = fillet(result.edges(), radius=1)
```

## Design Guidelines (FDM Printing)

- Minimum wall thickness: 0.8mm (prefer 1.2mm+)
- Minimum hole diameter: 2mm
- Fillet radii: 0.5–2mm for printability
- Overhangs: keep under 45° or design for supports
- Units: always millimeters
- Tolerances: add 0.2mm clearance for press-fit joints

## License

[CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) — personal use and sharing with attribution. No commercial use or modified redistribution.
