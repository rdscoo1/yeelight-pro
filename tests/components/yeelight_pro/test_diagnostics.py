from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yeelight_pro.core.const import CONF_GATEWAYS, DOMAIN
from custom_components.yeelight_pro.core.device import DeviceType, LightDevice, NodeType
from custom_components.yeelight_pro.core.gateway import ProGateway
from custom_components.yeelight_pro.diagnostics import async_get_config_entry_diagnostics


def _entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Gateway",
        entry_id="entry-1",
        data={CONF_HOST: "1.2.3.4"},
        options={},
    )


async def test_diagnostics_without_gateway_returns_entry_and_empty_gateway(hass):
    entry = _entry()
    entry.add_to_hass(hass)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["entry_id"] == "entry-1"
    assert result["entry"]["domain"] == DOMAIN
    assert result["entry"]["data"][CONF_HOST] != "1.2.3.4"
    assert result["gateway"] is None


async def test_diagnostics_includes_gateway_statistics_and_devices(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    gateway = ProGateway("1.2.3.4", entry_id=entry.entry_id)
    gateway.setups = {"light": object(), "sensor": object()}
    gateway._last_topology_devices = {100}
    gateway.stats.messages_sent = 3
    gateway.stats.commands_success = 2

    device = LightDevice(
        {
            "id": 100,
            "nt": NodeType.MESH,
            "type": DeviceType.LIGHT_WITH_BRIGHTNESS,
            "n": "Desk Lamp",
        }
    )
    device.prop.update({"o": True, "fv": "1.0.0"})
    gateway.devices[100] = device

    hass.data.setdefault(DOMAIN, {}).setdefault(CONF_GATEWAYS, {})[entry.entry_id] = gateway

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["gateway"]["devices_count"] == 1
    assert result["gateway"]["setups_registered"] == ["light", "sensor"]
    assert result["gateway"]["statistics"]["messages_sent"] == 3
    assert result["gateway"]["statistics"]["commands_success"] == 2
    assert result["gateway"]["devices"] == [
        {
            "id": 100,
            "name": "Desk Lamp",
            "type": DeviceType.LIGHT_WITH_BRIGHTNESS,
            "pid": None,
            "nt": NodeType.MESH,
            "online": True,
            "firmware_version": "1.0.0",
            "converters": ["light", "delay", "delayoff", "transition", "brightness"],
            "entities": [],
        }
    ]


async def test_diagnostics_redacts_host_values(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    gateway = ProGateway("1.2.3.4", entry_id=entry.entry_id)
    hass.data.setdefault(DOMAIN, {}).setdefault(CONF_GATEWAYS, {})[entry.entry_id] = gateway

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["data"][CONF_HOST] != "1.2.3.4"
    assert result["gateway"]["host"] != "1.2.3.4"
