"""Lazy in-process OpenVLA and Drafter inference boundary."""

from __future__ import annotations

import gc
import json
import math
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol


class BackendError(RuntimeError):
    """Raised when a decision backend cannot return a valid action."""


@dataclass(frozen=True)
class VerifyRequest:
    """One action-verify request independent from generated RoboNix types."""

    instruction: str
    observation_uri: str
    timeout_s: float = 30.0


@dataclass(frozen=True)
class VerifyResult:
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

    def verify(self, request: VerifyRequest) -> VerifyResult: ...

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
    if head.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        detected = "image/webp"
    else:
        detected = ""
    if not detected or mimetypes.guess_type(path.name)[0] != detected:
        raise BackendError("observation is not a supported JPEG, PNG, or WebP image")
    return path


def _normalize_action(
    payload: Any, max_action_dim: int, expected_action_dim: int
) -> tuple[float, ...]:
    """Convert a model action into one bounded finite vector."""
    if hasattr(payload, "tolist"):
        payload = payload.tolist()
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], list):
        payload = payload[0]
    if not isinstance(payload, (list, tuple)) or not payload:
        raise BackendError("model returned no action")
    if len(payload) > max_action_dim:
        raise BackendError("model action dimension exceeds its configured limit")
    if len(payload) != expected_action_dim:
        raise BackendError(
            "model action dimension does not match expected_action_dim "
            f"({len(payload)} != {expected_action_dim})"
        )
    values: list[float] = []
    for value in payload:
        if isinstance(value, bool):
            raise BackendError("model action contains a non-numeric value")
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
        self._get_vla_action = None
        self._torch = None
        self._cfg = None
        self._model = None
        self._processor = None
        try:
            cuda_visible_devices = str(
                config.get("cuda_visible_devices", "")
            ).strip()
            if cuda_visible_devices:
                os.environ["CUDA_VISIBLE_DEVICES"] = cuda_visible_devices

            from service_bootstrap import activate_vendor

            activate_vendor()
            import torch
            from experiments.robot.openvla_utils import (
                get_processor,
                get_vla,
                get_vla_action,
            )

            if bool(config.get("require_cuda", True)) and not torch.cuda.is_available():
                raise BackendError("CUDA is required but is not available")

            self._torch = torch
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
                max_image_pixels=int(config.get("max_image_pixels", 16_777_216)),
            )
            self._model = get_vla(self._cfg)
            self._processor = get_processor(self._cfg)
            target_model = getattr(self._model, "base_model", None)
            if target_model is None:
                raise BackendError("SpecVLA wrapper does not expose its target model")
            if hasattr(self._model, "norm_stats"):
                target_model.norm_stats = self._model.norm_stats
            self._model.eval()
            target_model.eval()
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _observation(self, image_path: Path) -> dict[str, Any]:
        import numpy as np
        from PIL import Image

        with Image.open(image_path) as image:
            if image.width * image.height > self._cfg.max_image_pixels:
                raise BackendError("observation image pixel count exceeds its configured limit")
            array = np.asarray(image.convert("RGB"))
        return {"full_image": array}

    def predict_speculative(self, image_path: Path, instruction: str) -> Any:
        """Run Drafter proposal plus target verification."""
        with self._torch.inference_mode():
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
        """Run target-only decoding through the loaded SpecVLA wrapper.

        The research loader replaces the base model's language model with a
        speculation-aware implementation.  Calling ``base_model.generate``
        directly bypasses the wrapper's cache setup and can leave the
        attention mask inconsistent.  The wrapper's default generation path
        is its target-only ``ea_forward`` implementation and reuses the same
        target weights without invoking the Drafter.
        """
        # The research wrapper may retain its Drafter tree mask after model
        # construction or a failed speculative call.  Target-only decoding
        # must never consume that request-local state.
        self._model.tree_mask = None
        language_model = getattr(self._model.base_model, "language_model", None)
        if language_model is not None and hasattr(language_model, "tree_mask"):
            language_model.tree_mask = None
        ea_layer = getattr(self._model, "ea_layer", None)
        if ea_layer is not None and hasattr(ea_layer, "tree_mask"):
            ea_layer.tree_mask = None
        with self._torch.inference_mode():
            return self._get_vla_action(
                self._model,
                self._processor,
                self._cfg.pretrained_checkpoint,
                self._observation(image_path),
                instruction,
                self._cfg.unnorm_key,
                center_crop=self._cfg.center_crop,
            )

    def close(self) -> None:
        """Release model references and package-owned CUDA cache."""
        torch_module = self._torch
        self._processor = None
        self._model = None
        self._get_vla_action = None
        self._torch = None
        cleanup_errors: list[str] = []
        try:
            gc.collect()
        except Exception as exc:
            cleanup_errors.append(f"garbage collection: {_error_summary(exc)}")
        if torch_module is not None:
            try:
                if torch_module.cuda.is_available():
                    torch_module.cuda.empty_cache()
                    if hasattr(torch_module.cuda, "ipc_collect"):
                        torch_module.cuda.ipc_collect()
            except Exception as exc:
                cleanup_errors.append(f"CUDA cache: {_error_summary(exc)}")
        if cleanup_errors:
            raise BackendError(
                "model references were released but cleanup was incomplete: "
                + "; ".join(cleanup_errors)
            )


