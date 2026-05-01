"""Support for cover."""
import logging
from homeassistant.core import callback
from homeassistant.components.cover import (
    CoverEntity,
    DOMAIN as ENTITY_DOMAIN,
    ATTR_POSITION,
    ATTR_CURRENT_POSITION,
)
from homeassistant.helpers.restore_state import RestoreEntity
from . import (
    XDevice,
    XEntity,
    Converter,
    platform_setup_factory,
)

_LOGGER = logging.getLogger(__name__)


def setuper(add_entities):
    def setup(device: XDevice, conv: Converter):
        if not (entity := device.entities.get(conv.attr)):
            entity = XCoverEntity(device, conv)
        entity.queue_add(add_entities)

    return setup


async_setup_entry, async_setup_platform = platform_setup_factory(ENTITY_DOMAIN, setuper)


class XCoverEntity(XEntity, CoverEntity, RestoreEntity):
    _attr_is_closed = None

    @callback
    def async_set_state(self, data: dict):
        # Map device run_state to cover open/close state
        if 'run_state' in data:
            run_state = data['run_state']
            self._attr_is_opening = run_state == "opening"
            self._attr_is_closing = run_state == "closing"
            self._attr_state = run_state

        # Handle cover position
        if ATTR_POSITION in data:
            self._attr_current_cover_position = data[ATTR_POSITION]
            self._attr_is_closed = self._attr_current_cover_position <= 3

    @callback
    def async_restore_last_state(self, state: str, attrs: dict):
        # Restore state from last known values
        if state:
            self.async_set_state({'run_state': state})
        if ATTR_CURRENT_POSITION in attrs:
            self.async_set_state({ATTR_POSITION: attrs[ATTR_CURRENT_POSITION]})

    async def async_open_cover(self, **kwargs):
        # Open: drive to 100% via position channel
        await self.device_send_props({ATTR_POSITION: 100})

    async def async_close_cover(self, **kwargs):
        # Close: drive to 0% via position channel
        await self.device_send_props({ATTR_POSITION: 0})

    async def async_stop_cover(self, **kwargs):
        # Stop: send the motor pause command
        await self.device_send_props({self._name: 'pause'})

    async def async_set_cover_position(self, **kwargs):
        # Forward only ATTR_POSITION - never leak unrelated HA kwargs to the gateway.
        if ATTR_POSITION not in kwargs:
            return
        await self.device_send_props({ATTR_POSITION: kwargs[ATTR_POSITION]})
