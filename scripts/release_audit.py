#!/usr/bin/env python3
"""Reject common publication hazards in the tracked release tree."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "README.md",
    "README-CN.md",
    "LICENSE",
    "CHANGELOG.md",
    "CITATION.cff",
    "UPSTREAM_SOURCE.md",
    "THIRD_PARTY_NOTICES.md",
    "CAPABILITY.md",
    "VALIDATION.md",
    "package_manifest.yaml",
    "config.spec",
    "capabilities/decide.v1.toml",
    "capabilities/lib/action_decision/srv/Decide.srv",
    "scripts/build.sh",
    "scripts/start.sh",
    "scripts/stop.sh",
    "scripts/verify_distribution.py",
    "vendor/openvla/openvla/LICENSE.OPENVLA",
}
EXECUTABLE = {"scripts/build.sh", "scripts/start.sh", "scripts/stop.sh"}
BLOCKED_SUFFIXES = {
    ".pt",
    ".pth",
    ".ckpt",
    ".safetensors",
    ".onnx",
    ".db",
    ".sqlite",
    ".sqlite3",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "subscription endpoint": re.compile(r"api/v1/client/subscribe|dash\.pqjc\.site"),
    "embedded token": re.compile(
        r"(?:token|api[_-]?key)\s*=\s*['\"][A-Za-z0-9_-]{16,}['\"]", re.I
    ),
}
SERVICE_FACING = {
    "README.md",
    "README-CN.md",
    "config.spec",
    "package_manifest.yaml",
    "CAPABILITY.md",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> None:
    failures: list[str] = []
    for relative in sorted(REQUIRED):
        if not (ROOT / relative).is_file():
            failures.append(f"missing required path: {relative}")
    for relative in sorted(EXECUTABLE):
        path = ROOT / relative
        if path.exists() and not os.access(path, os.X_OK):
            failures.append(f"script is not executable: {relative}")

    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if path.stat().st_size > 25 * 1024 * 1024:
            failures.append(f"tracked file exceeds 25 MiB: {relative}")
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            failures.append(f"model or database artifact is tracked: {relative}")
        if relative == "scripts/release_audit.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label} found in {relative}")
        if (
            relative in SERVICE_FACING
            or relative.startswith(("vla_action_service/", "examples/", "scripts/"))
        ) and re.search(r"/home/iflab-|/data/zhihao", text, re.I):
            failures.append(f"test-server absolute path found in {relative}")

    if failures:
        print("Release audit failed:")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print(f"Release audit passed for {len(tracked_files())} tracked files.")


if __name__ == "__main__":
    main()