class MockDecisionBackend:
    """Non-executable lifecycle backend used only by automated tests."""

    def verify(self, request: VerifyRequest) -> VerifyResult:
        if not request.instruction.strip():
            raise BackendError("instruction must not be empty")
        if not math.isfinite(request.timeout_s) or request.timeout_s <= 0:
            raise BackendError("timeout_s must be a positive finite value")
        return VerifyResult(
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
        load_in_8bit = _config_bool(config, "load_in_8bit", False)
        load_in_4bit = _config_bool(config, "load_in_4bit", False)
        parallel_draft = _config_bool(config, "parallel_draft", False)
        require_cuda = _config_bool(config, "require_cuda", True)
        center_crop = _config_bool(config, "center_crop", True)
        if load_in_8bit and load_in_4bit:
            raise ValueError("load_in_8bit and load_in_4bit cannot both be true")
        for field, value in values.items():
            if not Path(value).expanduser().is_absolute():
                raise ValueError(f"{field} must be an absolute path")
        allowed_root = Path(values["allowed_image_root"]).expanduser().resolve()
        if not allowed_root.is_dir():
            raise ValueError("allowed_image_root must be an existing directory")
        cuda_visible_devices = str(config.get("cuda_visible_devices", "")).strip()
        if cuda_visible_devices and not re.fullmatch(
            r"\d+(?:,\d+)*", cuda_visible_devices
        ):
            raise ValueError("cuda_visible_devices must be comma-separated GPU indices")
        self.config = {
            **config,
            **values,
            "allowed_image_root": str(allowed_root),
            "cuda_visible_devices": cuda_visible_devices,
            "load_in_8bit": load_in_8bit,
            "load_in_4bit": load_in_4bit,
            "parallel_draft": parallel_draft,
            "require_cuda": require_cuda,
            "center_crop": center_crop,
        }
        self.allowed_root = allowed_root
        self.max_image_bytes = int(config.get("max_image_bytes", 10 * 1024 * 1024))
        self.max_image_pixels = int(config.get("max_image_pixels", 16_777_216))
        self.max_action_dim = int(config.get("max_action_dim", 32))
        self.expected_action_dim = int(config.get("expected_action_dim", 7))
        self.max_instruction_chars = int(config.get("max_instruction_chars", 4096))
        self.max_timeout_s = float(config.get("max_timeout_s", 300.0))
        self.accept_threshold = int(config.get("accept_threshold", 9))
        unnorm_key = str(config.get("unnorm_key", "libero_goal")).strip()
        if (
            min(
                self.max_image_bytes,
                self.max_image_pixels,
                self.max_action_dim,
                self.expected_action_dim,
                self.max_instruction_chars,
                self.max_timeout_s,
            )
            <= 0
        ):
            raise ValueError("image, action, instruction, and timeout limits must be positive")
        if not math.isfinite(self.max_timeout_s):
            raise ValueError("max_timeout_s must be finite")
        if self.expected_action_dim > self.max_action_dim:
            raise ValueError("expected_action_dim cannot exceed max_action_dim")
        if self.accept_threshold < 0:
            raise ValueError("accept_threshold must be non-negative")
        if not unnorm_key or len(unnorm_key) > 128:
            raise ValueError("unnorm_key must contain between 1 and 128 characters")
        self.config["accept_threshold"] = self.accept_threshold
        self.config["unnorm_key"] = unnorm_key
        self.config["max_image_pixels"] = self.max_image_pixels
        self._adapter: ModelAdapter | None = None

    def _validate_checkpoint_layout(self) -> None:
        """Reject incomplete checkpoints before importing GPU libraries."""
        target = Path(self.config["target_checkpoint"]).expanduser()
        drafter = Path(self.config["drafter_checkpoint"]).expanduser()
        for field, path in (("target_checkpoint", target), ("drafter_checkpoint", drafter)):
            if not path.is_dir():
                raise BackendError(f"{field} directory does not exist")

        metadata: dict[str, Any] = {}
        for filename in ("config.json", "preprocessor_config.json", "dataset_statistics.json"):
            metadata_path = target / filename
            if not metadata_path.is_file():
                raise BackendError(f"target_checkpoint is missing {filename}")
            try:
                value = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackendError(f"target {filename} is invalid") from exc
            if not isinstance(value, dict):
                raise BackendError(f"target {filename} must contain a JSON object")
            metadata[filename] = value
        target_weights = [
            path
            for pattern in ("*.safetensors", "pytorch_model*.bin")
            for path in target.glob(pattern)
            if path.is_file() and path.stat().st_size > 1024
        ]
        if not target_weights:
            raise BackendError("target_checkpoint contains no usable model weights")

        drafter_config = drafter / "config.json"
        if not drafter_config.is_file():
            raise BackendError("drafter_checkpoint is missing config.json")
        try:
            drafter_metadata = json.loads(drafter_config.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackendError("drafter config.json is invalid") from exc
        if not isinstance(drafter_metadata, dict):
            raise BackendError("drafter config.json must contain a JSON object")
        drafter_weight_name = (
            "model.safetensors"
            if self.config["parallel_draft"]
            else "pytorch_model.bin"
        )
        drafter_weights = drafter / drafter_weight_name
        if not drafter_weights.is_file() or drafter_weights.stat().st_size <= 1024:
            raise BackendError(
                f"drafter_checkpoint is missing a usable {drafter_weight_name}"
            )

        statistics = metadata["dataset_statistics.json"]
        configured_key = self.config["unnorm_key"]
        unnorm_key = configured_key
        if unnorm_key not in statistics and f"{unnorm_key}_no_noops" in statistics:
            unnorm_key = f"{unnorm_key}_no_noops"
        if unnorm_key not in statistics:
            raise BackendError(
                f"unnorm_key {configured_key!r} is absent from dataset_statistics.json"
            )
        action_statistics = statistics[unnorm_key]
        if isinstance(action_statistics, dict):
            action_statistics = action_statistics.get("action")
        if not isinstance(action_statistics, dict):
            raise BackendError("dataset action statistics are missing")
        q01 = _finite_vector(action_statistics.get("q01"), "q01")
        q99 = _finite_vector(action_statistics.get("q99"), "q99")
        if len(q01) != self.expected_action_dim or len(q99) != self.expected_action_dim:
            raise BackendError(
                "dataset action statistics do not match expected_action_dim"
            )
        if any(low > high for low, high in zip(q01, q99)):
            raise BackendError("dataset action statistics contain q01 values above q99")
        mask = action_statistics.get("mask")
        if mask is not None and (
            not isinstance(mask, list)
            or len(mask) != self.expected_action_dim
            or any(not isinstance(value, bool) for value in mask)
        ):
            raise BackendError("dataset action mask does not match expected_action_dim")
        self.config["unnorm_key"] = unnorm_key

    def _load_adapter(self) -> ModelAdapter:
        """Construct the heavyweight adapter; separated for deterministic tests."""
        self._validate_checkpoint_layout()
        return ResearchModelAdapter(self.config)

    def _ensure_ready(self) -> ModelAdapter:
        if self._adapter is None:
            self._adapter = self._load_adapter()
        return self._adapter

    def verify(self, request: VerifyRequest) -> VerifyResult:
        instruction = request.instruction.strip()
        if not instruction:
            raise BackendError("instruction must not be empty")
        if len(instruction) > self.max_instruction_chars:
            raise BackendError("instruction exceeds its configured length limit")
        if (
            not math.isfinite(request.timeout_s)
            or request.timeout_s <= 0
            or request.timeout_s > self.max_timeout_s
        ):
            raise BackendError(
                "timeout_s must be positive, finite, and within max_timeout_s"
            )
        image_path = _verified_image(
            request.observation_uri, self.allowed_root, self.max_image_bytes
        )
        started = time.monotonic()
        deadline = started + request.timeout_s
        adapter = self._ensure_ready()
        if time.monotonic() > deadline:
            cleanup_detail = self._release_after_failure()
            raise BackendError(
                "model loading exceeded timeout_s; inference was not started"
                + cleanup_detail
            )
        try:
            action = _normalize_action(
                adapter.predict_speculative(image_path, instruction),
                self.max_action_dim,
                self.expected_action_dim,
            )
        except Exception as speculative_error:
            if time.monotonic() > deadline:
                cleanup_detail = self._release_after_failure()
                raise BackendError(
                    "speculative inference failed after timeout_s; target fallback was skipped"
                    + cleanup_detail
                ) from speculative_error
            try:
                action = _normalize_action(
                    adapter.predict_target(image_path, instruction),
                    self.max_action_dim,
                    self.expected_action_dim,
                )
            except Exception as target_error:
                cleanup_detail = self._release_after_failure()
                raise BackendError(
                    "speculative and target inference both failed: "
                    f"{_error_summary(speculative_error)}; "
                    f"{_error_summary(target_error)}"
                    f"{cleanup_detail}"
                ) from target_error
            if time.monotonic() > deadline:
                cleanup_detail = self._release_after_failure()
                raise BackendError(
                    "target fallback exceeded timeout_s at a safe boundary"
                    + cleanup_detail
                )
            mode = "target_fallback"
            fallback_used = True
        else:
            if time.monotonic() > deadline:
                cleanup_detail = self._release_after_failure()
                raise BackendError(
                    "speculative inference exceeded timeout_s at a safe boundary"
                    + cleanup_detail
                )
            mode = "speculative"
            fallback_used = False
        return VerifyResult(
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
        adapter, self._adapter = self._adapter, None
        if adapter is not None:
            adapter.close()

    def _release_after_failure(self) -> str:
        """Clear adapter ownership while preserving the primary call error."""
        try:
            self.close()
        except Exception as exc:
            return f"; cleanup also failed: {_error_summary(exc)}"
        return ""


def _error_summary(error: Exception, limit: int = 240) -> str:
    """Return a bounded single-line diagnostic suitable for an RPC error."""
    text = " ".join(str(error).split())
    if not text:
        text = type(error).__name__
    return text[:limit]


def _config_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    """Read one typed boolean without treating non-empty strings as true."""
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _finite_vector(payload: Any, field: str) -> tuple[float, ...]:
    """Validate one non-empty finite numeric vector from checkpoint metadata."""
    if not isinstance(payload, list) or not payload:
        raise BackendError(f"dataset action statistic {field} must be a non-empty list")
    values: list[float] = []
    for value in payload:
        if isinstance(value, bool):
            raise BackendError(
                f"dataset action statistic {field} contains a non-numeric value"
            )
        try:
            converted = float(value)
        except (TypeError, ValueError) as exc:
            raise BackendError(
                f"dataset action statistic {field} contains a non-numeric value"
            ) from exc
        if not math.isfinite(converted):
            raise BackendError(
                f"dataset action statistic {field} contains a non-finite value"
            )
        values.append(converted)
    return tuple(values)


def build_backend(config: dict[str, Any]) -> DecisionBackend:
    """Build a configured backend without loading any model."""
    mode = str(config.get("backend_mode", "openvla")).lower()
    if mode == "mock":
        return MockDecisionBackend()
    if mode == "openvla":
        return OpenVLADecisionBackend(config)
    raise ValueError(f"unsupported backend_mode: {mode}")
