import pytest
from homeassistant.const import CONF_HOST

import custom_components.yeelight_pro as yp
from custom_components.yeelight_pro.core.const import DOMAIN, CONF_GATEWAYS
from custom_components.yeelight_pro.core.gateway import ProGateway


class FakeBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_name, data=None):
        self.events.append((event_name, data))


class FakeServices:
    def async_register(self, *args, **kwargs):
        # Регистрация сервисов нам в тестах не важна
        return None


class FakeHass:
    def __init__(self):
        self.bus = FakeBus()
        self.services = FakeServices()
        self.data = {DOMAIN: {CONF_GATEWAYS: {}}}


class FakeGateway(ProGateway):
    """Фейковый ProGateway, без реальных подключений."""

    def __init__(self, host: str = "1.2.3.4"):
        # НЕ вызываем super().__init__, чтобы не трогать реальную логику
        self.host = host
        self.sent: list[tuple[str, dict | None, bool]] = []
        self.on_message = None  # будет переписан в тесте

    async def send(self, method, params=None, wait_result=True, **kwargs):
        self.sent.append((method, params, wait_result))
        return {"result": "ok"}


@pytest.mark.asyncio
async def test_async_send_command_no_throw(monkeypatch):
    """Проверяем, что при throw=False уведомление не создаётся и событие шлётся."""

    hass = FakeHass()

    # Заглушаем admin-сервис, чтобы __init__ не упал
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)

    # Перехватываем persistent_notification.async_create
    notifications = []

    def fake_notify(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(yp.persistent_notification, "async_create", fake_notify)

    # Кладём фейковый gateway в hass.data
    gw = FakeGateway()
    hass.data[DOMAIN][CONF_GATEWAYS]["gw1"] = gw

    services = yp.ComponentServices(hass)

    class Call:
        data = {
            CONF_HOST: "1.2.3.4",
            "method": "test_method",
            "params": {"x": 1},
            # Явно ставим throw=False — хотим, чтобы уведомление не создавалось
            "throw": False,
        }

    result = await services.async_send_command(Call())

    # send() был вызван с нужными аргументами
    assert gw.sent == [("test_method", {"x": 1}, True)]
    # вернулся результат из gateway.send
    assert result == {"result": "ok"}

    # уведомлений не создавалось
    assert notifications == []

    # событие на шине есть и содержит нужные поля
    assert len(hass.bus.events) == 1
    event_name, event_data = hass.bus.events[0]
    assert event_name == f"{DOMAIN}.send_command"
    assert event_data["host"] == "1.2.3.4"
    assert event_data["method"] == "test_method"
    assert event_data["params"] == {"x": 1}
    assert event_data["result"] == {"result": "ok"}


@pytest.mark.asyncio
async def test_async_mock_incoming_message_calls_on_message(monkeypatch):
    """Проверяем, что mock_incoming_message вызывает gtw.on_message с байтами."""

    hass = FakeHass()

    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)

    # Заглушка уведомлений, чтобы не мешали в случае ошибок
    monkeypatch.setattr(yp.persistent_notification, "async_create", lambda *a, **k: None)

    gw = FakeGateway()
    hass.data[DOMAIN][CONF_GATEWAYS]["gw1"] = gw

    services = yp.ComponentServices(hass)

    called: dict[str, bytes] = {}

    async def fake_on_message(msg: bytes):
        called["msg"] = msg

    # Переписываем on_message на нашу корутину
    gw.on_message = fake_on_message

    valid_json = (
        '{"id": 8218, "method": "gateway_post.event", '
        '"nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}'
    )

    class Call:
        data = {
            CONF_HOST: "1.2.3.4",
            "message": valid_json,
        }

    await services.async_mock_incoming_message(Call())

    # on_message должен быть вызван и получить байты utf-8
    assert called["msg"] == valid_json.encode("utf-8")


# ---------- async_remove_stale_devices tests ----------


class FakeDeviceEntry:
    """Stub for homeassistant.helpers.device_registry.DeviceEntry."""

    def __init__(self, entry_id, name, identifiers):
        self.id = entry_id
        self.name = name
        self.identifiers = identifiers


class FakeDeviceRegistry:
    """Stub for homeassistant.helpers.device_registry.DeviceRegistry."""

    def __init__(self, entries):
        self._entries = entries
        self.removed = []

    def async_remove_device(self, device_id):
        self.removed.append(device_id)


class StaleGateway(ProGateway):
    """ProGateway stub with a real devices dict for remove_stale_devices tests."""

    def __init__(self, host="1.2.3.4", entry_id="entry-1", device_ids=None):
        self.host = host
        self.entry_id = entry_id
        self.pid = 1
        self.devices = {did: True for did in (device_ids or [])}
        self.sent = []

    async def send(self, method, params=None, wait_result=True, **kwargs):
        self.sent.append((method, params, wait_result, kwargs))
        return {"ok": True}


