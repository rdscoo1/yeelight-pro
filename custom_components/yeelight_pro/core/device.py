import asyncio
import logging
import time
from enum import IntEnum
from typing import Dict, List, Optional, TYPE_CHECKING

from .converters.base import (
    Converter,
    PropConv,
    PropBoolConv,
    PropMapConv,
    DurationConv,
    BrightnessConv,
    ColorTempKelvin,
    ColorRgbConv,
    EventConv,
    MotorConv,
    SceneConv,
)

if TYPE_CHECKING:
    from .. import XEntity
    from .gateway import ProGateway
    from homeassistant.core import HomeAssistant

from homeassistant.components.light import ColorMode
from homeassistant.components.climate import (
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
)
from homeassistant.components.climate.const import (
    HVACMode,
)

_LOGGER = logging.getLogger(__name__)

# Passive state verification settings
STATE_VERIFY_TIMEOUT = 1.5  # Seconds to wait for gateway_post.prop before retry
STATE_VERIFY_RETRIES = 2  # Number of retry attempts on state mismatch


class NodeType(IntEnum):
    GATEWAY = -1
    ROOM = 1
    MESH = 2
    GROUP = 3
    MRSH_GROUP = 4
    HOME = 5
    SCENE = 6


class DeviceType(IntEnum):
    LIGHT = 1
    LIGHT_WITH_BRIGHTNESS = 2
    LIGHT_WITH_COLOR_TEMP = 3
    LIGHT_WITH_COLOR = 4
    CURTAIN = 6
    RELAY_DOUBLE = 7
    VRF = 10
    SWITCH_PANEL = 13
    LIGHT_WITH_ZOOM_CT = 14
    AIR_CONDITIONER = 15
    SWITCH_SENSOR = 128
    MOTION_SENSOR = 129
    MAGNET_SENSOR = 130
    KNOB = 132
    MOTION_WITH_LIGHT = 134
    ILLUMINATION_SENSOR = 135
    TEMPERATURE_HUMIDITY = 136


DEVICE_TYPE_LIGHTS = [
    DeviceType.LIGHT,
    DeviceType.LIGHT_WITH_BRIGHTNESS,
    DeviceType.LIGHT_WITH_COLOR_TEMP,
    DeviceType.LIGHT_WITH_COLOR,
    DeviceType.LIGHT_WITH_ZOOM_CT,
]


