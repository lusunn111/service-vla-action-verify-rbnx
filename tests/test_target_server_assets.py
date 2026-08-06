import csv
import json
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "target_server"


def test_real_deployment_and_benchmark_framework_are_versioned():
    assert (ROOT / "examples/real-deployment/robonix_manifest.yaml").is_file()
    manifest = json.loads((BENCHMARK / "input_manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert isinstance(manifest["cases"], list)
    for name in (
        "executor_client.py",
        "extract_inputs.py",
        "invoke_executor.py",
        "run_benchmark.py",
        "run_robonix_rollout.py",
        "render_readme_media.py",
        "render_speed_comparison.py",
        "render_results.py",
    ):
        py_compile.compile(str(BENCHMARK / name), doraise=True)
    deployment = (ROOT / "examples/real-deployment/robonix_manifest.yaml").read_text()
    assert "    env:" not in deployment


def test_committed_real_results_are_complete_and_reproducible(tmp_path):
    manifest = json.loads((BENCHMARK / "input_manifest.json").read_text())
    assert len(manifest["cases"]) == 10
    assert all(len(case["observation_sha256"]) == 64 for case in manifest["cases"])

    results = BENCHMARK / "results"
    summary = json.loads((results / "summary.json").read_text())
    assert summary["parity_failures"] == 0
    assert summary["max_action_error"] <= 1e-6
    assert summary["fallback"]["mode"] == "target_fallback"
    assert summary["fallback"]["fallback_used"] is True
    assert summary["routes"]["direct_target"]["calls"] == 30
    assert summary["routes"]["direct_speculative"]["calls"] == 30
    assert summary["routes"]["robonix_executor_mcp"]["calls"] == 30
    rollout = json.loads((results / "rollout-summary.json").read_text())
    assert rollout["route"] == "Executor -> Atlas -> MCP -> vla_action_verify"
    assert rollout["task_suite"] == "libero_goal"
    assert rollout["task_id"] == 0
    assert rollout["initial_state"] == 0
    assert rollout["success"] is True
    assert rollout["policy_steps"] == 120
    assert rollout["wall_time_s"] > 0
    with (results / "calls.csv").open(newline="", encoding="utf-8") as stream:
        assert sum(1 for _ in csv.DictReader(stream)) == 90

    rendered = tmp_path / "latency.svg"
    subprocess.run(
        [
            sys.executable,
            str(BENCHMARK / "render_results.py"),
            "--summary", str(results / "summary.json"),
            "--output", str(rendered),
        ],
        check=True,
    )
    assert rendered.read_bytes() == (results / "latency.svg").read_bytes()
    assert "status: passed" in (BENCHMARK / "metadata.yaml").read_text()
