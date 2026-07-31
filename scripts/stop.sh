#!/usr/bin/env bash
set -euo pipefail

PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNTIME_DIR="${RBNX_RUNTIME_DIR:-$PKG_ROOT/.run}"
PID_FILE="$RUNTIME_DIR/vla-action-decision.pid"

if [[ ! -f "$PID_FILE" ]]; then
  exit 0
fi

pid="$(tr -dc '0-9' < "$PID_FILE")"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
fi

rm "$PID_FILE"