class XDevice:
    hass: "HomeAssistant" = None
    converters: Dict[str, Converter] = None

    def __init__(self, node: dict):
        self.id = int(node['id'])
        self.nt = node.get('nt', 0)
        self.pid = node.get('pid')
        self.type = node.get('type', 0)
        self.name = node.get('n', '')
        self.cids = node.get('cids')
        self.ch_num = node.get('ch_num')
        self.prop = {}
        self.entities: Dict[str, "XEntity"] = {}
        self.gateways: List["ProGateway"] = []
        self.converters = {}
        self.setup_converters()
        
        # Passive state verification
        self._expected_state: Optional[Dict] = None
        self._verify_task: Optional[asyncio.Task] = None

    def setup_converters(self):
        pass

    def add_converter(self, conv: Converter):
        self.converters[conv.attr] = conv

    def add_converters(self, *args: Converter):
        for conv in args:
            self.add_converter(conv)

    @staticmethod
    async def from_node(gateway: "ProGateway", node: dict):
        if not (nid := node.get('id')):
            return None
        
        # Handle gateway node (id=0, nt=GATEWAY) to update firmware version
        if node.get('nt') == NodeType.GATEWAY:
            if gateway.device and isinstance(gateway.device, GatewayDevice):
                # Update gateway device properties from topology
                if 'prop' in node:
                    gateway.device.prop.update(node['prop'])
                if 'n' in node:
                    gateway.device.name = node['n']
                _LOGGER.debug('[%s] Gateway node updated: fv=%s', 
                             gateway.host, gateway.device.firmware_version)
                # Trigger entity updates
                await gateway.device.prop_changed(node)
            return gateway.device
        
        if node.get('nt') not in [NodeType.MESH, NodeType.GROUP, NodeType.MRSH_GROUP, NodeType.SCENE]:
            return None
        if dvc := gateway.devices.get(nid):
            if n := node.get('n'):
                dvc.name = n
            # Update device properties from topology
            if 'prop' in node:
                dvc.prop.update(node['prop'])
        else:
            dvc = XDevice(node)
            if dvc.nt in [NodeType.SCENE]:
                if isinstance(gateway.device, GatewayDevice):
                    await gateway.device.add_scene(node)
                return gateway.device
            elif dvc.nt in [NodeType.GROUP, NodeType.MRSH_GROUP]:
                dvc = GroupDevice(node)
            elif dvc.type in DEVICE_TYPE_LIGHTS:
                dvc = LightDevice(node)
            elif dvc.type in [DeviceType.SWITCH_PANEL]:
                dvc = SwitchPanelDevice(node)
            elif dvc.type in [DeviceType.RELAY_DOUBLE]:
                dvc = RelayDoubleDevice(node)
            elif dvc.type in [DeviceType.SWITCH_SENSOR]:
                dvc = KnobDevice(node)                  
            elif dvc.type in [DeviceType.KNOB]:
                dvc = KnobDevice(node)
            elif dvc.type in [DeviceType.MOTION_SENSOR, DeviceType.MOTION_WITH_LIGHT]:
                dvc = MotionDevice(node)
            elif dvc.type in [DeviceType.MAGNET_SENSOR]:
                dvc = ContactDevice(node)
            elif dvc.type in [DeviceType.CURTAIN]:
                dvc = CoverDevice(node)
            elif dvc.type in [DeviceType.AIR_CONDITIONER]:
                dvc = ClimateDevice(node)
            else:
                _LOGGER.warning('Unsupported device: %s', node)
                return None
            if gateway.pid == 2:
                await gateway.get_node(dvc.id, wait_result=False)
            await gateway.add_device(dvc)
        return dvc

    @staticmethod
    async def from_nodes(gateway: "ProGateway", nodes: List[dict]):
        res = []
        for node in nodes:
            dvc = await XDevice.from_node(gateway, node)   # ← await
            if dvc is not None:
                res.append(dvc)
        return res

    async def prop_changed(self, data: dict):
        has_new = False
        for k in data.keys():
            if k not in self.prop:
                has_new = True
                break
        self.prop.update(data)
        if has_new:
            self.setup_converters()
            await self.setup_entities()
        self.update(self.decode(data))
        
        # Check if this update matches expected state from passive verification
        if self._expected_state:
            params = data.get('params', {})
            expected_power = self._expected_state.get('power')
            actual_power = params.get('p')
            
            if actual_power == expected_power:
                # State matched - cancel verification task
                _LOGGER.debug('[%s] State verified via gateway_post.prop: p=%s', self.id, actual_power)
                if self._verify_task and not self._verify_task.done():
                    self._verify_task.cancel()
                self._expected_state = None

    async def event_fired(self, data: dict):
        decoded = self.decode_event(data)
        self.update(decoded)
        self._fire_ha_event(data, decoded)
        _LOGGER.debug('Event fired: %s', [data, decoded])

    def _fire_ha_event(self, raw_data: dict, decoded: dict) -> None:
        """Fire event to Home Assistant event bus."""
        if not self.hass:
            return
        event_type = raw_data.get('value') or raw_data.get('type')
        if not event_type:
            return
        
        from .const import DOMAIN
        event_data = {
            'device_id': self.id,
            'device_name': self.name,
            'device_type': self.type,
            'event_type': event_type,
            'params': raw_data.get('params') or {},
            'decoded': decoded,
        }
        if self.gateway:
            event_data['gateway_host'] = self.gateway.host
        
        self.hass.bus.async_fire(f"{DOMAIN}_event", event_data)

    @property
    def gateway(self):
        if self.gateways:
            return self.gateways[0]
        return None

    @property
    def online(self):
        return self.prop.get('o')

    @property
    def firmware_version(self):
        return self.prop.get('fv')

    @property
    def prop_params(self):
        return self.prop.get('params') or {}

    @property
    def unique_id(self):
        return f'{self.type}_{self.id}'

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.yp{self.unique_id}_{conv.attr}'

    async def setup_entities(self):
        gateway = self.gateway
        if not gateway:
            return
        if not self.converters:
            _LOGGER.warning('Device has none converters: %s', [type(self), self.id])
            return
        
        # Collect converters that need setup
        pending = [
            conv for conv in self.converters.values()
            if conv.domain and conv.attr not in self.entities
        ]
        
        if not pending:
            return
        
        # Setup all entities in one batch to avoid task storm
        for conv in pending:
            await gateway.setup_entity(conv.domain, self, conv)

    def subscribe_attrs(self, conv: Converter):
        attrs = {conv.attr}
        if conv.childs:
            attrs |= set(conv.childs)
        attrs.update(c.attr for c in self.converters.values() if c.parent == conv.attr)
        return attrs

    def decode(self, value: dict) -> dict:
        """Decode device props for HA."""
        payload = {}
        if 'o' in value:
            payload['available'] = value['o']
        if 'fv' in value:
            payload['firmware_version'] = value['fv']
        if 'nfv' in value:
            payload['new_firmware_version'] = value['nfv']
        if 'fu' in value:
            payload['firmware_update_available'] = value['fu']
        for conv in self.converters.values():
            prop = conv.prop or conv.attr
            data = value
            if isinstance(conv, PropConv):
                data = value.get('params') or {}
            if prop not in data:
                continue
            conv.decode(self, payload, data[prop])
        return payload

    def decode_event(self, data: dict) -> dict:
        """Decode device event for HA."""
        payload = {}
        event = data.get('value') or data.get('type')
        if conv := self.converters.get(event):
            value = data.get('params') or {}
            conv.decode(self, payload, value)
        return payload

    def encode(self, value: dict) -> dict:
        """Encode payload for device."""
        payload = {}
        for conv in self.converters.values():
            if conv.attr not in value:
                continue
            if isinstance(conv, PropConv):
                dat = payload.setdefault('set', {})
            else:
                dat = payload
            conv.encode(self, dat, value[conv.attr])
        return payload

    def encode_read(self, attrs: set) -> dict:
        payload = {}
        for conv in self.converters.values():
            if conv.attr not in attrs:
                continue
            conv.read(self, payload)
        return payload

    def update(self, value: dict):
        """Push new state to Hass entities."""
        if not value:
            return
        attrs = set(value.keys())
        has_available = 'available' in value

        for entity in self.entities.values():
            if has_available or (entity.subscribed_attrs & attrs):
                entity.async_set_state(value)
                if entity.added:
                    entity.async_write_ha_state()

    async def get_node(self):
        if not self.gateway:
            return None
        return await self.gateway.send('gateway_get.node', params={'id': self.id})

    async def _verify_state_later(self, expected_power: bool, retry_cmd: str, retry_node: dict, attempt: int = 0):
        """Passive state verification - waits for gateway_post.prop, retries if mismatch.
        
        This method waits for STATE_VERIFY_TIMEOUT seconds. If gateway_post.prop arrives
        with matching state, prop_changed() cancels this task. If timeout occurs and state
        still doesn't match, retries the command.
        
        Zero overhead: no additional gateway requests, uses existing gateway_post.prop messages.
        """
        try:
            await asyncio.sleep(STATE_VERIFY_TIMEOUT)
            
            # If we reach here, timeout occurred without state update
            if not self._expected_state:
                # State was already verified and cleared by prop_changed
                return
            
            # Check current state
            actual_power = self.prop.get('params', {}).get('p')
            
            if actual_power == expected_power:
                # State matches now
                _LOGGER.debug('[%s] State verified after timeout: p=%s', self.id, actual_power)
                self._expected_state = None
                return
            
            # State mismatch - retry
            if attempt < STATE_VERIFY_RETRIES:
                if self.gateway:
                    self.gateway.stats.state_mismatches += 1
                _LOGGER.warning(
                    '[%s] State mismatch after %.1fs: expected p=%s, actual p=%s (retry %d/%d)',
                    self.id, STATE_VERIFY_TIMEOUT, expected_power, actual_power, 
                    attempt + 1, STATE_VERIFY_RETRIES
                )
                
                # Retry command
                result = await self.gateway.send(retry_cmd, nodes=[retry_node])
                if result and self.gateway:
                    self.gateway.stats.state_corrections += 1
                    _LOGGER.info('[%s] State correction command sent', self.id)
                    
                    # Schedule next verification
                    self._verify_task = asyncio.create_task(
                        self._verify_state_later(expected_power, retry_cmd, retry_node, attempt + 1)
                    )
            else:
                _LOGGER.error(
                    '[%s] State verification failed after %d retries: expected p=%s, actual p=%s',
                    self.id, STATE_VERIFY_RETRIES, expected_power, actual_power
                )
                self._expected_state = None
                
        except asyncio.CancelledError:
            # Task was cancelled by prop_changed - state matched
            pass

    async def set_prop(self, **kwargs):
        """Set device properties with passive state verification.
        
        After sending command, schedules verification task that waits for gateway_post.prop.
        If state doesn't match within timeout, automatically retries the command.
        
        Zero overhead: no additional gateway requests in normal case.
        """
        if not self.gateway:
            return None
        
        cmd = kwargs.pop('method', 'gateway_set.prop')
        verify = kwargs.pop('verify', True)
        
        # Extract expected power state for verification
        expected_power = kwargs.get('set', {}).get('p') if 'set' in kwargs else None
        
        node = {
            'id': self.id,
            'nt': self.nt,
            **kwargs,
        }
        
        result = await self.gateway.send(cmd, nodes=[node])
        
        # Schedule passive verification if enabled and power state is being set
        if verify and result and expected_power is not None:
            # Cancel previous verification if exists
            if self._verify_task and not self._verify_task.done():
                self._verify_task.cancel()
            
            # Store expected state
            self._expected_state = {
                'power': expected_power,
                'timestamp': time.time(),
            }
            
            # Schedule verification
            self._verify_task = asyncio.create_task(
                self._verify_state_later(expected_power, cmd, node)
            )
            _LOGGER.debug('[%s] Scheduled passive verification for p=%s', self.id, expected_power)
        
        return result