@pytest.mark.asyncio
async def test_remove_stale_devices_removes_missing(monkeypatch):
    """Devices not present in gateway.devices should be removed."""
    hass = FakeHass()
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)

    notifications = []
    monkeypatch.setattr(yp.persistent_notification, "async_create",
                        lambda *a, **k: notifications.append((a, k)))

    # Gateway knows about device 100 only
    gw = StaleGateway(device_ids=[100])
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] = gw

    # Device registry has device 100 (current) and device 200 (stale)
    entries = [
        FakeDeviceEntry("dev-100", "Light", {(DOMAIN, "entry-1-100")}),
        FakeDeviceEntry("dev-200", "Old Sensor", {(DOMAIN, "entry-1-200")}),
    ]
    registry = FakeDeviceRegistry(entries)

    import homeassistant.helpers.device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_entries_for_config_entry",
                        lambda reg, eid: entries)

    services = yp.ComponentServices(hass)

    class Call:
        data = {"dry_run": False}

    result = await services.async_remove_stale_devices(Call())

    assert result['count'] == 1
    assert result['removed'][0]['id'] == 200
    assert registry.removed == ["dev-200"]


@pytest.mark.asyncio
async def test_remove_stale_devices_dry_run_does_not_remove(monkeypatch):
    """dry_run=True should report stale devices but not remove them."""
    hass = FakeHass()
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)
    monkeypatch.setattr(yp.persistent_notification, "async_create", lambda *a, **k: None)

    gw = StaleGateway(device_ids=[100])
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] = gw

    entries = [
        FakeDeviceEntry("dev-100", "Light", {(DOMAIN, "entry-1-100")}),
        FakeDeviceEntry("dev-200", "Old Sensor", {(DOMAIN, "entry-1-200")}),
    ]
    registry = FakeDeviceRegistry(entries)

    import homeassistant.helpers.device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_entries_for_config_entry",
                        lambda reg, eid: entries)

    services = yp.ComponentServices(hass)

    class Call:
        data = {"dry_run": True}

    result = await services.async_remove_stale_devices(Call())

    assert result['count'] == 1
    assert registry.removed == [], "dry_run should not actually remove devices"


@pytest.mark.asyncio
async def test_remove_stale_devices_filters_by_host(monkeypatch):
    """When host is specified, only that gateway's stale devices are checked."""
    hass = FakeHass()
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)
    monkeypatch.setattr(yp.persistent_notification, "async_create", lambda *a, **k: None)

    gw1 = StaleGateway(host="1.2.3.4", entry_id="entry-1", device_ids=[100])
    gw2 = StaleGateway(host="5.6.7.8", entry_id="entry-2", device_ids=[])
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] = gw1
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-2"] = gw2

    # Only gw1 entries
    entries_gw1 = [
        FakeDeviceEntry("dev-100", "Light", {(DOMAIN, "entry-1-100")}),
        FakeDeviceEntry("dev-200", "Old", {(DOMAIN, "entry-1-200")}),
    ]
    entries_gw2 = [
        FakeDeviceEntry("dev-300", "Stale2", {(DOMAIN, "entry-2-300")}),
    ]

    def fake_entries(reg, eid):
        if eid == "entry-1":
            return entries_gw1
        return entries_gw2

    registry = FakeDeviceRegistry([])
    import homeassistant.helpers.device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_entries_for_config_entry", fake_entries)

    services = yp.ComponentServices(hass)

    class Call:
        data = {CONF_HOST: "1.2.3.4", "dry_run": False}

    result = await services.async_remove_stale_devices(Call())

    # Only gw1's stale device 200 should be removed; gw2's 300 is ignored
    assert result['count'] == 1
    assert result['removed'][0]['id'] == 200


@pytest.mark.asyncio
async def test_remove_stale_devices_skips_gateway_device(monkeypatch):
    """The gateway's own device entry (matching host) should never be removed."""
    hass = FakeHass()
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)
    monkeypatch.setattr(yp.persistent_notification, "async_create", lambda *a, **k: None)

    gw = StaleGateway(device_ids=[])
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] = gw

    entries = [
        FakeDeviceEntry("dev-gw", "Gateway", {(DOMAIN, "1.2.3.4")}),
    ]
    registry = FakeDeviceRegistry(entries)

    import homeassistant.helpers.device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_entries_for_config_entry",
                        lambda reg, eid: entries)

    services = yp.ComponentServices(hass)

    class Call:
        data = {"dry_run": False}

    result = await services.async_remove_stale_devices(Call())

    assert result['count'] == 0
    assert registry.removed == []


@pytest.mark.asyncio
async def test_remove_stale_devices_no_stale(monkeypatch):
    """When all devices are current, nothing should be removed."""
    hass = FakeHass()
    monkeypatch.setattr(yp, "async_register_admin_service", lambda *a, **k: None)
    monkeypatch.setattr(yp.persistent_notification, "async_create", lambda *a, **k: None)

    gw = StaleGateway(device_ids=[100, 200])
    hass.data[DOMAIN][CONF_GATEWAYS]["entry-1"] = gw

    entries = [
        FakeDeviceEntry("dev-100", "Light", {(DOMAIN, "entry-1-100")}),
        FakeDeviceEntry("dev-200", "Sensor", {(DOMAIN, "entry-1-200")}),
    ]
    registry = FakeDeviceRegistry(entries)

    import homeassistant.helpers.device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    monkeypatch.setattr(dr, "async_entries_for_config_entry",
                        lambda reg, eid: entries)

    services = yp.ComponentServices(hass)

    class Call:
        data = {"dry_run": False}

    result = await services.async_remove_stale_devices(Call())

    assert result['count'] == 0
    assert registry.removed == []
