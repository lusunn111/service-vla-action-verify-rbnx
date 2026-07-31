"""Lazy in-process OpenVLA and Drafter inference boundary."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol


class BackendError(RuntimeError):
    """Raised when a decision backend cannot return a valid action."""


@dataclass(frozen=True)
class DecisionRequest:
    """One action-decision request independent from generated RoboNix types."""

    instruction: str
    observation_uri: str
    timeout_s: float = 30.0


@dataclass(frozen=True)
class DecisionResult:
    """A normalized candidate action and its inference mode."""

    success: bool
    actions: tuple[float, ...] = ()
    action_horizon: int = 0
    action_dim: int = 0
    mode: str = "unavailable"
    fallback_used: bool = False
    fallback_required: bool = True
    detail: str = ""


class DecisionBackend(Protocol):
    """Lifecycle and request boundary implemented by every backend."""

    def decide(self, request: DecisionRequest) -> DecisionResult: ...

    def close(self) -> None: ...


class ModelAdapter(Protocol):
    """Minimal adapter over the heavyweight research model implementation."""

    def predict_speculative(self, image_path: Path, instruction: str) -> Any: ...

    def predict_target(self, image_path: Path, instruction: str) -> Any: ...

    def close(self) -> None: ...


def _verified_image(
    uri: str, allowed_root: Path, max_image_bytes: int
) -> Path:
    """Resolve and signature-check one deployment-owned local image."""
    value = uri[7:] if uri.startswith("file://") else uri
    if "://" in value:
        raise BackendError("observation_uri only supports local paths and file:// URIs")
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(allowed_root):
        raise BackendError(f"observation path is outside allowed_image_root: {path}")
    if not path.is_file():
        raise BackendError(f"observation image does not exist: {path}")
    size = path.stat().st_size
    if size <= 0 or size > max_image_bytes:
        raise BackendError("observation image size is outside the allowed range")
    with path.open("rb") as stream:
        head = stream.read(12)
    supported = (
        head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"\x89PNG\r\n\x1a\n")
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
    )
    if not supported:
        raise BackendError("observation is not a supported JPEG, PNG, or WebP image")
    return path


def _normalize_action(payload: Any, max_action_dim: int) -> tuple[float, ...]:
    """Convert a model action into one bounded finite vector."""
    if hasattr(payload, "tolist"):
        payload = payload.tolist()
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], list):
        payload = payload[0]
    if not isinstance(payload, (list, tuple)) or not payload:
        raise BackendError("model returned no action")
    if len(payload) > max_action_dim:
        raise BackendError("model action dimension exceeds its configured limit")
    values: list[float] = []
    for value in payload:
        try:
            converted = float(value)
        except (TypeError, ValueError) as exc:
            raise BackendError("model action contains a non-numeric value") from exc
        if not math.isfinite(converted):
            raise BackendError("model action contains a non-finite value")
        values.append(converted)
    return tuple(values)


class ResearchModelAdapter:
    """Load and call the preserved SpecVLA research implementation on demand."""

    def __init__(self, config: dict[str, Any]):
        from service_bootstrap import activate_vendor

        activate_vendor()
        from experiments.robot.openvla_utils import (
            get_processor,
            get_vla,
            get_vla_action,
        )

        self._get_vla_action = get_vla_action
        self._cfg = SimpleNamespace(
            model_family="openvla",
            pretrained_checkpoint=config["target_checkpoint"],
            spec_checkpoint=config["drafter_checkpoint"],
            use_spec=True,
            parallel_draft=bool(config.get("parallel_draft", False)),
            accept_threshold=int(config.get("accept_threshold", 9)),
            load_in_8bit=bool(config.get("load_in_8bit", False)),
            load_in_4bit=bool(config.get("load_in_4bit", False)),
            unnorm_key=str(config.get("unnorm_key", "libero_goal")),
            center_crop=bool(config.get("center_crop", True)),
        )
        self._model = get_vla(self._cfg)
        self._processor = get_processor(self._cfg)
        self._target_model = getattr(self._model, "base_model", None)
        if self._target_model is None:
            self.close()
            raise BackendError("SpecVLA wrapper does not expose its target model")

    def _observation(self, image_path: Path) -> dict[str, Any]:
        import numpy as np
        from PIL import Image

        with Image.open(image_path) as image:
            array = np.asarray(image.convert("RGB"))
        return {"full_image": array}

    def predict_speculative(self, image_path: Path, instruction: str) -> Any:
        """Run Drafter proposal plus target verification."""
        return self._get_vla_action(
            self._model,
            self._processor,
            self._cfg.pretrained_checkpoint,
            self._observation(image_path),
            instruction,
            self._cfg.unnorm_key,
            center_crop=self._cfg.center_crop,
            generate_mode="speculative",
        )

    def predict_target(self, image_path: Path, instruction: str) -> Any:
        """Run the already-loaded target model without loading a second copy."""
        return self._get_vla_action(
            self._target_model,
            self._processor,
            self._cfg.pretrained_checkpoint,
            self._observation(image_path),
            instruction,
            self._cfg.unnorm_key,
            center_crop=self._cfg.center_crop,
        )

    def close(self) -> None:
        """Release model references and package-owned CUDA cache."""
        self._target_model = None
        self._processor = None
        self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


class MockDecisionBackend:
    """Non-executable lifecycle backend used only by automated tests."""

    def decide(self, request: DecisionRequest) -> DecisionResult:
        if not request.instruction.strip():
            raise BackendError("instruction must not be empty")
        return DecisionResult(
            success=False,
            mode="mock",
            fallback_required=True,
            detail="mock mode performs no model inference and returns no executable action",
        )

    def close(self) -> None:
        return None


class OpenVLADecisionBackend:
    """Own one lazily loaded target model and Drafter pair."""

    def __init__(self, config: dict[str, Any]):
        required = ("target_checkpoint", "drafter_checkpoint", "allowed_image_root")
        values = {key: str(config.get(key, "")).strip() for key in required}
        if not all(values.values()):
            raise ValueError(
                "target_checkpoint, drafter_checkpoint, and allowed_image_root are required"
            )
        if bool(config.get("load_in_8bit", False)) and bool(
            config.get("load_in_4bit", False)
        ):
            raise ValueError("load_in_8bit and load_in_4bit cannot both be true")
        self.config = {**config, **values}
        self.max_image_bytes = int(config.get("max_image_bytes", 10 * 1024 * 1024))
        self.max_action_dim = int(config.get("max_action_dim", 32))
        if min(self.max_image_bytes, self.max_action_dim) <= 0:
            raise ValueError("image and action limits must be positive")
        self._adapter: ModelAdapter | None = None

    def _load_adapter(self) -> ModelAdapter:
        """Construct the heavyweight adapter; separated for deterministic tests."""
        for field in ("target_checkpoint", "drafter_checkpoint"):
            if not Path(self.config[field]).expanduser().is_dir():
                raise BackendError(f"{field} directory does not exist")
        return ResearchModelAdapter(self.config)

    def _ensure_ready(self) -> ModelAdapter:
        if self._adapter is None:
            self._adapter = self._load_adapter()
        return self._adapter

    def decide(self, request: DecisionRequest) -> DecisionResult:
        if not request.instruction.strip():
            raise BackendError("instruction must not be empty")
        if request.timeout_s <= 0:
            raise BackendError("timeout_s must be positive")
        root = Path(self.config["allowed_image_root"]).expanduser().resolve()
        if not root.is_dir():
            raise BackendError("allowed_image_root directory does not exist")
        image_path = _verified_image(request.observation_uri, root, self.max_image_bytes)
        adapter = self._ensure_ready()
        started = time.monotonic()
        try:
            action = _normalize_action(
                adapter.predict_speculative(image_path, request.instruction),
                self.max_action_dim,
            )
            mode = "speculative"
            fallback_used = False
        except Exception as speculative_error:
            try:
                action = _normalize_action(
                    adapter.predict_target(image_path, request.instruction),
                    self.max_action_dim,
                )
            except Exception as target_error:
                raise BackendError(
                    "speculative and target inference both failed: "
                    f"{speculative_error}; {target_error}"
                ) from target_error
            mode = "target_fallback"
            fallback_used = True
        elapsed = time.monotonic() - started
        if elapsed > request.timeout_s:
            raise BackendError(
                f"inference exceeded timeout_s ({elapsed:.3f}s > {request.timeout_s:.3f}s)"
            )
        return DecisionResult(
            success=True,
            actions=action,
            action_horizon=1,
            action_dim=len(action),
            mode=mode,
            fallback_used=fallback_used,
            fallback_required=False,
            detail="candidate action returned; downstream safety validation is required",
        )

    def close(self) -> None:
        if self._adapter is not None:
            self._adapter.close()
        self._adapter = None


def build_backend(config: dict[str, Any]) -> DecisionBackend:
    """Build a configured backend without loading any model."""
    mode = str(config.get("backend_mode", "openvla")).lower()
    if mode == "mock":
        return MockDecisionBackend()
    if mode == "openvla":
        return OpenVLADecisionBackend(config)
    raise ValueError(f"unsupported backend_mode: {mode}")
