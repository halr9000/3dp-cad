#!/bin/bash
set -e

# 3DP CAD MCP Server — Setup Script for macOS / Linux
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SRC_DIR="$SCRIPT_DIR/src/threedp"

echo "=== 3DP CAD MCP Server Setup ==="
echo ""

PYTHON=""
for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$("$cmd" -c "import sys; print(sys.version_info.major)")
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)")
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ] && [ "$minor" -le 12 ]; then
            PYTHON="$cmd"
            echo "[OK] Found $cmd ($version)"
            break
        fi
    fi
done

# Check for Python 3.14+ which requires conda
if [ -z "$PYTHON" ] && command -v python3 &>/dev/null; then
    version=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$version" -ge 14 ]; then
        echo "[WARN] Python 3.14+ detected. build123d requires conda for this Python version."
        echo ""
        echo "Option 1: Use Conda (recommended for Python 3.14+)"
        echo "  curl -L -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
        echo "  bash /tmp/miniforge.sh -b -p \"\$HOME/.miniforge\""
        echo "  export PATH=\"\$HOME/.miniforge/bin:\$PATH\""
        echo "  mamba create -n 3dp-cad python=3.12 -y"
        echo "  mamba install -n 3dp-cad -c conda-forge cadquery ocp -y"
        echo "  mamba run -n 3dp-cad pip install build123d mcp pillow cairosvg matplotlib trimesh"
        echo ""
        echo "Option 2: Install Python 3.11 or 3.12"
        echo "  brew install python@3.12  (macOS)"
        echo "  apt install python3.12 python3.12-venv (Linux)"
        echo ""
        read -p "Continue with conda setup? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            if ! command -v mamba &>/dev/null; then
                echo "[INFO] Installing Miniforge..."
                curl -L -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
                bash /tmp/miniforge.sh -b -p "$HOME/.miniforge"
                export PATH="$HOME/.miniforge/bin:$PATH"
            fi
            export PATH="$HOME/.miniforge/bin:$PATH"
            echo "[INFO] Creating conda environment '3dp-cad' with Python 3.12..."
            mamba create -n 3dp-cad python=3.12 -y
            echo "[INFO] Installing cadquery and OCP..."
            mamba install -n 3dp-cad -c conda-forge cadquery ocp -y
            echo "[INFO] Installing Python packages..."
            mamba run -n 3dp-cad pip install build123d mcp pillow cairosvg matplotlib trimesh
            echo "[OK] Conda environment '3dp-cad' ready."
            echo ""
            echo "To use: export PATH=\"\$HOME/.miniforge/bin:\$PATH\" && mamba run -n 3dp-cad python src/threedp/server.py"
            exit 0
        else
            exit 1
        fi
    fi
fi

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.11-3.12 is required but not found."
    echo "Install with: brew install python@3.12  (macOS) or apt install python3.12 (Linux)"
    exit 1
fi

echo ""
echo "Creating virtual environment..."
"$PYTHON" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "Installing dependencies (this may take a few minutes for build123d)..."
pip install --upgrade pip -q
pip install "build123d>=0.7" "mcp[cli]>=1.0" "bd_warehouse" "qrcode>=7.0" "matplotlib" "trimesh" -q

echo ""
echo "[OK] Dependencies installed"

echo "Verifying build123d..."
python3 -c "from build123d import Box; b = Box(10,10,10); print(f'[OK] build123d works — test cube volume: {b.volume:.1f} mm³')"

echo "Verifying MCP..."
python3 -c "from mcp.server.fastmcp import FastMCP; print('[OK] MCP server framework works')"

mkdir -p "$SCRIPT_DIR/outputs" "$SCRIPT_DIR/logs"

echo ""
echo "Registering MCP server with Claude Code..."
if command -v claude &>/dev/null; then
    claude mcp add 3dp-mcp-server \
        "$VENV_DIR/bin/python3" "$SRC_DIR/server.py" \
        -s user
    echo "[OK] MCP server registered with Claude Code"
else
    echo "[SKIP] 'claude' CLI not found in PATH."
    echo "  Run this manually after installing Claude Code:"
    echo ""
    echo "  claude mcp add 3dp-mcp-server $VENV_DIR/bin/python3 $SRC_DIR/server.py -s user"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To verify, start Claude Code and ask:"
echo '  "What MCP servers are available?"'
echo ""
echo "Then try:"
echo '  "Create a 50x40x10mm box with 2mm fillets on all edges"'
echo ""
echo "Output files: $SCRIPT_DIR/outputs/"
echo "Log files:    $SCRIPT_DIR/logs/"
