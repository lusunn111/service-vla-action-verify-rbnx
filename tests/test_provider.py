import importlib
import sys
from types import ModuleType, SimpleNamespace


class FakeResponse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeService:
    def __init__(self, id, namespace):
        self.id = id
        self.namespace = namespace

    @staticmethod
    def _decorator(function):
        return function

    on_init = _decorator
    on_activate = _decorator
    on_deactivate = _decorator
    on_shutdown = _decorator

    def mcp(self, *_args, **_kwargs):
        return self._decorator

    def run(self):
        return None


def test_provider_wires_service_lifecycle_and_non_executable_mock(monkeypatch):
    api = ModuleType("robonix_api")
    api.Service = FakeService
    api.Ok = lambda: ("ok", "")
    api.Err = lambda detail: ("err", detail)
    generated = ModuleType("action_verify_mcp")
    generated.Verify_Request = object
    generated.Verify_Response = FakeResponse
    monkeypatch.setitem(sys.modules, "robonix_api", api)
    monkeypatch.setitem(sys.modules, "action_verify_mcp", generated)
    sys.modules.pop("vla_action_service.main", None)

    provider = importlib.import_module("vla_action_service.main")
    assert provider.service.id == "vla_action_verify"
    assert provider.service.namespace == "robonix/service/vla/action_verify"
    assert provider.init({"backend_mode": "mock"})[0] == "ok"
    assert provider.activate()[0] == "ok"
    response = provider.verify(
        SimpleNamespace(instruction="test", observation_uri="unused.jpg", timeout_s=1.0)
    )
    assert not response.success
    assert not response.actions
    assert response.mode == "mock"
    assert response.fallback_required
    assert provider.deactivate()[0] == "ok"
