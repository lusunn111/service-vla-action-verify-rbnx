#!/usr/bin/env python3
"""Verify that built distributions contain the real Service inference code."""

from __future__ import annotations

import tarfile
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WHEEL_REQUIRED = {
    "vla_action_service/backend.py",
    "vla_action_service/main.py",
    "service_bootstrap.py",
    "experiments/robot/openvla_utils.py",
    "experiments/robot/tool_utils.py",
    "openvla/__init__.py",
    "openvla/LICENSE.OPENVLA",
    "prismatic/__init__.py",
    "prismatic/extern/hf/modeling_prismatic.py",
    "prismatic/extern/hf/modeling_speculation.py",
    "local_transformers/generation_utils.py",
    "specdecoding/model/cnets.py",
}
SDIST_REQUIRED_SUFFIXES = {
    "vendor/openvla/experiments/robot/openvla_utils.py",
    "vendor/openvla/prismatic/extern/hf/modeling_speculation.py",
    "vendor/openvla/specdecoding/model/cnets.py",
}


def main() -> None:
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one Wheel and one source distribution")

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = set(archive.namelist())
    missing_wheel = sorted(WHEEL_REQUIRED - wheel_names)
    if missing_wheel:
        raise SystemExit(f"Wheel is missing runtime source: {missing_wheel}")

    with tarfile.open(sdists[0], "r:gz") as archive:
        sdist_names = archive.getnames()
    missing_sdist = sorted(
        suffix
        for suffix in SDIST_REQUIRED_SUFFIXES
        if not any(name.endswith(suffix) for name in sdist_names)
    )
    if missing_sdist:
        raise SystemExit(f"source distribution is missing vendor source: {missing_sdist}")

    with tempfile.TemporaryDirectory() as temporary_directory:
        environment = Path(temporary_directory) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = (
            environment / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else environment / "bin" / "python"
        )
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
            check=True,
            cwd=temporary_directory,
        )
        smoke_test = """
import importlib.util
from pathlib import Path
from vla_action_service.backend import DecisionRequest
from service_bootstrap import activate_vendor

root = activate_vendor()
assert DecisionRequest("move", "/tmp/observation.jpg").instruction == "move"
for name in (
    "experiments.robot.openvla_utils",
    "openvla.prismatic",
    "openvla.specdecoding",
):
    assert importlib.util.find_spec(name) is not None, name
for relative_path in (
    "prismatic/extern/hf/modeling_speculation.py",
    "specdecoding/model/cnets.py",
):
    assert (Path(root) / relative_path).is_file(), relative_path
"""
        subprocess.run(
            [str(python), "-c", smoke_test],
            check=True,
            cwd=temporary_directory,
        )

    print(
        "Distribution audit passed: Service and inference sources are packaged "
        "and discoverable from an isolated Wheel installation."
    )


if __name__ == "__main__":
    main()
