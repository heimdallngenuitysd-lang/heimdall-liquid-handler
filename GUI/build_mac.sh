#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3.12}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtual environment in GUI/.venv ..."
  "$PYTHON" -m venv .venv
fi

echo "Installing packages into .venv ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt pyinstaller

echo "Building LiquidHandler.app ..."
.venv/bin/python -m PyInstaller --noconfirm LiquidHandler.spec

echo "Done. Double-click: dist/LiquidHandler.app"
echo "Packages live only in GUI/.venv and will not change your other Python installs."
