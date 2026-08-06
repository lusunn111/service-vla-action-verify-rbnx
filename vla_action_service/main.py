"""RoboNix Service provider for VLA action verification."""

from __future__ import annotations

import ipaddress
import os

from action_verify_mcp import Verify_Request, Verify_Response
from robonix_api import Err, Ok, Service

from .backend import BackendError, VerifyRequest
from .runtime import ServiceRuntime


service = Service(
    id="vla_action_verify",
    namespace="robonix/service/vla/action_verify",
)
runtime = ServiceRuntime()


def _install_secure_loopback_mcp_app() -> None:
    """Allow dynamic loopback ports with MCP SDK DNS-rebinding protection."""
    install = getattr(service, "use_mcp_app", None)
    if not callable(install):
        return
    bind_host = os.environ.get("ROBONIX_PROVIDER_BIND_HOST", "127.0.0.1").strip()
    protect_loopback = ipaddress.ip_address(bind_host).is_loopback
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_hosts = [f"{bind_host}:*"]
    allowed_origins = [f"http://{bind_host}:*", f"https://{bind_host}:*"]
    if protect_loopback:
        allowed_hosts.extend(["127.0.0.1:*", "localhost:*"])
        allowed_origins.extend(
            ["http://127.0.0.1:*", "http://localhost:*", "https://localhost:*"]
        )
    install(
        FastMCP(
            service.id,
            host=bind_host,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=protect_loopback,
                allowed_hosts=sorted(set(allowed_hosts)),
                allowed_origins=sorted(set(allowed_origins)),
            ),
        )
    )


_install_secure_loopback_mcp_app()


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
    "robonix/service/vla/action_verify/verify",
    description="Return a candidate VLA action without commanding robot hardware.",
)
def verify(request: Verify_Request) -> Verify_Response:
    """Run speculative inference with target-model fallback."""
    try:
        result = runtime.verify(
            VerifyRequest(
                instruction=request.instruction,
                observation_uri=request.observation_uri,
                timeout_s=float(request.timeout_s),
            )
        )
    except (BackendError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    return Verify_Response(
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
