import asyncio

import pytest

from custom_components.yeelight_pro.sensor import XSensorEntity, XActionEntity
from custom_components.yeelight_pro.core.converters.base import Converter


class FakeHass:
    """Минимальный hass: нужен только loop для XActionEntity."""

    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()

    def async_create_task(self, coro):
        return self.loop.create_task(coro)


class FakeGatewayDevice:
    def __init__(self):
        self.id = "gw-device-id"


class FakeGateway:
    """Фейковый gateway, чтобы XEntity мог собрать device_info."""

    def __init__(self):
        self.host = "127.0.0.1"
        self.entry_id = "test-entry"
        self.device = FakeGatewayDevice()
        self.is_connected = True


class FakeDevice:
    """
    Лёгкая заглушка вместо XDevice для XSensorEntity/XActionEntity.
    Ожидаемые поля/методы для XEntity:
    - hass
    - gateway
    - id, name, pid, type, firmware_version
    - entities (dict)
    - subscribe_attrs(conv)
    - entity_id(conv)
    """

    def __init__(self, hass):
        self.hass = hass
        self.gateway = FakeGateway()
        self.id = "dev-1"
        self.name = "Test device"
        self.pid = "pid"
        self.type = "type"
        self.firmware_version = "1.0.0"
        self.entities = {}
        self.online = True

    def subscribe_attrs(self, conv):
        return {conv.attr}

    def entity_id(self, conv):
        return f"{conv.domain}.test_{conv.attr}"


def make_sensor_entity():
    loop = asyncio.get_event_loop()
    hass = FakeHass(loop)
    device = FakeDevice(hass)
    conv = Converter("temperature", "sensor")
    entity = XSensorEntity(device, conv)
    return entity


def make_action_entity():
    loop = asyncio.get_event_loop()
    hass = FakeHass(loop)
    device = FakeDevice(hass)
    conv = Converter("action", "sensor")
    entity = XActionEntity(device, conv)
    return entity


def test_xsensor_async_set_state_sets_native_and_attr():
    """XSensorEntity.async_set_state должен проставлять native_value и extra native_value."""
    entity = make_sensor_entity()

    data = {"temperature": 25, "extra": "foo"}

    # Метод callback — вызываем напрямую
    entity.async_set_state(data)

    # state внутри XEntity выставляется по ключу conv.attr -> "temperature"
    assert entity._attr_native_value == 25
    assert entity._attr_extra_state_attributes["native_value"] == 25


def test_xsensor_async_restore_last_state_restores_native_and_attrs():
    """XSensorEntity.async_restore_last_state восстанавливает native_value и только нужные attrs."""
    entity = make_sensor_entity()

    attrs = {
        "native_value": 30,
        "temperature": 30,
        "other": "ignored",
    }

    entity.async_restore_last_state(state="old", attrs=attrs)

    # native_value должен браться из attrs['native_value']
    assert entity._attr_native_value == 30
    # extra_state_attributes должны содержать только подписанные атрибуты и native_value
    assert entity._attr_extra_state_attributes["native_value"] == 30
    assert entity._attr_extra_state_attributes["temperature"] == 30
    assert "other" not in entity._attr_extra_state_attributes


@pytest.mark.asyncio
async def test_xaction_async_set_state_schedules_clear_and_resets(monkeypatch):
    """
    XActionEntity.async_set_state:
    - устанавливает native_value и extra attrs
    - запускает clear_state, который обнуляет native_value.
    """
    entity = make_action_entity()

    # убираем реальные вызовы HA, чтобы не требовался настоящий hass
    monkeypatch.setattr(
        entity,
        "async_write_ha_state",
        lambda *a, **k: None,
    )

    data = {"action": "single", "foo": "bar"}

    entity.async_set_state(data)

    # сразу после установки
    assert entity._attr_native_value == "single"
    assert entity._attr_extra_state_attributes == data
    assert entity.clear_task is not None
    assert not entity.clear_task.done()

    # ждём выполнения clear_state
    await asyncio.sleep(0.4)

    assert entity._attr_native_value == ""


