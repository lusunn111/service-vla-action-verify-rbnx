"""RoboNix Service provider for VLA action decisions."""

from __future__ import annotations

from action_decision_mcp import Decide_Request, Decide_Response
from robonix_api import Err, Ok, Service

from .backend import BackendError, DecisionRequest
from .runtime import ServiceRuntime


service = Service(
    id="vla_action_decision",
    namespace="robonix/service/vla/action_decision",
)
runtime = ServiceRuntime()


@service.on_init
def init(config: dict):
    """Validate configuration without importing or loading model code."""
    try:
        runtime.configure(config)
    except (TypeError, ValueError, RuntimeError) as exc:
        return Err(str(exc))
    return Ok()


@service.on_activate
def activate():
    """Make the Service callable while keeping GPU allocation lazy."""
    try:
        runtime.activate()
    except RuntimeError as exc:
        return Err(str(exc))
    return Ok()


@service.on_deactivate
def deactivate():
    """Release package-owned model and GPU state."""
    try:
        runtime.deactivate()
    except Exception as exc:
        return Err(str(exc))
    return Ok()


@service.on_shutdown
def shutdown():
    """Discard configuration and release package-owned state."""
    try:
        runtime.shutdown()
    except Exception as exc:
        return Err(str(exc))
    return Ok()


@service.mcp(
    "robonix/service/vla/action_decision/decide",
    description="Return a candidate VLA action without commanding robot hardware.",
)
def decide(request: Decide_Request) -> Decide_Response:
    """Run speculative inference with target-model fallback."""
    try:
        result = runtime.decide(
            DecisionRequest(
                instruction=request.instruction,
                observation_uri=request.observation_uri,
                timeout_s=float(request.timeout_s),
            )
        )
    except (BackendError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    return Decide_Response(
        success=result.success,
        actions=list(result.actions),
        action_horizon=result.action_horizon,
        action_dim=result.action_dim,
        mode=result.mode,
        fallback_used=result.fallback_used,
        fallback_required=result.fallback_required,
        detail=result.detail,
    )


if __name__ == "__main__":
    service.run()
