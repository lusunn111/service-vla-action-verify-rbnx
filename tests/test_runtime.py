import math
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from vla_action_service.backend import (
    BackendError,
    DecisionRequest,
    OpenVLADecisionBackend,
)
from vla_action_service.runtime import ServiceRuntime


JPEG = b"\xff\xd8\xff" + b"\x00" * 32


class FakeAdapter:
    def __init__(self, speculative=None, target=None):
        self.speculative = speculative
        self.target = target
        self.closed = False

    def predict_speculative(self, _image_path, _instruction):
        if isinstance(self.speculative, Exception):
            raise self.speculative
        if callable(self.speculative):
            return self.speculative()
        return self.speculative

    def predict_target(self, _image_path, _instruction):
        if isinstance(self.target, Exception):
            raise self.target
        return self.target

    def close(self):
        self.closed = True


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


def test_both_inference_paths_failing_is_a_call_error():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)
        adapter = FakeAdapter(RuntimeError("draft"), RuntimeError("target"))
        backend = _backend(tmp, adapter)
        with pytest.raises(BackendError, match="both failed"):
            backend.decide(DecisionRequest("move", str(image)))


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


def test_timeout_is_reported_after_non_preemptible_inference():
    with TemporaryDirectory() as tmp:
        image = Path(tmp) / "observation.jpg"
        image.write_bytes(JPEG)

        def slow_action():
            time.sleep(0.02)
            return [0.0] * 7

        backend = _backend(tmp, FakeAdapter(speculative=slow_action))
        with pytest.raises(BackendError, match="exceeded timeout"):
            backend.decide(DecisionRequest("move", str(image), timeout_s=0.001))