def test_xaction_async_set_state_ignores_when_no_name_or_hass():
    """Если в data нет ключа _name или нет hass — состояние не меняется."""
    entity = make_action_entity()

    # нет ключа "action" — не должно ничего менять
    entity.async_set_state({"foo": "bar"})
    assert entity._attr_native_value == ""

    # нет hass — тоже игнор
    entity.hass = None
    entity.async_set_state({"action": "tap"})
    assert entity._attr_native_value == ""


# ---------- Fix 2: XDiagnosticsSensor must NOT block HA bootstrap ----------


@pytest.mark.asyncio
async def test_xdiagnostics_sensor_does_not_register_task_with_hass():
    """_periodic_update должен создаваться через asyncio.create_task,
    а НЕ через hass.async_create_task, чтобы не блокировать HA bootstrap.

    Регрессионный тест: hass.async_create_task добавляет задачу в hass._tasks,
    которые HA ожидает при загрузке. _periodic_update — бесконечный цикл,
    поэтому он блокировал запуск HA на ~307 секунд.
    """
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    from custom_components.yeelight_pro.core.device import GatewayDevice
    from custom_components.yeelight_pro.core.converters.base import Converter

    tasks_registered_with_hass = []

    class TrackingHass(FakeHass):
        def async_create_task(self, coro):
            tasks_registered_with_hass.append(coro)
            return self.loop.create_task(coro)

    class FakeGatewayDev(GatewayDevice):
        def __init__(self):
            gw = FakeGateway()
            super().__init__(gw)  # type: ignore[arg-type]

    hass = TrackingHass()
    device = FakeGatewayDev()
    conv = Converter("diagnostics", "sensor")

    entity = XDiagnosticsSensor(device, conv)
    entity.hass = hass  # type: ignore[assignment]
    entity.entity_id = "sensor.test_diagnostics"
    entity.added = False

    await entity.async_added_to_hass()

    # Background task must NOT have been registered via hass.async_create_task
    assert tasks_registered_with_hass == [], (
        "_periodic_update не должен регистрироваться через hass.async_create_task "
        "— это блокирует HA bootstrap"
    )

    # But the task should exist and be running
    assert entity._update_task is not None
    assert not entity._update_task.done()

    # Cleanup
    entity._update_task.cancel()
    try:
        await entity._update_task
    except asyncio.CancelledError:
        pass


# ---------- XDiagnosticsSensor: periodic update, cleanup, format_uptime ----------


def _make_diagnostics_entity():
    """Helper to create an XDiagnosticsSensor with fake gateway diagnostics."""
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    from custom_components.yeelight_pro.core.device import GatewayDevice
    from custom_components.yeelight_pro.core.converters.base import Converter

    class FakeGatewayForDiag:
        host = "10.0.0.1"
        entry_id = "entry-diag"
        device = type("D", (), {"id": "gw-0"})()
        is_connected = True
        diagnostics = {
            'connected': True,
            'success_rate': 100,
            'device_count': 3,
            'uptime_seconds': 3661,
            'messages_sent': 50,
            'messages_received': 120,
            'commands_success': 45,
            'commands_failed': 2,
            'commands_retried': 1,
            'reconnect_count': 0,
            'keepalive_total': 10,
            'keepalive_success': 10,
            'keepalive_failed': 0,
            'last_error': None,
            'transition_time': 5.0,
            'topology_cache_age': 42.0,
        }

    class FakeGatewayDev(GatewayDevice):
        def __init__(self):
            super().__init__(FakeGatewayForDiag())  # type: ignore[arg-type]

    loop = asyncio.get_event_loop()
    hass = FakeHass(loop)
    device = FakeGatewayDev()
    device._gateway_ref = FakeGatewayForDiag()
    conv = Converter("diagnostics", "sensor")

    entity = XDiagnosticsSensor(device, conv)
    entity.hass = hass  # type: ignore[assignment]
    entity.entity_id = "sensor.test_diagnostics"
    entity.added = False
    return entity


