#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "==> agent-memory-mcp installer"
echo "    Repo: $SCRIPT_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "==> Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
else
    echo "==> Virtual environment already exists at $VENV_DIR, skipping creation."
fi

# Activate and upgrade pip
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

# Install production dependencies
echo "==> Installing production dependencies ..."
pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "✅ Installation complete!"
echo ""
echo "   Python interpreter : $VENV_DIR/bin/python"
echo "   Server script      : $SCRIPT_DIR/server.py"
echo ""
echo "── Add this to ~/.gemini/settings.json ──────────────────────────────────────"
echo '{
  "mcpServers": {
    "agent-memory": {
      "command": "'"$VENV_DIR/bin/python"'",
      "args": ["'"$SCRIPT_DIR/server.py"'"],
      "env": {
        "MEMORY_CWD": "${workspaceFolder}"
      }
    }
  }
}'
echo "─────────────────────────────────────────────────────────────────────────────"
