#!/usr/bin/env bash
set -euo pipefail

PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

command -v rbnx >/dev/null 2>&1 || {
  echo "rbnx is required; install the RoboNix CLI before building." >&2
  exit 127
}

rbnx codegen -p "$PKG_ROOT" --mcp
python3 -m compileall -q "$PKG_ROOT/vla_action_service"
