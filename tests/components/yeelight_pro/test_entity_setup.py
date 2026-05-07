import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yeelight_pro.binary_sensor import (
    XGatewayConnectionEntity,
    setuper as binary_sensor_setuper,
)
from custom_components.yeelight_pro.button import XSceneEntity, setuper as button_setuper
from custom_components.yeelight_pro.core.const import DOMAIN
from custom_components.yeelight_pro.core.device import DeviceType, NodeType
from custom_components.yeelight_pro.core.gateway import ProGateway
from custom_components.yeelight_pro.light import XLightEntity, setuper as light_setuper
from custom_components.yeelight_pro.sensor import XDiagnosticsSensor, setuper as sensor_setuper
from custom_components.yeelight_pro.switch import XSwitchEntity, setuper as switch_setuper
from custom_components.yeelight_pro.update import XGatewayUpdateEntity, setuper as update_setuper


def _gateway_with_platform_setups(hass):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-1", unique_id="stable-gw")
    gateway = ProGateway("1.2.3.4", hass=hass, entry_id=entry.entry_id, config_entry=entry)
    added = {
        "binary_sensor": [],
        "button": [],
        "light": [],
        "sensor": [],
        "switch": [],
        "update": [],
    }
    gateway.add_setup("binary_sensor", binary_sensor_setuper(added["binary_sensor"].extend))
    gateway.add_setup("button", button_setuper(added["button"].extend))
    gateway.add_setup("light", light_setuper(added["light"].extend))
    gateway.add_setup("sensor", sensor_setuper(added["sensor"].extend))
    gateway.add_setup("switch", switch_setuper(added["switch"].extend))
    gateway.add_setup("update", update_setuper(added["update"].extend))
    return gateway, added


async def test_topology_registers_entities_through_platform_setup_callbacks(hass):
    gateway, added = _gateway_with_platform_setups(hass)

    await gateway.on_message(
        json.dumps(
            {
                "method": "gateway_post.topology",
                "nodes": [
                    {"id": 0, "nt": NodeType.GATEWAY},
                    {
                        "id": 100,
                        "nt": NodeType.MESH,
                        "type": DeviceType.LIGHT_WITH_BRIGHTNESS,
                        "n": "Desk Lamp",
                        "prop": {"o": True, "params": {"p": True, "l": 80}},
                    },
                    {
                        "id": 101,
                        "nt": NodeType.MESH,
                        "type": DeviceType.RELAY_DOUBLE,
                        "n": "Relay",
                        "prop": {"o": True, "params": {"1-p": False, "2-p": True}},
                    },
                    {
                        "id": 102,
                        "nt": NodeType.SCENE,
                        "n": "Evening",
                    },
                ],
            }
        ).encode()
    )

    light = next(entity for entity in added["light"] if isinstance(entity, XLightEntity))
    switch = next(entity for entity in added["switch"] if isinstance(entity, XSwitchEntity))
    scene = next(entity for entity in added["button"] if isinstance(entity, XSceneEntity))
    connection = next(
        entity for entity in added["binary_sensor"] if isinstance(entity, XGatewayConnectionEntity)
    )
    diagnostics = next(
        entity for entity in added["sensor"] if isinstance(entity, XDiagnosticsSensor)
    )
    update = next(entity for entity in added["update"] if isinstance(entity, XGatewayUpdateEntity))

    assert light.unique_id == "stable-gw-100-light"
    assert light.device_info["identifiers"] == {(DOMAIN, "stable-gw-100")}
    assert switch.unique_id == "stable-gw-101-switch1"
    assert scene.unique_id == "stable-gw-stable-gw-scene_102"
    assert connection.unique_id == "stable-gw-stable-gw-connection"
    assert diagnostics.unique_id == "stable-gw-stable-gw-diagnostics"
    assert update.unique_id == "stable-gw-stable-gw-firmware"


async def test_topology_removal_marks_existing_entities_unavailable(hass):
    gateway, added = _gateway_with_platform_setups(hass)

    await gateway.on_message(
        json.dumps(
            {
                "method": "gateway_post.topology",
                "nodes": [
                    {"id": 0, "nt": NodeType.GATEWAY},
                    {
                        "id": 100,
                        "nt": NodeType.MESH,
                        "type": DeviceType.LIGHT,
                        "n": "Desk Lamp",
                        "prop": {"o": True, "params": {"p": True}},
                    },
                ],
            }
        ).encode()
    )
    light = next(entity for entity in added["light"] if isinstance(entity, XLightEntity))
    assert light.available is True

    await gateway.on_message(
        json.dumps(
            {
                "method": "gateway_post.topology",
                "nodes": [{"id": 0, "nt": NodeType.GATEWAY}],
            }
        ).encode()
    )

    assert gateway.devices[100].prop["o"] is False
    assert light.available is False
