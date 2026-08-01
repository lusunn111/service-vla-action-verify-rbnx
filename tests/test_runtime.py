import json
import math
import time
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from vla_action_service.backend import (
    BackendError,
    DecisionRequest,
    OpenVLADecisionBackend,
    ResearchModelAdapter,
)
from vla_action_service.runtime import ServiceRuntime


JPEG = b"\xff\xd8\xff" + b"\x00" * 32


class FakeAdapter:
    def __init__(self, speculative=None, target=None):
        self.speculative = speculative
        self.target = target
        self.closed = False
        self.speculative_calls = 0
        self.target_calls = 0

    def predict_speculative(self, _image_path, _instruction):
        self.speculative_calls += 1
        if isinstance(self.speculative, Exception):
            raise self.speculative
        if callable(self.speculative):
            return self.speculative()
        return self.speculative

    def predict_target(self, _image_path, _instruction):
        self.target_calls += 1
        if isinstance(self.target, Exception):
            raise self.target
        if callable(self.target):
            return self.target()
        return self.target

    def close(self):
        self.closed = True


class FailingCloseAdapter(FakeAdapter):
    def close(self):
        self.closed = True
        raise RuntimeError("cleanup failed")


def _backend(tmp: str, adapter: FakeAdapter) -> OpenVLADecisionBackend:
    backend = OpenVLADecisionBackend(
        {
            "target_checkpoint": "/not-loaded-during-config/target",
            "drafter_checkpoint": "/not-loaded-during-config/drafter",
            "allowed_image_root": tmp,
        }
    )
    backend._load_adapter = lambda: adapter
    return backend


def test_mock_lifecycle_never_returns_an_executable_action():
    runtime = ServiceRuntime()
    runtime.configure({"backend_mode": "mock"})
    runtime.activate()
    result = runtime.decide(DecisionRequest("test", "unused.jpg"))
    assert not result.success
    assert not result.actions
    assert result.mode == "mock"
    assert result.fallback_required
    runtime.shutdown()
    assert not runtime.active


def test_openvla_load_is_deferred_until_first_decide():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)
        adapter = FakeAdapter(speculative=[0.0] * 7)
        backend = _backend(tmp, adapter)
        assert backend._adapter is None
        result = backend.decide(DecisionRequest("pick up the cup", str(image)))
        assert backend._adapter is adapter
        assert result.success
        assert result.mode == "speculative"
        assert (result.action_horizon, result.action_dim) == (1, 7)
        backend.close()
        assert adapter.closed


def test_speculative_failure_reuses_target_model_for_fallback():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        adapter = FakeAdapter(RuntimeError("drafter failed"), [0.1] * 7)
        backend = _backend(tmp, adapter)
        result = backend.decide(DecisionRequest("move left", f"file://{image}"))
        assert result.success
        assert result.mode == "target_fallback"
        assert result.fallback_used
        assert not result.fallback_required


def test_target_adapter_clears_speculative_tree_state_and_uses_wrapper():
    adapter = ResearchModelAdapter.__new__(ResearchModelAdapter)
    language_model = SimpleNamespace(tree_mask="stale-language-tree")
    base_model = SimpleNamespace(language_model=language_model)
    ea_layer = SimpleNamespace(tree_mask="stale-drafter-tree")
    wrapper = SimpleNamespace(
        tree_mask="stale-wrapper-tree", base_model=base_model, ea_layer=ea_layer
    )
    calls = []
    adapter._model = wrapper
    adapter._processor = object()
    adapter._torch = SimpleNamespace(inference_mode=nullcontext)
    adapter._cfg = SimpleNamespace(
        pretrained_checkpoint="checkpoint",
        unnorm_key="libero_goal",
        center_crop=True,
    )
    adapter._observation = lambda _path: {"full_image": object()}
    adapter._get_vla_action = lambda model, *args, **kwargs: (
        calls.append((model, kwargs)) or [0.0] * 7
    )

    assert adapter.predict_target(Path("observation.jpg"), "move") == [0.0] * 7
    assert calls[0][0] is wrapper
    assert "generate_mode" not in calls[0][1]
    assert wrapper.tree_mask is None
    assert language_model.tree_mask is None
    assert ea_layer.tree_mask is None


def test_both_inference_paths_failing_is_a_call_error():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)
        adapter = FakeAdapter(RuntimeError("draft"), RuntimeError("target"))
        backend = _backend(tmp, adapter)
        with pytest.raises(BackendError, match="both failed"):
            backend.decide(DecisionRequest("move", str(image)))
        assert adapter.closed
        assert backend._adapter is None


def test_image_boundary_and_action_values_are_validated():
    with TemporaryDirectory() as allowed, TemporaryDirectory() as outside:
        outside_image = Path(outside) / "observation.jpg"
        outside_image.write_bytes(JPEG)
        backend = _backend(allowed, FakeAdapter(speculative=[0.0] * 7))
        with pytest.raises(BackendError, match="outside allowed_image_root"):
            backend.decide(DecisionRequest("move", str(outside_image)))

        image = Path(allowed) / "observation.jpg"
        image.write_bytes(JPEG)
        backend = _backend(allowed, FakeAdapter(speculative=[math.nan] * 7))
        with pytest.raises(BackendError, match="non-finite"):
            backend.decide(DecisionRequest("move", str(image)))

        backend = _backend(allowed, FakeAdapter(speculative=[True] * 7))
        with pytest.raises(BackendError, match="non-numeric"):
            backend.decide(DecisionRequest("move", str(image)))


