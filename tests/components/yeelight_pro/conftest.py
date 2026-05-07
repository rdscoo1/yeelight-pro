import pytest
from custom_components.yeelight_pro.core.device import XDevice
from custom_components.yeelight_pro.core.gateway import ProGateway


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def patch_setup_entities(monkeypatch):
    async def _noop(self):
        return
    monkeypatch.setattr(XDevice, "setup_entities", _noop)


@pytest.fixture(autouse=True)
def maybe_patch_setup_entities(request, monkeypatch):
    if "patch_setup_entities" not in request.keywords:
        return
    async def _noop(self):
        return
    monkeypatch.setattr(XDevice, "setup_entities", _noop)


@pytest.fixture
def gateway():
    return ProGateway("127.0.0.1")
