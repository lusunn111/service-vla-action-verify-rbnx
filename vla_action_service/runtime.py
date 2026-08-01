"""Lifecycle-owned VLA Service state."""

from __future__ import annotations

from threading import RLock
from typing import Any

from .backend import DecisionBackend, DecisionRequest, DecisionResult, build_backend


class ServiceRuntime:
    """Serialize inference and keep model loading out of RoboNix boot."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._backend: DecisionBackend | None = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def configure(self, config: dict[str, Any]) -> None:
        """Validate configuration without importing GPU dependencies."""
        with self._lock:
            if self._active:
                raise RuntimeError("cannot reconfigure an active Service")
            replacement = build_backend(config)
            previous = self._backend
            if previous is not None:
                try:
                    previous.close()
                except Exception:
                    try:
                        replacement.close()
                    except Exception:
                        pass
                    raise
            self._backend = replacement

    def activate(self) -> None:
        """Enter ACTIVE without loading the target model or Drafter."""
        with self._lock:
            if self._backend is None:
                raise RuntimeError("Service has not been initialized")
            self._active = True

    def decide(self, request: DecisionRequest) -> DecisionResult:
        with self._lock:
            if not self._active or self._backend is None:
                raise RuntimeError("Service is not active")
            return self._backend.decide(request)

    def deactivate(self) -> None:
        """Stop new calls and release model state, even if cleanup reports an error."""
        with self._lock:
            backend = self._backend
            self._active = False
            if backend is not None:
                backend.close()

    def shutdown(self) -> None:
        """Discard configuration and release the package-owned model state."""
        with self._lock:
            backend = self._backend
            self._backend = None
            self._active = False
            if backend is not None:
                backend.close()
