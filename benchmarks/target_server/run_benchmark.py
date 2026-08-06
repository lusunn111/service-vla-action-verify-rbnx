#!/usr/bin/env python3
"""Run direct-model, RoboNix, fallback, and summary benchmark phases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from executor_client import ExecutorClient
from vla_action_service.backend import (
    VerifyRequest,
    OpenVLADecisionBackend,
    _normalize_action,
)


CONTRACT = "robonix/service/vla/action_verify/verify"


def _cases(manifest: Path, input_root: Path) -> list[dict]:
    value = json.loads(manifest.read_text(encoding="utf-8"))
    cases = value.get("cases") if isinstance(value, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("input manifest must contain at least one case")
    root = input_root.resolve()
    resolved = []
    for case in cases:
        relative = case.get("observation")
        expected = case.get("observation_sha256")
        path = (root / relative).resolve() if isinstance(relative, str) else root.parent
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"invalid observation path: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch for {relative}")
        resolved.append({**case, "path": str(path)})
    return resolved


def _config(args) -> dict:
    return {
        "backend_mode": "openvla",
        "target_checkpoint": str(args.target_checkpoint.resolve()),
        "drafter_checkpoint": str(args.drafter_checkpoint.resolve()),
        "allowed_image_root": str(args.input_root.resolve()),
        "cuda_visible_devices": str(args.gpu_index),
        "require_cuda": True,
        "unnorm_key": "libero_goal",
        "center_crop": True,
        "accept_threshold": 9,
        "parallel_draft": False,
        "expected_action_dim": 7,
        "max_timeout_s": 900.0,
    }


def _gpu_memory_mib(index: str) -> int:
    result = subprocess.run(
        ["nvidia-smi", f"--id={index}", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        return int(result.stdout.strip().splitlines()[0]) if result.returncode == 0 else -1
    except (ValueError, IndexError):
        return -1


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def run_direct(args, cases: list[dict]) -> None:
    backend = OpenVLADecisionBackend(_config(args))
    rows = []
    try:
        memory_before = _gpu_memory_mib(str(args.gpu_index))
        load_started = time.perf_counter()
        adapter = backend._ensure_ready()
        model_load = {
            "elapsed_ms": (time.perf_counter() - load_started) * 1000.0,
            "gpu_memory_before_mib": memory_before,
            "gpu_memory_after_mib": _gpu_memory_mib(str(args.gpu_index)),
        }
        for case in cases:
            image = Path(case["path"])
            instruction = str(case["instruction"])
            for route, prediction in (
                ("direct_target", adapter.predict_target),
                ("direct_speculative", adapter.predict_speculative),
            ):
                for _ in range(args.warmup):
                    prediction(image, instruction)
                for iteration in range(args.repeats):
                    started = time.perf_counter()
                    action = _normalize_action(prediction(image, instruction), 32, 7)
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    rows.append({
                        "case_id": case["case_id"], "route": route, "iteration": iteration,
                        "latency_ms": elapsed_ms, "gpu_memory_mib": _gpu_memory_mib(str(args.gpu_index)),
                        "mode": route.removeprefix("direct_"), "fallback_used": False,
                        "actions_json": json.dumps(action, separators=(",", ":")),
                    })
    finally:
        backend.close()
    _write_csv(args.output_dir / "direct_calls.csv", rows)
    (args.output_dir / "model_load.json").write_text(
        json.dumps(model_load, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_service(args, cases: list[dict]) -> None:
    client = ExecutorClient(args.atlas, timeout_s=900.0)
    rows = []
    try:
        first = cases[0]
        cold_wire = {
            "instruction": str(first["instruction"]),
            "observation_uri": first["path"],
            "timeout_s": 600.0,
        }
        memory_before = _gpu_memory_mib(str(args.gpu_index))
        cold = client.call(args.provider, CONTRACT, cold_wire)
        cold_start = {
            "case_id": first["case_id"],
            "elapsed_ms": cold.elapsed_ms,
            "gpu_memory_before_mib": memory_before,
            "gpu_memory_after_mib": _gpu_memory_mib(str(args.gpu_index)),
            "mode": cold.output.get("mode", ""),
            "fallback_used": cold.output.get("fallback_used", False),
        }
        for case in cases:
            wire = {"instruction": str(case["instruction"]), "observation_uri": case["path"], "timeout_s": 600.0}
            for _ in range(args.warmup):
                client.call(args.provider, CONTRACT, wire)
            for iteration in range(args.repeats):
                result = client.call(args.provider, CONTRACT, wire)
                rows.append({
                    "case_id": case["case_id"], "route": "robonix_executor_mcp", "iteration": iteration,
                    "latency_ms": result.elapsed_ms, "gpu_memory_mib": _gpu_memory_mib(str(args.gpu_index)),
                    "mode": result.output.get("mode", ""), "fallback_used": result.output.get("fallback_used", False),
                    "actions_json": json.dumps(result.output.get("actions", []), separators=(",", ":")),
                })
    finally:
        client.close()
    _write_csv(args.output_dir / "service_calls.csv", rows)
    (args.output_dir / "service_cold_start.json").write_text(
        json.dumps(cold_start, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class _FailingSpeculativeAdapter:
    def __init__(self, delegate):
        self.delegate = delegate

    def predict_speculative(self, _image, _instruction):
        raise RuntimeError("benchmark fault injection: Drafter unavailable")

    def predict_target(self, image, instruction):
        return self.delegate.predict_target(image, instruction)

    def close(self):
        self.delegate.close()


def run_fallback(args, cases: list[dict]) -> None:
    backend = OpenVLADecisionBackend(_config(args))
    try:
        backend._adapter = _FailingSpeculativeAdapter(backend._ensure_ready())
        case = cases[0]
        started = time.perf_counter()
        result = backend.verify(VerifyRequest(str(case["instruction"]), case["path"], 600.0))
        payload = {
            "case_id": case["case_id"], "mode": result.mode, "fallback_used": result.fallback_used,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "gpu_memory_mib": _gpu_memory_mib(str(args.gpu_index)), "actions": list(result.actions),
            "fault": "Drafter exception injected by benchmark harness after real model loading",
        }
        if result.mode != "target_fallback" or not result.fallback_used:
            raise RuntimeError("real target-model fallback was not observed")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "fallback.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        backend.close()


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def run_summary(args) -> None:
    direct = _read_csv(args.output_dir / "direct_calls.csv")
    service = _read_csv(args.output_dir / "service_calls.csv")
    _write_csv(args.output_dir / "calls.csv", [*direct, *service])
    fallback = json.loads((args.output_dir / "fallback.json").read_text(encoding="utf-8"))
    model_load = json.loads((args.output_dir / "model_load.json").read_text(encoding="utf-8"))
    service_cold_start = json.loads(
        (args.output_dir / "service_cold_start.json").read_text(encoding="utf-8")
    )
    direct_spec = {(row["case_id"], row["iteration"]): json.loads(row["actions_json"]) for row in direct if row["route"] == "direct_speculative"}
    parity_failures = 0
    max_error = 0.0
    for row in service:
        expected = direct_spec[(row["case_id"], row["iteration"])]
        observed = json.loads(row["actions_json"])
        if len(expected) != len(observed):
            parity_failures += 1
            continue
        error = max((abs(float(a) - float(b)) for a, b in zip(expected, observed)), default=0.0)
        max_error = max(max_error, error)
        if error > 1e-6:
            parity_failures += 1
    routes = {}
    for route in ("direct_target", "direct_speculative", "robonix_executor_mcp"):
        source = service if route == "robonix_executor_mcp" else direct
        values = [float(row["latency_ms"]) for row in source if row["route"] == route]
        routes[route] = {
            "calls": len(values), "mean_ms": statistics.fmean(values),
            "p50_ms": _percentile(values, 0.50), "p95_ms": _percentile(values, 0.95),
            "peak_gpu_memory_mib": max(int(row["gpu_memory_mib"]) for row in source if row["route"] == route),
        }
    summary = {
        "schema_version": 1, "parity_failures": parity_failures, "max_action_error": max_error,
        "routes": routes, "fallback": fallback, "model_load": model_load,
        "service_cold_start": service_cold_start,
        "service_wrapper_overhead_p50_ms": (
            routes["robonix_executor_mcp"]["p50_ms"]
            - routes["direct_speculative"]["p50_ms"]
        ),
        "speculative_speedup_p50": routes["direct_target"]["p50_ms"] / routes["direct_speculative"]["p50_ms"],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if parity_failures:
        raise SystemExit("VLA direct/Service action parity failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("direct", "service", "fallback", "summary"))
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("input_manifest.json"))
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--target-checkpoint", type=Path)
    parser.add_argument("--drafter-checkpoint", type=Path)
    parser.add_argument("--atlas", default="127.0.0.1:50351")
    parser.add_argument("--provider", default="vla_action_verify")
    parser.add_argument("--gpu-index", default="1")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "summary":
        run_summary(args)
        return
    for field in ("input_root", "target_checkpoint", "drafter_checkpoint"):
        if getattr(args, field) is None:
            raise SystemExit(f"--{field.replace('_', '-')} is required for {args.mode}")
    cases = _cases(args.manifest, args.input_root)
    {"direct": run_direct, "service": run_service, "fallback": run_fallback}[args.mode](args, cases)


if __name__ == "__main__":
    main()
