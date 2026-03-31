"""The component."""
import json
import logging
import asyncio
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.const import (
    CONF_HOST,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_RELOAD,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.reload import (
    async_integration_yaml_config,
    async_reload_integration_platforms,
)
from homeassistant.components import persistent_notification
from homeassistant.helpers import discovery
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .core.const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_GATEWAYS,
    SUPPORTED_DOMAINS,
)
from .core.gateway import ProGateway
from .core.device import XDevice, GatewayDevice, WifiPanelDevice
from .core.converters.base import Converter

_LOGGER = logging.getLogger(__name__)

GATEWAY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_GATEWAYS): vol.All(cv.ensure_list, [GATEWAY_SCHEMA]),
            },
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


def init_integration_data(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(CONF_GATEWAYS, {})


async def async_setup(hass: HomeAssistant, hass_config: dict):
    init_integration_data(hass)

    gws = hass_config.get(DOMAIN, {}).get(CONF_GATEWAYS) or []
    for gwc in gws:
        host = gwc.get(CONF_HOST)
        if not host:
            continue
        gtw = await get_gateway_from_config(hass, gwc)
        gwc['gateway'] = gtw
        hass.data[DOMAIN][CONF_GATEWAYS][host] = gtw

        await asyncio.gather(
            *[
                discovery.async_load_platform(hass, domain, DOMAIN, gwc, gwc)
                for domain in SUPPORTED_DOMAINS
            ]
        )
        await gtw.start()

    ComponentServices(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    init_integration_data(hass)
    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_DOMAINS)

    if gtw := await get_gateway_from_config(hass, entry):
        await gtw.start()
        # Register cleanup on HA stop (unregistered automatically on entry unload)
        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, gtw.stop)
        )
        # Note: async_unload_entry handles stop() on entry unload/reload
    
    # Listen for options updates to restart gateway with new config
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update - restart gateway with new configuration."""
    _LOGGER.debug('Config entry updated, reloading: %s', entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_DOMAINS)
    if unload_ok:
        gtw = hass.data[DOMAIN][CONF_GATEWAYS].pop(entry.entry_id, None)
        if gtw:
            await gtw.stop()
    return unload_ok


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry):
    """Supported from Hass v2022.3"""
    dr.async_get(hass).async_remove_device(device.id)


async def async_add_setuper(hass: HomeAssistant, config, domain, setuper):
    gtw = await get_gateway_from_config(hass, config)
    if isinstance(gtw, ProGateway):
        gtw.add_setup(domain, setuper)


def platform_setup_factory(entity_domain: str, setuper_fn):
    """Generate async_setup_entry and async_setup_platform for a platform.

    Eliminates identical boilerplate across all 9 entity platform modules.
    """
    async def async_setup_entry(hass, config_entry, async_add_entities):
        await async_add_setuper(hass, config_entry, entity_domain, setuper_fn(async_add_entities))

    async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
        await async_add_setuper(hass, config or discovery_info, entity_domain, setuper_fn(async_add_entities))

    return async_setup_entry, async_setup_platform


async def get_gateway_from_config(hass, config, renew=False):
    if isinstance(config, ConfigEntry):
        cfg = {
            **config.data,
            **config.options,
            'hass': hass,
            'entry_id': config.entry_id,
            'config_entry': config,
        }
    else:
        cfg = {
            **config,
            'hass': hass,
            'entry_id': config.get(CONF_HOST),
        }
    if not (eid := cfg.get('entry_id')):
        _LOGGER.warning('Config invalid: %s', cfg)
        return None
    host = cfg.pop(CONF_HOST, None)
    if renew:
        return ProGateway(host, **cfg)
    gtw = hass.data[DOMAIN][CONF_GATEWAYS].get(eid)
    if not gtw:
        gtw = ProGateway(host, **cfg)
        hass.data[DOMAIN][CONF_GATEWAYS][eid] = gtw
    return gtw


async def async_reload_integration_config(hass, config):
    hass.data[DOMAIN]['config'] = config
    return config


class ComponentServices:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass

        async_register_admin_service(
            hass, DOMAIN, SERVICE_RELOAD, self.handle_reload_config,
        )

        hass.services.async_register(
            DOMAIN, 'send_command', self.async_send_command,
            schema=vol.Schema({
                vol.Required(CONF_HOST): cv.string,
                vol.Required('method'): cv.string,
                vol.Optional('params', default={}): dict,
                vol.Optional('result'): object,
                vol.Optional('throw', default=True): cv.boolean,
            }),
        )

        hass.services.async_register(
            DOMAIN, 'mock_incoming_message', self.async_mock_incoming_message,
            schema=vol.Schema({
                vol.Optional(CONF_HOST): cv.string,
                vol.Required('message'): cv.string,
            }),
        )

        hass.services.async_register(
            DOMAIN, 'remove_stale_devices', self.async_remove_stale_devices,
            schema=vol.Schema({
                vol.Optional(CONF_HOST): cv.string,
                vol.Optional('dry_run', default=False): cv.boolean,
            }),
        )


    async def handle_reload_config(self, call):
        config = await async_integration_yaml_config(self.hass, DOMAIN)
        if not config or DOMAIN not in config:
            return
        await async_reload_integration_config(self.hass, config.get(DOMAIN) or {})
        current_entries = self.hass.config_entries.async_entries(DOMAIN)
        reload_tasks = [
            self.hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]
        await asyncio.gather(*reload_tasks)
        await async_reload_integration_platforms(self.hass, DOMAIN, SUPPORTED_DOMAINS)

    async def async_send_command(self, call):
        dat = call.data
        gip = dat.get(CONF_HOST)

        gtw: ProGateway | None = None
        for g in self.hass.data[DOMAIN][CONF_GATEWAYS].values():
            # ✅ фикс: проверяем g, а не gtw
            if not isinstance(g, ProGateway):
                continue
            if not gip or g.host == gip:
                gtw = g
                break

        if not gtw:
            _LOGGER.warning("Gateway %s not found.", gip)
            return

        method = dat.get("method") or "gateway_post.event"
        params = dat.get("params") or {}
        rdt = dat.get("result")

        try:
            ret = await gtw.send(method, wait_result=True, params=params)
        except Exception as err:  # noqa: BLE001
            rdt = repr(err)
        else:
            if not rdt:
                rdt = ret

        if dat.get("throw", True):
            persistent_notification.async_create(
                self.hass,
                f"{rdt}",
                "Yeelight Pro command result",
                f"{DOMAIN}-debug",
            )

        self.hass.bus.async_fire(
            f"{DOMAIN}.send_command",
            {
                "host": gip,
                "method": method,
                "params": params,
                "result": rdt,
            },
        )
        return rdt

    async def async_mock_incoming_message(self, call):
        dat = call.data or {}
        gip = dat.get(CONF_HOST)
        gtw = None
        for g in self.hass.data[DOMAIN][CONF_GATEWAYS].values():
            if not isinstance(g, ProGateway):
                continue
            if g.host == gip or not gip:
                gtw = g
                break
        if not gtw:
            _LOGGER.warning('Gateway %s not found.', gip)
            return False
        message = dat['message']

        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError) as exc:
            title = 'Yeelight Pro mock incoming message'
            err_info = f'❌ Invalid JSON: {exc}\n\n'
            err_info += f'Input: {message}\n\n'
            err_info += '✅ Example: {"id": 8218, "method": "gateway_post.event", "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}\n'
            persistent_notification.async_create(
                self.hass, err_info, title=title, notification_id=f'{DOMAIN}-debug',
            )
            return False
                
        if not isinstance(msg, dict):
            title = 'Yeelight Pro mock incoming message'
            err_info = f'❌ Expected a JSON object, got {type(msg).__name__}\n\n'
            err_info += '✅ Example: {"id": 8218, "method": "gateway_post.event", "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}\n'
            persistent_notification.async_create(
                self.hass, err_info, title=title, notification_id=f'{DOMAIN}-debug',
            )
            return False
        message = json.dumps(msg)
        _LOGGER.info('Mock message: %s', message)
        await gtw.on_message(message.encode('utf-8'))

    async def async_remove_stale_devices(self, call):
        """Remove devices that are no longer in gateway topology."""
        dat = call.data or {}
        gip = dat.get(CONF_HOST)
        dry_run = dat.get('dry_run', False)
        
        removed_devices = []
        device_registry = dr.async_get(self.hass)
        
        for gtw in self.hass.data[DOMAIN][CONF_GATEWAYS].values():
            if not isinstance(gtw, ProGateway):
                continue
            if gip and gtw.host != gip:
                continue
            
            current_device_ids = set(gtw.devices.keys())
            gateway_identity_keys = {
                str(key)
                for key in (
                    getattr(getattr(gtw, "device", None), "id", None),
                    gtw.host,
                    gtw.entry_id,
                    _gateway_registry_key(gtw),
                )
                if key is not None
            }
            
            for device_entry in dr.async_entries_for_config_entry(
                device_registry, gtw.entry_id
            ):
                for identifier in device_entry.identifiers:
                    if identifier[0] != DOMAIN:
                        continue
                    device_uid = identifier[1]
                    device_id_part = device_uid
                    for prefix in (_gateway_registry_key(gtw), gtw.host, gtw.entry_id):
                        if prefix and device_uid.startswith(f"{prefix}-"):
                            device_id_part = device_uid[len(prefix) + 1:]
                            break
                    
                    try:
                        device_id = int(device_id_part)
                    except ValueError:
                        device_id = device_id_part
                    
                    if str(device_id) in gateway_identity_keys:
                        continue
                    
                    if device_id not in current_device_ids:
                        removed_devices.append({
                            'name': device_entry.name,
                            'id': device_id,
                            'device_id': device_entry.id,
                        })
                        if not dry_run:
                            device_registry.async_remove_device(device_entry.id)
        
        result_msg = f"{'Would remove' if dry_run else 'Removed'} {len(removed_devices)} stale device(s)"
        if removed_devices:
            device_list = "\n".join([f"- {d['name']} (ID: {d['id']})" for d in removed_devices])
            result_msg += f":\n{device_list}"
        
        persistent_notification.async_create(
            self.hass,
            result_msg,
            title="Yeelight Pro Stale Devices",
            notification_id=f"{DOMAIN}-stale-devices",
        )
        
        return {'removed': removed_devices, 'count': len(removed_devices)}
        
def _gateway_registry_key(gateway) -> str:
    """Return the stable registry identity for a gateway."""
    if gateway is None:
        return "gw"

    config_entry = getattr(gateway, "config_entry", None)
    unique_id = getattr(config_entry, "unique_id", None)
    if unique_id:
        return str(unique_id)

    if getattr(gateway, "host", None):
        return str(gateway.host)

    if getattr(gateway, "entry_id", None):
        return str(gateway.entry_id)

    return "gw"


def _device_registry_key(device, gateway_key: str) -> str:
    """Return the stable registry identity component for a device."""
    if isinstance(device, GatewayDevice):
        return gateway_key
    return str(device.id)


class XEntity(Entity):
    added = False
    _attr_should_poll = False

    def __init__(self, device: XDevice, conv: Converter, option=None):
        self.device = device
        self.hass = device.hass
        self._name = conv.attr
        self._option = option or {}
        self._attr_available = device.online if device.online is not None else True
        self._attr_name = f'{device.name} {conv.attr}'.strip()

        gateway = device.gateway
        gw_id = _gateway_registry_key(gateway)
        device_registry_key = _device_registry_key(device, gw_id)

        # Check if old unique_id exists in registry - if so, use it to avoid duplicates
        old_uid = f"{device.id}-{self._name}"
        new_uid = f"{gw_id}-{device_registry_key}-{self._name}"

        # Try to check registry for existing entity (may not be available in tests)
        existing_entity = None
        try:
            if hasattr(self.hass, 'data'):
                reg = er.async_get(self.hass)
                existing_entity = reg.async_get_entity_id(conv.domain, DOMAIN, old_uid)
        except (KeyError, AttributeError):
            pass

        # Use old unique_id if it exists in registry, otherwise use new format
        self._attr_unique_id = old_uid if existing_entity else new_uid

        self._attr_has_entity_name = True
        self._attr_icon = self._option.get('icon')
        self._attr_entity_picture = self._option.get('picture')
        self._attr_device_class = self._option.get('class') or conv.device_class
        self._attr_native_unit_of_measurement = conv.unit_of_measurement
        self._attr_entity_category = self._option.get('category')
        self._attr_translation_key = self._option.get('translation_key', conv.attr)

        via_device = None
        if not isinstance(device, (GatewayDevice, WifiPanelDevice)):
            parent_device = getattr(gateway, "device", None)
            parent_registry_key = _device_registry_key(parent_device, gw_id) if parent_device else gw_id
            via_device = (DOMAIN, f"{gw_id}-{parent_registry_key}")

        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{gw_id}-{device_registry_key}"),
            },
            name=device.name,
            model=device.pid or device.type or '',
            via_device=via_device,
            sw_version=device.firmware_version,
            manufacturer=DEFAULT_NAME,
        )
        self._attr_extra_state_attributes = {}
        self._vars = {}
        self._queued_for_add = False
        self.subscribed_attrs = device.subscribe_attrs(conv)
        device.entities[conv.attr] = self

        _LOGGER.debug('Entity created: %s uid=%s dev=%s', conv.domain, self._attr_unique_id, device.id)

    def queue_add(self, add_entities) -> None:
        """Queue entity addition exactly once until async_added_to_hass runs."""
        if self.added or self._queued_for_add:
            return
        self._queued_for_add = True
        add_entities([self])

    async def async_added_to_hass(self):
        if hasattr(self, 'async_get_last_state'):
            state = await self.async_get_last_state()
            if state:
                self.async_restore_last_state(state.state, state.attributes)

        self.added = True
        self._queued_for_add = False
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        self.added = False
        self._queued_for_add = False
        # HA base Entity defines async_will_remove_from_hass as a no-op coroutine;
        # calling super() is safe and forward-compatible.
        parent_method = getattr(super(), "async_will_remove_from_hass", None)
        if parent_method is not None:
            await parent_method()

    @callback
    def async_restore_last_state(self, state: str, attrs: dict):
        """Restore previous state."""
        self._attr_state = state

    @callback
    def async_set_state(self, data: dict):
        """Handle state update from gateway."""
        if self._name in data:
            self._attr_state = data[self._name]
        if 'available' in data:
            self._attr_available = data['available']
        for k in self.subscribed_attrs:
            if k in data:
                self._attr_extra_state_attributes[k] = data[k]

    async def device_send_props(self, value: dict):
        payload = self.device.encode(value)
        if not payload:
            _LOGGER.warning('%s: Empty payload after encoding %s', self.entity_id, value)
            return False
        return await self.device.set_prop(**payload)