def test_update_diagnostics_sets_ok_when_connected():
    """_update_diagnostics sets native_value='OK' when connected and success_rate >= 95."""
    entity = _make_diagnostics_entity()
    entity._update_diagnostics()

    assert entity._attr_native_value == "OK"
    assert entity._attr_extra_state_attributes['connected'] is True
    assert entity._attr_extra_state_attributes['device_count'] == 3
    assert entity._attr_extra_state_attributes['messages_sent'] == 50


def test_update_diagnostics_sets_degraded():
    """_update_diagnostics sets 'Degraded' when success_rate is between 80 and 95."""
    entity = _make_diagnostics_entity()
    entity.device._gateway_ref.diagnostics['success_rate'] = 90
    entity._update_diagnostics()

    assert entity._attr_native_value == "Degraded"


def test_update_diagnostics_sets_poor():
    """_update_diagnostics sets 'Poor' when success_rate < 80."""
    entity = _make_diagnostics_entity()
    entity.device._gateway_ref.diagnostics['success_rate'] = 50
    entity._update_diagnostics()

    assert entity._attr_native_value == "Poor"


def test_update_diagnostics_sets_disconnected():
    """_update_diagnostics sets 'Disconnected' when not connected."""
    entity = _make_diagnostics_entity()
    entity.device._gateway_ref.diagnostics['connected'] = False
    entity._update_diagnostics()

    assert entity._attr_native_value == "Disconnected"


def test_update_diagnostics_no_gateway():
    """_update_diagnostics sets 'No Gateway' when _gateway_ref is missing."""
    entity = _make_diagnostics_entity()
    entity.device._gateway_ref = None
    entity._update_diagnostics()

    assert entity._attr_native_value == "No Gateway"


def test_format_uptime_seconds():
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    assert XDiagnosticsSensor._format_uptime(45) == "45s"


def test_format_uptime_minutes():
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    assert XDiagnosticsSensor._format_uptime(125) == "2m 5s"


def test_format_uptime_hours():
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    assert XDiagnosticsSensor._format_uptime(3661) == "1h 1m"


def test_format_uptime_days():
    from custom_components.yeelight_pro.sensor import XDiagnosticsSensor
    assert XDiagnosticsSensor._format_uptime(90061) == "1d 1h"


@pytest.mark.asyncio
async def test_periodic_update_calls_update_diagnostics(monkeypatch):
    """_periodic_update should call _update_diagnostics after sleep."""
    entity = _make_diagnostics_entity()
    monkeypatch.setattr(entity, "async_write_ha_state", lambda: None)

    call_count = 0
    original = entity._update_diagnostics

    def tracking_update():
        nonlocal call_count
        call_count += 1
        original()

    monkeypatch.setattr(entity, "_update_diagnostics", tracking_update)

    # Patch sleep to return immediately once, then cancel
    sleep_count = 0
    original_sleep = asyncio.sleep

    async def fast_sleep(duration):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise asyncio.CancelledError
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    try:
        await entity._periodic_update()
    except asyncio.CancelledError:
        pass

    assert call_count >= 1, "_update_diagnostics should have been called at least once"


@pytest.mark.asyncio
async def test_async_will_remove_cancels_update_task():
    """async_will_remove_from_hass should cancel _update_task cleanly."""
    entity = _make_diagnostics_entity()

    async def _forever():
        try:
            await asyncio.sleep(999)
        except asyncio.CancelledError:
            raise

    entity._update_task = asyncio.get_event_loop().create_task(_forever())
    await asyncio.sleep(0)  # let task start

    await entity.async_will_remove_from_hass()

    assert entity._update_task.done()


def test_async_set_state_triggers_update():
    """async_set_state should call _update_diagnostics."""
    entity = _make_diagnostics_entity()
    entity._attr_native_value = "initial"

    entity.async_set_state({})

    # After async_set_state, diagnostics should be refreshed from gateway
    assert entity._attr_native_value == "OK"
