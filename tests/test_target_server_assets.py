import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "target_server"


def test_real_deployment_and_benchmark_framework_are_versioned():
    assert (ROOT / "examples/real-deployment/robonix_manifest.yaml").is_file()
    manifest = json.loads((BENCHMARK / "input_manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert isinstance(manifest["cases"], list)
    for name in ("executor_client.py", "invoke_executor.py", "run_benchmark.py", "render_results.py"):
        py_compile.compile(str(BENCHMARK / name), doraise=True)