class GatewayDevice(XDevice):
    def __init__(self, gateway: "ProGateway"):
        super().__init__({
            'id': 0,
            'nt': NodeType.GATEWAY,
            'pid': 'gateway',
            'type': 'gateway',
        })
        self.id = gateway.host
        self.name = 'Yeelight Pro'
        self._gateway_ref = gateway
        # Re-setup converters after changing id
        self.setup_converters()

    def setup_converters(self):
        super().setup_converters()
        self.add_converter(Converter('connection', 'binary_sensor', device_class='connectivity'))
        self.add_converter(Converter('firmware', 'update'))
        self.add_converter(Converter('diagnostics', 'sensor'))

    @property
    def online(self):
        if self._gateway_ref:
            return self._gateway_ref.is_connected
        return None

    async def add_scene(self, node: dict):
        if not (nid := node.get('id')):
            return
        self.add_converter(SceneConv(f'scene_{nid}', 'button', node=node))
        await self.setup_entities()

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.yp_{conv.attr}'


class LightDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(PropBoolConv('light', 'light', prop='p'))
        self.add_converter(DurationConv('delay', parent='light'))
        self.add_converter(DurationConv('delayoff', 'number', readable=False))
        self.add_converter(DurationConv('transition', prop='duration', parent='light'))
        if ColorMode.BRIGHTNESS in self.color_modes:
            self.add_converter(BrightnessConv('brightness', prop='l', parent='light'))
        if ColorMode.COLOR_TEMP in self.color_modes:
            self.add_converter(ColorTempKelvin('color_temp', prop='ct', parent='light'))
        if ColorMode.RGB in self.color_modes:
            self.add_converter(ColorRgbConv('rgb_color', prop='c', parent='light'))
        if self.type == DeviceType.LIGHT_WITH_ZOOM_CT:
            self.add_converter(PropConv('angel', 'number'))

    @property
    def color_modes(self):
        modes = {
            ColorMode.ONOFF,
        }
        if self.type == DeviceType.LIGHT_WITH_BRIGHTNESS:
            modes.add(ColorMode.BRIGHTNESS)
        if self.type == DeviceType.LIGHT_WITH_COLOR_TEMP:
            modes.add(ColorMode.BRIGHTNESS)
            modes.add(ColorMode.COLOR_TEMP)
        if self.type == DeviceType.LIGHT_WITH_COLOR:
            modes.add(ColorMode.BRIGHTNESS)
            modes.add(ColorMode.COLOR_TEMP)
            modes.add(ColorMode.RGB)
        return modes


class ActionDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(Converter('action', 'sensor'))


class SwitchSensorDevice(ActionDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converters(
            EventConv('panel.click'),
            EventConv('panel.hold'),
            EventConv('panel.release'),
        )


class RelayDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        switches = self.switches
        if len(switches) == 1:
            self.add_converter(PropBoolConv('switch', 'switch', prop='1-p'))
        else:
            for i, p in self.switches.items():
                self.add_converter(PropBoolConv(f'switch{i}', 'switch', prop=f'{i}-p'))

    @property
    def switches(self):
        lst = {}
        for i in range(1, 9):
            if (p := self.switch_power(i)) is None:
                continue
            lst[i] = p
        return lst

    def switch_power(self, index=1):
        return self.prop_params.get(f'{index}-p')


class SwitchPanelDevice(RelayDevice, SwitchSensorDevice):
    def setup_converters(self):
        super().setup_converters()
        SwitchSensorDevice.setup_converters(self)

        switches = self.switches
        if len(switches) == 1:
            self.add_converter(PropBoolConv('switch', 'switch', prop='1-sp'))
        else:
            for i, p in self.switches.items():
                self.add_converter(PropBoolConv(f'switch{i}', 'switch', prop=f'{i}-sp'))
        if '0-blp' in self.prop_params:
            self.add_converter(PropBoolConv('backlight', 'light', prop='0-blp'))

    def switch_power(self, index=1):
        return self.prop_params.get(f'{index}-sp')


class RelayDoubleDevice(XDevice):
    def setup_converters(self):
        self.add_converters(
            PropBoolConv('switch1', 'switch', prop='1-p'),
            PropBoolConv('switch2', 'switch', prop='2-p')
        )


class KnobDevice(SwitchSensorDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(EventConv('knob.spin'))


class MotionDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converters(PropBoolConv('motion', 'binary_sensor', prop="mv"))
        self.add_converter(EventConv('motion.true'))
        self.add_converter(EventConv('motion.false'))
        if self.type in [DeviceType.MOTION_WITH_LIGHT]:
            self.add_converter(PropConv('light', 'sensor', prop='level'))
        
        # This is a presence sensor with a built-in light sensor. Its type is still defined as 129,
        # so we can only temporarily distinguish it by the `cids` value.
        if 73 in self.cids:
            # Regular presence sensors use cids = [9], while ceiling-mounted sensors with light detection use cids = [73].
            self.add_converter(PropConv(
                    attr='luminance',
                    domain='sensor',
                    prop='luminance',
                    unit_of_measurement='lx',
                    device_class='illuminance'
            ))

            # Currently, `approach.true` and `approach.false` seem to behave the same as `mv` (motion).


class ContactDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(Converter('contact', 'binary_sensor'))
        self.add_converter(EventConv('contact.open'))
        self.add_converter(EventConv('contact.close'))


class CoverDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converters(
            MotorConv('motor', 'cover'),
            PropConv('position', parent='motor', prop='tp'),
            PropConv('current_position', parent='motor', prop='cp'),
        )
        if 'rs' in self.prop_params:
            self.add_converter(PropBoolConv('reverse', 'switch', prop='rs'))


class WifiPanelDevice(RelayDoubleDevice):
    def __init__(self, node: dict):
        super().__init__({
            **node,
            'type': 'wifi_panel',
        })
        self.name = 'Yeelight Wifi Panel'

    async def set_prop(self, **kwargs):
        kwargs['method'] = 'device_set.prop'
        return await super().set_prop(**kwargs)

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.yp_{self.id}_{conv.attr}'

    def setup_converters(self):
        super().setup_converters()
        self.add_converter(Converter('action', 'sensor'))
        self.add_converter(EventConv('keyClick'))


class ClimateDevice(XDevice):
    def setup_converters(self):
        super().setup_converters()
        self.add_converter(Converter('climate', 'climate'))
        self.add_converter(PropBoolConv('is_on', parent='climate', prop='1-acp'))
        self.add_converter(PropConv('current_temperature', parent='climate', prop='1-acct'))
        self.add_converter(PropConv('target_temperature', parent='climate', prop='1-actt'))
        self.add_converter(PropMapConv('mode', parent='climate', prop='1-acm', map={
            1: HVACMode.COOL,
            2: HVACMode.DRY,
            4: HVACMode.FAN_ONLY,
            8: HVACMode.HEAT
        }))
        self.add_converter(PropMapConv('fan_mode', parent='climate', prop='1-acf', map={
            1: FAN_HIGH,
            2: FAN_MEDIUM,
            4: FAN_LOW
        }))
        
        # NYI
        # acd: Air conditioner delay switch remaining time (unit: milliseconds)
        # aco: Whether the air conditioner is online (air conditioner online status)


class GroupDevice(XDevice):
    """Device representing a group of lights from the gateway."""
    
    def __init__(self, node: dict):
        super().__init__(node)
        self.member_ids = node.get('cids') or []
        self.name = node.get('n') or f'Group {self.id}'

    def setup_converters(self):
        super().setup_converters()
        self.add_converter(PropBoolConv('light', 'light', prop='p'))
        self.add_converter(DurationConv('delay', parent='light'))
        self.add_converter(DurationConv('delayoff', 'number', readable=False))
        self.add_converter(DurationConv('transition', prop='duration', parent='light'))
        self.add_converter(BrightnessConv('brightness', prop='l', parent='light'))
        self.add_converter(ColorTempKelvin('color_temp', prop='ct', parent='light'))

    @property
    def color_modes(self):
        return {ColorMode.ONOFF, ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP}

    @property
    def online(self):
        return True

    def entity_id(self, conv: Converter):
        return f'{conv.domain}.yp_group_{self.id}_{conv.attr}'