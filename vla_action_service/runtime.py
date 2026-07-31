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
            if self._backend is not None:
                self._backend.close()
            self._backend = build_backend(config)

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
        with self._lock:
            if self._backend is not None:
                self._backend.close()
            self._active = False

    def shutdown(self) -> None:
        with self._lock:
            self.deactivate()
            self._backend = None
