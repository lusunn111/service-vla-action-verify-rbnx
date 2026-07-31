#!/usr/bin/env bash
set -euo pipefail

PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNTIME_DIR="${RBNX_RUNTIME_DIR:-$PKG_ROOT/.run}"
PID_FILE="$RUNTIME_DIR/vla-action-decision.pid"

if [[ ! -f "$PID_FILE" ]]; then
  exit 0
fi

IFS= read -r pid < "$PID_FILE" || true
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  rm -f "$PID_FILE"
  echo "Removed an invalid VLA action decision Service PID file." >&2
  exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PID_FILE"
  exit 0
fi

command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
if [[ "$command_line" != *"-m vla_action_service.main"* ]]; then
  rm -f "$PID_FILE"
  echo "Refusing to stop PID $pid because it is not the VLA action decision Service." >&2
  exit 1
fi

kill "$pid"
rm -f "$PID_FILE"