def test_timeout_is_reported_after_non_preemptible_inference():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)

        def slow_action():
            time.sleep(0.02)
            return [0.0] * 7

        adapter = FakeAdapter(speculative=slow_action)
        backend = _backend(tmp, adapter)
        with pytest.raises(BackendError, match="exceeded timeout"):
            backend.decide(DecisionRequest("move", str(image), timeout_s=0.001))
        assert adapter.closed
        assert backend._adapter is None


def test_expired_speculative_failure_does_not_start_target_fallback():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)

        def slow_failure():
            time.sleep(0.02)
            raise RuntimeError("drafter failed")

        adapter = FakeAdapter(speculative=slow_failure, target=[0.0] * 7)
        backend = _backend(tmp, adapter)
        with pytest.raises(BackendError, match="fallback was skipped"):
            backend.decide(DecisionRequest("move", str(image), timeout_s=0.001))
        assert adapter.speculative_calls == 1
        assert adapter.target_calls == 0
        assert adapter.closed
        assert backend._adapter is None


def test_wrong_action_dimension_triggers_target_fallback():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)
        adapter = FakeAdapter(speculative=[0.0] * 6, target=[0.1] * 7)
        backend = _backend(tmp, adapter)
        result = backend.decide(DecisionRequest("move", str(image)))
        assert result.success
        assert result.mode == "target_fallback"
        assert result.action_dim == 7


def test_image_signature_must_match_extension_and_network_uri_is_rejected():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.png"
        image.write_bytes(JPEG)
        backend = _backend(tmp, FakeAdapter(speculative=[0.0] * 7))
        with pytest.raises(BackendError, match="not a supported"):
            backend.decide(DecisionRequest("move", str(image)))
        with pytest.raises(BackendError, match="only supports local"):
            backend.decide(
                DecisionRequest("move", "https://example.invalid/observation.jpg")
            )


def test_checkpoint_preflight_rejects_missing_files_and_accepts_complete_layout():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "target"
        drafter = root / "drafter"
        observations = root / "observations"
        target.mkdir()
        drafter.mkdir()
        observations.mkdir()
        backend = OpenVLADecisionBackend(
            {
                "target_checkpoint": str(target),
                "drafter_checkpoint": str(drafter),
                "allowed_image_root": str(observations),
                "unnorm_key": "libero_goal",
            }
        )
        with pytest.raises(BackendError, match="config.json"):
            backend._validate_checkpoint_layout()

        (target / "config.json").write_text("{}")
        (target / "preprocessor_config.json").write_text("{}")
        (target / "dataset_statistics.json").write_text(json.dumps({
            "libero_goal": {
                "action": {
                    "q01": [-1.0] * 7,
                    "q99": [1.0] * 7,
                    "mask": [True] * 7,
                }
            }
        }))
        (target / "model.safetensors").write_bytes(b"x" * 2048)
        (drafter / "config.json").write_text("{}")
        (drafter / "pytorch_model.bin").write_bytes(b"x" * 2048)
        backend._validate_checkpoint_layout()


def test_checkpoint_statistics_resolve_no_noops_and_enforce_action_shape():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "target"
        drafter = root / "drafter"
        observations = root / "observations"
        target.mkdir()
        drafter.mkdir()
        observations.mkdir()
        (target / "config.json").write_text("{}")
        (target / "preprocessor_config.json").write_text("{}")
        (target / "model.safetensors").write_bytes(b"x" * 2048)
        (drafter / "config.json").write_text("{}")
        (drafter / "pytorch_model.bin").write_bytes(b"x" * 2048)
        statistics_path = target / "dataset_statistics.json"
        statistics_path.write_text(json.dumps({
            "libero_goal_no_noops": {
                "action": {"q01": [-1.0] * 7, "q99": [1.0] * 7}
            }
        }))
        backend = OpenVLADecisionBackend(
            {
                "target_checkpoint": str(target),
                "drafter_checkpoint": str(drafter),
                "allowed_image_root": str(observations),
                "unnorm_key": "libero_goal",
            }
        )
        backend._validate_checkpoint_layout()
        assert backend.config["unnorm_key"] == "libero_goal_no_noops"

        statistics_path.write_text(json.dumps({
            "libero_goal_no_noops": {
                "action": {"q01": [-1.0] * 6, "q99": [1.0] * 6}
            }
        }))
        with pytest.raises(BackendError, match="expected_action_dim"):
            backend._validate_checkpoint_layout()


def test_configuration_rejects_relative_paths_and_invalid_gpu_selection():
    with TemporaryDirectory() as tmp:
        base = {
            "target_checkpoint": "/absolute/target",
            "drafter_checkpoint": "/absolute/drafter",
            "allowed_image_root": tmp,
        }
        with pytest.raises(ValueError, match="target_checkpoint must be an absolute"):
            OpenVLADecisionBackend({**base, "target_checkpoint": "relative"})
        with pytest.raises(ValueError, match="GPU indices"):
            OpenVLADecisionBackend({**base, "cuda_visible_devices": "GPU-1"})
        with pytest.raises(ValueError, match="must be a boolean"):
            OpenVLADecisionBackend({**base, "require_cuda": "false"})


def test_runtime_clears_lifecycle_state_even_when_model_cleanup_fails():
    class FailingBackend:
        def close(self):
            adapter.close()

    runtime = ServiceRuntime()
    adapter = FailingCloseAdapter(speculative=[0.0] * 7)
    runtime._backend = FailingBackend()
    runtime._active = True
    with pytest.raises(RuntimeError, match="cleanup failed"):
        runtime.shutdown()
    assert not runtime.active
    assert runtime._backend is None
