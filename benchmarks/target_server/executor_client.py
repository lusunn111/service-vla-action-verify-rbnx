"""Small deterministic client for one-node RTDL calls through RoboNix Executor."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
PROTO_ROOT = ROOT / "rbnx-build" / "codegen" / "proto_gen"


@dataclass(frozen=True)
class ExecutorResult:
    output: dict
    elapsed_ms: float
    plan_id: str


def _load_generated_modules():
    if not PROTO_ROOT.is_dir():
        raise RuntimeError(
            f"RoboNix codegen output is missing at {PROTO_ROOT}; run `rbnx build -p .`"
        )
    sys.path.insert(0, str(PROTO_ROOT))
    try:
        import grpc
        import pilot_pb2
        import robonix_contracts_pb2_grpc
    except ImportError as exc:
        raise RuntimeError(
            "Executor client needs grpcio and the generated RoboNix Python stubs"
        ) from exc
    return grpc, pilot_pb2, robonix_contracts_pb2_grpc


def _inspect(atlas: str) -> dict:
    result = subprocess.run(
        ["rbnx", "inspect", "--server", atlas],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rbnx inspect failed: {result.stderr.strip()}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("rbnx inspect returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("rbnx inspect returned a non-object JSON value")
    return value


def _executor_endpoint(snapshot: dict) -> str:
    contract = "robonix/system/executor/execute"
    providers = snapshot.get("providers", {})
    executor = providers.get("executor", {}) if isinstance(providers, dict) else {}
    for endpoint in executor.get("endpoints", []):
        if endpoint.get("contract_id") == contract:
            raw = str(endpoint.get("endpoint", ""))
            parsed = urlsplit(raw if "://" in raw else f"grpc://{raw}")
            if parsed.hostname and parsed.port:
                return f"{parsed.hostname}:{parsed.port}"
    raise RuntimeError("Atlas does not expose robonix/system/executor/execute")


class ExecutorClient:
    def __init__(self, atlas: str, timeout_s: float = 900.0):
        self.timeout_s = timeout_s
        grpc, pilot_pb2, contracts_grpc = _load_generated_modules()
        self._pilot_pb2 = pilot_pb2
        endpoint = _executor_endpoint(_inspect(atlas))
        self._channel = grpc.insecure_channel(endpoint)
        self._stub = contracts_grpc.RobonixSystemExecutorExecuteStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    def call(self, provider: str, contract: str, arguments: dict) -> ExecutorResult:
        plan_id = f"validation-{uuid.uuid4()}"
        plan = self._pilot_pb2.Plan(
            plan_id=plan_id,
            session_id="target-server-validation",
            round=1,
            root_index=0,
            nodes=[
                self._pilot_pb2.RtdlNode(
                    node_kind=2,
                    op_id="op-call",
                    description=f"validate {contract}",
                    call=self._pilot_pb2.CapabilityCall(
                        call_id=f"{plan_id}-call",
                        provider_id=provider,
                        contract_id=contract,
                        args_json=json.dumps(arguments, separators=(",", ":")),
                    ),
                )
            ],
        )
        started = time.perf_counter()
        terminal = None
        completed = False
        for event in self._stub.Execute(plan, timeout=self.timeout_s):
            if event.HasField("node_state") and event.node_state.op_id == "op-call":
                if event.node_state.state in {2, 3, 4, 5}:
                    terminal = event.node_state
            if event.HasField("plan_complete"):
                completed = True
                if event.plan_complete.any_failed:
                    break
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not completed or terminal is None:
            raise RuntimeError("Executor did not return a terminal node and plan completion")
        result = terminal.leaf_result
        if terminal.state != 2 or not result.success:
            raise RuntimeError(result.error or terminal.operator_detail or "Executor call failed")
        try:
            output = json.loads(result.output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Executor returned non-JSON capability output") from exc
        if not isinstance(output, dict):
            raise RuntimeError("Executor capability output is not a JSON object")
        return ExecutorResult(output=output, elapsed_ms=elapsed_ms, plan_id=plan_id)
