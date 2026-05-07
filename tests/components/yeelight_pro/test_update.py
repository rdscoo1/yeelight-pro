from custom_components.yeelight_pro.core.converters.base import Converter
from custom_components.yeelight_pro.core.device import (
    DeviceType,
    GatewayDevice,
    LightDevice,
    NodeType,
)
from custom_components.yeelight_pro.core.gateway import ProGateway
from custom_components.yeelight_pro.update import (
    XGatewayUpdateEntity,
    XUpdateEntity,
    setuper,
)


def _gateway(hass):
    gateway = ProGateway("1.2.3.4", hass=hass, entry_id="entry-1")
    gateway.device = type("GatewayRef", (), {"id": "gateway"})()
    return gateway


def _light_device(hass, online=True, firmware_version="1.0.0"):
    device = LightDevice(
        {
            "id": 100,
            "nt": NodeType.MESH,
            "type": DeviceType.LIGHT,
            "n": "Desk Lamp",
        }
    )
    device.hass = hass
    device.prop.update({"o": online, "fv": firmware_version})
    device.gateways.append(_gateway(hass))
    return device


def test_update_setuper_creates_device_firmware_entity(hass):
    added = []
    device = _light_device(hass)
    setup = setuper(added.extend)

    setup(device, Converter("firmware", "update"))

    assert len(added) == 1
    assert isinstance(added[0], XUpdateEntity)
    assert not isinstance(added[0], XGatewayUpdateEntity)
    assert device.entities["firmware"] is added[0]


def test_update_setuper_creates_gateway_firmware_entity(hass):
    added = []
    gateway = ProGateway("1.2.3.4", hass=hass, entry_id="entry-1")
    device = GatewayDevice(gateway)
    device.hass = hass
    device.gateways.append(gateway)
    setup = setuper(added.extend)

    setup(device, Converter("firmware", "update"))

    assert len(added) == 1
    assert isinstance(added[0], XGatewayUpdateEntity)
    assert added[0]._attr_name == "Gateway Firmware"


def test_update_entity_tracks_installed_and_latest_versions(hass):
    device = _light_device(hass, firmware_version="1.0.0")
    entity = XUpdateEntity(device, Converter("firmware", "update"))

    entity.async_set_state(
        {
            "firmware_version": "1.0.1",
            "new_firmware_version": "1.0.2",
            "firmware_update_available": True,
        }
    )

    assert entity.installed_version == "1.0.1"
    assert entity.latest_version == "1.0.2"


def test_update_entity_availability_follows_device_online_state(hass):
    online_device = _light_device(hass, online=True)
    offline_device = _light_device(hass, online=False)

    assert XUpdateEntity(online_device, Converter("firmware", "update")).available is True
    assert XUpdateEntity(offline_device, Converter("firmware", "update")).available is False


def test_gateway_update_entity_is_always_available(hass):
    gateway = ProGateway("1.2.3.4", hass=hass, entry_id="entry-1")
    device = GatewayDevice(gateway)
    device.hass = hass
    device.gateways.append(gateway)

    entity = XGatewayUpdateEntity(device, Converter("firmware", "update"))

    assert entity.available is True
