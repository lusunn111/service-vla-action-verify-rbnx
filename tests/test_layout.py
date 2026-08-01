import importlib.util
from pathlib import Path
import subprocess
import sys

try:
    import speculative_decoding_service as service
    from speculative_decoding_service.modules import strategies

    SERVICE_ROOT = Path(service.__file__).resolve().parent
    activate_vendor = service.activate_vendor
except ModuleNotFoundError:
    import service_bootstrap
    from modules import strategies

    SERVICE_ROOT = Path(service_bootstrap.__file__).resolve().parent
    activate_vendor = service_bootstrap.activate_vendor


def test_vendor_tree_and_default_strategy_exist():
    assert (SERVICE_ROOT / "vendor" / "openvla" / "specdecoding" / "model").is_dir()
    assert strategies.DEFAULT_STRATEGY in strategies.STRATEGIES


def test_activate_vendor_is_idempotent():
    assert activate_vendor() == activate_vendor()


def test_flattened_vendor_exposes_openvla_namespace():
    activate_vendor()
    assert importlib.util.find_spec("openvla.prismatic") is not None
    assert importlib.util.find_spec("openvla.specdecoding") is not None


def test_cli_help_works_from_independent_toolkit_root():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run", "--help"],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Path relative to vendor/openvla" in result.stdout


def test_service_activation_does_not_import_gpu_or_model_dependencies():
    code = """
import sys
from vla_action_service.runtime import ServiceRuntime
runtime = ServiceRuntime()
runtime.configure({"backend_mode": "mock"})
runtime.activate()
blocked = {"torch", "tensorflow", "transformers"} & set(sys.modules)
if blocked:
    print(f"eager imports: {sorted(blocked)}", file=sys.stderr)
raise SystemExit(1 if blocked else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
