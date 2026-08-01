"""Runtime helpers for loading the import-compatible KERV source snapshot."""

from __future__ import annotations

import runpy
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

SERVICE_ROOT = Path(__file__).resolve().parent
VENDOR_OPENVLA_ROOT = SERVICE_ROOT / "vendor" / "openvla"


def activate_vendor() -> Path:
    """Expose source-tree or Wheel-packaged inference code without loading models."""
    if VENDOR_OPENVLA_ROOT.is_dir():
        root = VENDOR_OPENVLA_ROOT
    else:
        spec = importlib.util.find_spec("experiments.robot.openvla_utils")
        if spec is None or spec.origin is None:
            raise RuntimeError(
                "OpenVLA inference sources are missing from this installation"
            )
        root = Path(spec.origin).resolve().parents[2]
    value = str(root)
    if value not in sys.path:
        sys.path.insert(0, value)
    return root


def run_vendor_script(relative_path: str) -> Dict[str, Any]:
    """Run an original KERV script with its CLI arguments unchanged."""
    root = VENDOR_OPENVLA_ROOT
    if not root.is_dir():
        raise RuntimeError(
            "research script execution requires a source checkout; "
            "the Wheel contains the Service inference runtime only"
        )
    activate_vendor()
    script = (root / relative_path).resolve()
    if root.resolve() not in script.parents or not script.is_file():
        raise FileNotFoundError(f"Unknown KERV script: {relative_path}")
    return runpy.run_path(str(script), run_name="__main__")
