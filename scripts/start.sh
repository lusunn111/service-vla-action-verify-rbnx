#!/usr/bin/env bash
set -euo pipefail

PKG_ROOT="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG_ROOT"

command -v rbnx >/dev/null 2>&1 || {
  echo "rbnx is required to locate robonix-api." >&2
  exit 127
}

RUNTIME_DIR="${RBNX_RUNTIME_DIR:-$PKG_ROOT/.run}"
SERVICE_PYTHON="${ROBONIX_SERVICE_PYTHON:-python3}"
PID_FILE="$RUNTIME_DIR/vla-action-decision.pid"
mkdir -p "$RUNTIME_DIR"
if [[ -f "$PID_FILE" ]]; then
  IFS= read -r existing_pid < "$PID_FILE" || true
  if [[ "$existing_pid" =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "VLA action decision Service PID file already names a live process." >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi
trap 'rm -f "$PID_FILE"' EXIT
printf '%s\n' "$$" > "$PID_FILE"

export PYTHONPATH="$(rbnx path robonix-api):$PKG_ROOT:${PYTHONPATH:-}"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="${PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION:-python}"
exec "$SERVICE_PYTHON" -m vla_action_service.main
