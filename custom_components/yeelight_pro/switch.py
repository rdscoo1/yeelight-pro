"""Support for switch."""
import logging

from homeassistant.core import callback
from homeassistant.components.switch import (
    SwitchEntity,
    DOMAIN as ENTITY_DOMAIN,
)

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
            entity = XSwitchEntity(device, conv)
        entity.queue_add(add_entities)
    return setup


async_setup_entry, async_setup_platform = platform_setup_factory(ENTITY_DOMAIN, setuper)


class XSwitchEntity(XEntity, SwitchEntity):
    _attr_is_on = None

    @callback
    def async_set_state(self, data: dict):
        super().async_set_state(data)

        if self._name in data:
            self._attr_is_on = data[self._name]

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        return await self.async_turn(True, **kwargs)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        return await self.async_turn(False, **kwargs)

    async def async_turn(self, on=True, **kwargs):
        """Turn the entity on/off."""
        kwargs[self._name] = on
        ret = await self.device_send_props(kwargs)
        if ret:
            self._attr_is_on = on
            if self.added:
                self.async_write_ha_state()
        return ret
