#!/usr/bin/env bash
set -euo pipefail

PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG_ROOT"

command -v rbnx >/dev/null 2>&1 || {
  echo "rbnx is required to locate robonix-api." >&2
  exit 127
}

RUNTIME_DIR="${RBNX_RUNTIME_DIR:-$PKG_ROOT/.run}"
mkdir -p "$RUNTIME_DIR"
printf '%s\n' "$$" > "$RUNTIME_DIR/vla-action-decision.pid"

export PYTHONPATH="$(rbnx path robonix-api):$PKG_ROOT:${PYTHONPATH:-}"
exec python3 -m vla_action_service.main
