import pytest

import custom_components.yeelight_pro as yp
from custom_components.yeelight_pro import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
    async_add_setuper,
    ComponentServices,
)
from custom_components.yeelight_pro.core.const import (
    DOMAIN,
    CONF_GATEWAYS,
    SUPPORTED_DOMAINS,
)
from custom_components.yeelight_pro.core.gateway import ProGateway
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from pytest_homeassistant_custom_component.common import MockConfigEntry


# ---------- Вспомогательные заглушки ----------


class FakeHassForSetup:
    """Минимальный hass для теста async_setup."""

    def __init__(self):
        self.data = {}
        self.discovery_calls = []


class FakeServices:
    def __init__(self):
        self.registered = []

    def async_register(self, domain, service, handler, schema=None):
        self.registered.append((domain, service, handler, schema))


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, event_data):
        self.events.append((event_type, event_data))


class FakeHassForComponent:
    """Hass, достаточный для ComponentServices / mock_incoming_message."""

    def __init__(self):
        self.data = {DOMAIN: {CONF_GATEWAYS: {}}}
        self.services = FakeServices()
        self.bus = FakeBus()


class FakeCall:
    def __init__(self, data: dict):
        self.data = data


class LifecycleGateway:
    def __init__(self, host="1.2.3.4"):
        self.host = host
        self.started = False
        self.stop_calls = 0

    async def start(self):
        self.started = True

    async def stop(self, *_args):
        self.stop_calls += 1


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Gateway",
        entry_id="entry-1",
        data={CONF_HOST: "1.2.3.4"},
    )


@pytest.mark.asyncio
async def test_async_setup_entry_forwards_platforms_starts_gateway_and_stops_on_hass_stop(
    hass, monkeypatch, config_entry
):
    config_entry.add_to_hass(hass)
    gateway = LifecycleGateway()
    forwarded = []

    async def fake_forward_entry_setups(entry, domains):
        forwarded.append((entry, domains))

    async def fake_get_gateway_from_config(hass_, entry):
        hass_.data[DOMAIN][CONF_GATEWAYS][entry.entry_id] = gateway
        return gateway

    monkeypatch.setattr(
        hass.config_entries,
        "async_forward_entry_setups",
        fake_forward_entry_setups,
    )
    monkeypatch.setattr(yp, "get_gateway_from_config", fake_get_gateway_from_config)

    assert await async_setup_entry(hass, config_entry) is True

    assert forwarded == [(config_entry, SUPPORTED_DOMAINS)]
    assert gateway.started is True
    assert hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] is gateway

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert gateway.stop_calls == 1


@pytest.mark.asyncio
async def test_async_unload_entry_stops_gateway_and_removes_data(hass, monkeypatch, config_entry):
    yp.init_integration_data(hass)
    gateway = LifecycleGateway()
    hass.data[DOMAIN][CONF_GATEWAYS][config_entry.entry_id] = gateway
    unloaded = []

    async def fake_unload_platforms(entry, domains):
        unloaded.append((entry, domains))
        return True

    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", fake_unload_platforms)

    assert await async_unload_entry(hass, config_entry) is True

    assert unloaded == [(config_entry, SUPPORTED_DOMAINS)]
    assert gateway.stop_calls == 1
    assert config_entry.entry_id not in hass.data[DOMAIN][CONF_GATEWAYS]


@pytest.mark.asyncio
async def test_async_unload_entry_leaves_gateway_when_platform_unload_fails(
    hass, monkeypatch, config_entry
):
    yp.init_integration_data(hass)
    gateway = LifecycleGateway()
    hass.data[DOMAIN][CONF_GATEWAYS][config_entry.entry_id] = gateway

    async def fake_unload_platforms(entry, domains):
        return False

    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", fake_unload_platforms)

    assert await async_unload_entry(hass, config_entry) is False

    assert gateway.stop_calls == 0
    assert hass.data[DOMAIN][CONF_GATEWAYS][config_entry.entry_id] is gateway


@pytest.mark.asyncio
async def test_update_listener_reloads_entry(hass, monkeypatch, config_entry):
    reloaded = []

    async def fake_reload(entry_id):
        reloaded.append(entry_id)

    monkeypatch.setattr(hass.config_entries, "async_reload", fake_reload)

    await yp._async_update_listener(hass, config_entry)

    assert reloaded == [config_entry.entry_id]


