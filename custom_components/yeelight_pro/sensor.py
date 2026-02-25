"""Support for sensor."""
import logging
import asyncio

from homeassistant.core import callback
from homeassistant.components.sensor import (
    SensorEntity,
    DOMAIN as ENTITY_DOMAIN,
)
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.const import EntityCategory

from . import (
    XDevice,
    XEntity,
    Converter,
    async_add_setuper,
)
from .core.device import GatewayDevice

_LOGGER = logging.getLogger(__name__)


def setuper(add_entities):
    def setup(device: XDevice, conv: Converter):
        if not (entity := device.entities.get(conv.attr)):
            if conv.attr == 'action':
                entity = XActionEntity(device, conv)
            elif conv.attr == 'diagnostics' and isinstance(device, GatewayDevice):
                entity = XDiagnosticsSensor(device, conv)
            else:
                entity = XSensorEntity(device, conv)
        entity.queue_add(add_entities)
    return setup


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_add_setuper(hass, config_entry, ENTITY_DOMAIN, setuper(async_add_entities))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_add_setuper(hass, config or discovery_info, ENTITY_DOMAIN, setuper(async_add_entities))


class XSensorEntity(XEntity, SensorEntity, RestoreEntity):

    @callback
    def async_set_state(self, data: dict):
        super().async_set_state(data)
        self._attr_native_value = self._attr_state
        self._attr_extra_state_attributes['native_value'] = self._attr_state

    @callback
    def async_restore_last_state(self, state: str, attrs: dict):
        self._attr_native_value = attrs.get('native_value', state)
        for k, v in attrs.items():
            if k in self.subscribed_attrs or k == 'native_value':
                self._attr_extra_state_attributes[k] = v


class XActionEntity(XEntity, SensorEntity):
    _attr_native_value = ''
    clear_task: asyncio.Task = None

    @callback
    def async_set_state(self, data: dict):
        if self._name not in data or not self.hass:
            return
        if self.clear_task:
            self.clear_task.cancel()

        self._attr_native_value = data[self._name]
        self._attr_extra_state_attributes = data
        self.clear_task = self.hass.async_create_task(self.clear_state())
        _LOGGER.debug('%s: State changed: %s', self.entity_id, data)

    async def clear_state(self):
        await asyncio.sleep(0.3)
        self._attr_native_value = ''
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        if self.clear_task:
            self.clear_task.cancel()

        if self.native_value != '':
            self._attr_native_value = ''
            self.async_write_ha_state()

        await super().async_will_remove_from_hass()


class XDiagnosticsSensor(XEntity, SensorEntity):
    """Diagnostics sensor for gateway monitoring."""
    
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-box"
    _update_task: asyncio.Task = None
    
    def __init__(self, device: XDevice, conv: Converter, option=None):
        super().__init__(device, conv, option)
        self._attr_name = f"{device.name} Diagnostics"
        self._attr_native_value = "OK"
    
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Use asyncio.create_task (NOT hass.async_create_task) — hass.async_create_task
        # registers the task in hass._tasks which HA awaits during bootstrap. Since
        # _periodic_update is an infinite loop it would block startup for ~300 s.
        # Cleanup is handled manually in async_will_remove_from_hass.
        self._update_task = asyncio.create_task(self._periodic_update())
    
    async def async_will_remove_from_hass(self):
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        await super().async_will_remove_from_hass()
    
    async def _periodic_update(self):
        """Update diagnostics every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                self._update_diagnostics()
                self.async_write_ha_state()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.debug('Diagnostics update error: %s', exc)
    
    def _update_diagnostics(self):
        """Update diagnostics from gateway."""
        gateway = getattr(self.device, '_gateway_ref', None)
        if not gateway:
            self._attr_native_value = "No Gateway"
            return
        
        # Get diagnostics data
        diag = gateway.diagnostics
        
        # Set main value based on connection status
        if diag.get('connected'):
            success_rate = diag.get('success_rate', 100)
            if success_rate >= 95:
                self._attr_native_value = "OK"
            elif success_rate >= 80:
                self._attr_native_value = "Degraded"
            else:
                self._attr_native_value = "Poor"
        else:
            self._attr_native_value = "Disconnected"
        
        # Update extra attributes
        self._attr_extra_state_attributes = {
            'connected': diag.get('connected', False),
            'device_count': diag.get('device_count', 0),
            'uptime_seconds': diag.get('uptime_seconds', 0),
            'uptime_formatted': self._format_uptime(diag.get('uptime_seconds', 0)),
            'messages_sent': diag.get('messages_sent', 0),
            'messages_received': diag.get('messages_received', 0),
            'commands_success': diag.get('commands_success', 0),
            'commands_failed': diag.get('commands_failed', 0),
            'commands_retried': diag.get('commands_retried', 0),
            'success_rate': diag.get('success_rate', 100),
            'reconnect_count': diag.get('reconnect_count', 0),
            'keepalive_total': diag.get('keepalive_total', 0),
            'keepalive_success': diag.get('keepalive_success', 0),
            'keepalive_failed': diag.get('keepalive_failed', 0),
            'last_error': diag.get('last_error'),
            'transition_time': diag.get('transition_time', 5.0),
            'topology_cache_age': diag.get('topology_cache_age'),
        }
    
    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h"
    
    @callback
    def async_set_state(self, data: dict):
        """Handle state update - update diagnostics."""
        self._update_diagnostics()
