#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$ROOT_DIR/.git/hooks"
SOURCE_HOOK="$ROOT_DIR/.git-hooks/commit-msg"
TARGET_HOOK="$HOOKS_DIR/commit-msg"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

if [[ ! -d "$ROOT_DIR/.git" ]]; then
  echo "❌ Not a git repository: $ROOT_DIR" >&2
  exit 1
fi

if [[ -d "$ROOT_DIR/.venv" ]]; then
  echo "Found existing virtual environment: .venv"
else
  echo "No .venv found"
fi

if command -v python"$PYTHON_VERSION" >/dev/null 2>&1; then
  echo "Found python$PYTHON_VERSION"
elif command -v python3 >/dev/null 2>&1; then
  echo "Found python3, but not python$PYTHON_VERSION"
else
  echo "No suitable Python runtime found"
fi

if command -v docker >/dev/null 2>&1; then
  echo "Found docker"
else
  echo "Docker is not installed"
fi

mkdir -p "$HOOKS_DIR"
cp "$SOURCE_HOOK" "$TARGET_HOOK"
chmod +x "$TARGET_HOOK"

echo "Installed commit-msg hook to .git/hooks/commit-msg"