@pytest.mark.asyncio
async def test_reload_service_loads_yaml_and_reloads_entries_and_platforms(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-1", data={CONF_HOST: "1.2.3.4"})
    yaml_config = {DOMAIN: {CONF_GATEWAYS: [{CONF_HOST: "1.2.3.4"}]}}
    reloaded_entries = []
    reloaded_platforms = []

    async def fake_yaml_config(hass_, domain):
        return yaml_config

    monkeypatch.setattr(yp, "async_integration_yaml_config", fake_yaml_config)
    def fake_async_entries(domain=None):
        return [entry] if domain == DOMAIN else []

    monkeypatch.setattr(hass.config_entries, "async_entries", fake_async_entries)

    async def fake_reload(entry_id):
        reloaded_entries.append(entry_id)

    async def fake_reload_platforms(hass_, domain, platforms):
        reloaded_platforms.append((domain, platforms))

    monkeypatch.setattr(hass.config_entries, "async_reload", fake_reload)
    monkeypatch.setattr(yp, "async_reload_integration_platforms", fake_reload_platforms)

    yp.init_integration_data(hass)
    services = ComponentServices(hass)
    await services.handle_reload_config(FakeCall({}))

    assert hass.data[DOMAIN]["config"] == yaml_config[DOMAIN]
    assert reloaded_entries == ["entry-1"]
    assert reloaded_platforms == [(DOMAIN, SUPPORTED_DOMAINS)]


# ---------- Тест async_setup ----------


@pytest.mark.asyncio
async def test_async_setup_creates_gateways_and_loads_platforms(monkeypatch):
    """Проверяем, что async_setup создаёт gateway и поднимает платформы."""

    hass = FakeHassForSetup()
    created_gateway = []
    discovery_calls = []

    class FakeGateway:
        def __init__(self, host, **kwargs):
            self.host = host
            self.started = False
            created_gateway.append(self)

        async def start(self):
            self.started = True

    async def fake_get_gateway_from_config(hass_, cfg, renew=False):
        return FakeGateway(cfg[CONF_HOST])

    async def fake_async_load_platform(hass_, domain, component, config, discovery_info=None):
        discovery_calls.append((domain, component, config, discovery_info))

    # Подменяем get_gateway_from_config и ComponentServices,
    # чтобы не тянуть реальные зависимости HA.
    monkeypatch.setattr(
        "custom_components.yeelight_pro.get_gateway_from_config",
        fake_get_gateway_from_config,
        raising=True,
    )
    monkeypatch.setattr(
        "custom_components.yeelight_pro.discovery.async_load_platform",
        fake_async_load_platform,
        raising=True,
    )

    class DummyComponentServices:
        def __init__(self, hass_):
            self.hass = hass_

    monkeypatch.setattr(
        "custom_components.yeelight_pro.ComponentServices",
        DummyComponentServices,
        raising=True,
    )

    hass_config = {
        DOMAIN: {
            CONF_GATEWAYS: [
                {CONF_HOST: "1.2.3.4"},
            ],
        },
    }

    result = await async_setup(hass, hass_config)
    assert result is True

    # В hass.data должен появиться gateway, привязанный к host
    assert DOMAIN in hass.data
    assert CONF_GATEWAYS in hass.data[DOMAIN]
    assert hass.data[DOMAIN][CONF_GATEWAYS]["1.2.3.4"] is created_gateway[0]

    # Проверяем, что все платформы были переданы в discovery.async_load_platform
    from custom_components.yeelight_pro.core.const import SUPPORTED_DOMAINS

    called_domains = [c[0] for c in discovery_calls]
    for dom in SUPPORTED_DOMAINS:
        assert dom in called_domains

    # Gateway должен быть стартован
    assert created_gateway[0].started is True


# ---------- Тест async_add_setuper ----------


@pytest.mark.asyncio
async def test_async_add_setuper_adds_setup_when_gateway_is_progateway(monkeypatch):
    """Проверяем, что async_add_setuper вызывает add_setup у ProGateway."""

    hass = object()  # hass в get_gateway_from_config нам не важен

    captured = {}

    class FakeProGateway(ProGateway):
        def __init__(self):
            super().__init__("1.2.3.4")
            self.setups = {}

        def add_setup(self, domain, handler):
            captured["domain"] = domain
            captured["handler"] = handler

    async def fake_get_gateway_from_config(hass_, cfg, renew=False):
        return FakeProGateway()

    monkeypatch.setattr(
        "custom_components.yeelight_pro.get_gateway_from_config",
        fake_get_gateway_from_config,
        raising=True,
    )

    async def dummy_setuper(device, conv):
        pass

    config = {"some": "config"}

    await async_add_setuper(hass, config, "light", dummy_setuper)

    assert captured["domain"] == "light"
    assert captured["handler"] is dummy_setuper


# ---------- Тест async_mock_incoming_message (невалидный JSON) ----------


@pytest.mark.asyncio
async def test_async_mock_incoming_message_invalid_json_creates_notification(monkeypatch):
    """
    Если message нельзя распарсить ни как JSON, ни как literal_eval,
    должен создаваться persistent_notification и метод возвращает False.
    """
    hass = FakeHassForComponent()
    gw = ProGateway("1.2.3.4")
    hass.data[DOMAIN][CONF_GATEWAYS][gw.host] = gw

    # Подменяем async_register_admin_service, чтобы конструктор ComponentServices не упал
    monkeypatch.setattr(
        "custom_components.yeelight_pro.async_register_admin_service",
        lambda *a, **k: None,
        raising=True,
    )

    # Подменяем persistent_notification.async_create, чтобы отловить вызов
    created = {}

    def fake_notification_create(hass_, message, title=None, notification_id=None):
        created["hass"] = hass_
        created["message"] = message
        created["title"] = title
        created["notification_id"] = notification_id

    monkeypatch.setattr(
        "custom_components.yeelight_pro.persistent_notification.async_create",
        fake_notification_create,
        raising=True,
    )

    services = ComponentServices(hass)

    call = FakeCall(
        {
            CONF_HOST: "1.2.3.4",
            "message": "not-a-json-and-not-a-dict",  # гарантированно не распарсится
        }
    )

    result = await services.async_mock_incoming_message(call)

    assert result is False
    # Убедимся, что нотификация создалась
    assert created["hass"] is hass
    assert "Invalid JSON" in created["message"]
    assert created["title"] == "Yeelight Pro mock incoming message"
    assert created["notification_id"].endswith("-debug")
