"""End-to-end integration tests.

Verifies the full flow: gateway topology -> device creation -> entity setup
-> state update -> entity state reflects correctly.
"""
import asyncio
import json

import pytest

from homeassistant.components.light import ColorMode

from custom_components.yeelight_pro.core.gateway import ProGateway, MSG_SPLIT
from custom_components.yeelight_pro.core.device import (
    XDevice,
    LightDevice,
    GatewayDevice,
    MotionDevice,
    DeviceType,
    NodeType,
)
from custom_components.yeelight_pro.core.converters.base import Converter
from custom_components.yeelight_pro.light import XLightEntity
from custom_components.yeelight_pro.switch import XSwitchEntity
from custom_components.yeelight_pro.binary_sensor import XBinarySensorEntity
from custom_components.yeelight_pro.sensor import XActionEntity


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data=None):
        self.events.append((event_type, data))


class FakeHass:
    """Minimal hass that supports entity creation flow."""

    def __init__(self):
        self.bus = FakeBus()
        self.data = {}

    def async_create_task(self, coro):
        return asyncio.create_task(coro)


class E2EGateway(ProGateway):
    """Gateway that captures entity setup calls instead of using HA platform."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created_entities = []
        self._add_entities_callbacks = {}

    def register_platform(self, domain, add_entities_fn):
        """Register a fake add_entities callback for a domain."""
        self._add_entities_callbacks[domain] = add_entities_fn

    async def setup_entity(self, domain, device, conv):
        """Instead of real platform setup, create entities directly."""
        self.created_entities.append((domain, device, conv))


# ---------- Full topology -> device -> entity flow ----------


@pytest.mark.no_patch_setup
@pytest.mark.asyncio
async def test_topology_creates_light_device_with_converters():
    """Full flow: topology message -> LightDevice created -> converters set up."""
    gtw = E2EGateway("10.0.0.1", hass=FakeHass())

    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": NodeType.GATEWAY, "pid": "gateway", "type": "gateway"},
            {
                "id": 100,
                "nt": NodeType.MESH,
                "type": DeviceType.LIGHT_WITH_COLOR_TEMP,
                "n": "Ceiling Light",
                "prop": {"o": True, "params": {"p": True, "l": 80, "ct": 4000}},
            },
        ],
    }

    await gtw.on_message(json.dumps(topo).encode())

    # Gateway device created
    assert isinstance(gtw.device, GatewayDevice)

    # Light device created with correct type
    dev = gtw.devices.get(100)
    assert dev is not None
    assert isinstance(dev, LightDevice)
    assert dev.name == "Ceiling Light"

    # Converters set up correctly
    assert "light" in dev.converters
    assert "brightness" in dev.converters
    assert "color_temp" in dev.converters

    # Color modes correct
    assert ColorMode.BRIGHTNESS in dev.color_modes
    assert ColorMode.COLOR_TEMP in dev.color_modes

    # Entity setup was requested
    domains = [d for d, _, _ in gtw.created_entities if d == "light"]
    assert len(domains) >= 1


@pytest.mark.asyncio
async def test_prop_changed_updates_device_state():
    """Full flow: gateway_post.prop -> device state updated -> decode works."""
    gtw = E2EGateway("10.0.0.1", hass=FakeHass())

    # First, create device via topology
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": NodeType.GATEWAY},
            {
                "id": 200,
                "nt": NodeType.MESH,
                "type": DeviceType.LIGHT_WITH_BRIGHTNESS,
                "n": "Lamp",
                "prop": {"o": True, "params": {"p": False, "l": 50}},
            },
        ],
    }
    await gtw.on_message(json.dumps(topo).encode())

    dev = gtw.devices[200]
    assert isinstance(dev, LightDevice)

    # Now send a prop change
    prop_msg = {
        "method": "gateway_post.prop",
        "nodes": [
            {
                "id": 200,
                "nt": NodeType.MESH,
                "params": {"p": True, "l": 80},
            },
        ],
    }
    await gtw.on_message(json.dumps(prop_msg).encode())

    # Device prop should be updated
    assert dev.prop_params.get("p") is True
    assert dev.prop_params.get("l") == 80


@pytest.mark.asyncio
async def test_event_fires_to_ha_bus():
    """Full flow: gateway_post.event -> event fired on HA bus."""
    hass = FakeHass()
    gtw = E2EGateway("10.0.0.1", hass=hass)

    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": NodeType.GATEWAY},
            {
                "id": 300,
                "nt": NodeType.MESH,
                "type": DeviceType.MOTION_SENSOR,
                "n": "Motion",
                "cids": [9],
                "prop": {"o": True},
            },
        ],
    }
    await gtw.on_message(json.dumps(topo).encode())

    dev = gtw.devices[300]
    assert isinstance(dev, MotionDevice)

    # Fire event
    event_msg = {
        "method": "gateway_post.event",
        "nodes": [
            {
                "id": 300,
                "nt": NodeType.MESH,
                "value": "motion.true",
                "params": {},
            },
        ],
    }
    await gtw.on_message(json.dumps(event_msg).encode())

    # Event should be on the bus
    events = [e for e in hass.bus.events if e[0] == "yeelight_pro_event"]
    assert len(events) == 1
    assert events[0][1]["device_id"] == 300
    assert events[0][1]["event_type"] == "motion.true"


@pytest.mark.asyncio
async def test_device_disappears_from_topology_marked_offline():
    """Device removed from topology -> marked unavailable, not deleted."""
    hass = FakeHass()
    gtw = E2EGateway("10.0.0.1", hass=hass)

    # Initial topology with two devices
    topo1 = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": NodeType.GATEWAY},
            {"id": 400, "nt": NodeType.MESH, "type": DeviceType.LIGHT, "n": "Light A", "prop": {"o": True}},
            {"id": 401, "nt": NodeType.MESH, "type": DeviceType.LIGHT, "n": "Light B", "prop": {"o": True}},
        ],
    }
    await gtw.on_message(json.dumps(topo1).encode())
    assert 400 in gtw.devices
    assert 401 in gtw.devices

    # New topology without device 401
    topo2 = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": NodeType.GATEWAY},
            {"id": 400, "nt": NodeType.MESH, "type": DeviceType.LIGHT, "n": "Light A", "prop": {"o": True}},
        ],
    }
    await gtw.on_message(json.dumps(topo2).encode())

    # Device 401 still exists (not deleted) but marked offline
    assert 401 in gtw.devices
    assert gtw.devices[401].prop.get("o") is False


@pytest.mark.asyncio
async def test_light_entity_full_state_cycle():
    """Create a LightEntity, update state, verify attributes."""
    hass = FakeHass()

    node = {"id": 500, "nt": NodeType.MESH, "type": DeviceType.LIGHT_WITH_COLOR_TEMP, "n": "Test"}
    dev = LightDevice(node)
    dev.hass = hass

    class FakeGW:
        host = "10.0.0.1"
        entry_id = "test"
        device = type("D", (), {"id": "gw"})()

    dev.gateways.append(FakeGW())

    # Get light converter
    light_conv = dev.converters["light"]
    entity = XLightEntity(dev, light_conv)

    # Simulate state update
    decoded = dev.decode({
        "o": True,
        "params": {"p": True, "l": 75, "ct": 4000},
    })
    entity.async_set_state(decoded)

    assert entity._attr_is_on is True
    assert entity.brightness == round(75 / 100 * 255)
    assert entity.color_temp_kelvin == 4000

