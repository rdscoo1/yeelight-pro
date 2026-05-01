"""Support for button."""
import logging

from homeassistant.components.button import (
    ButtonEntity,
    DOMAIN as ENTITY_DOMAIN,
)

from . import (
    XDevice,
    XEntity,
    Converter,
    platform_setup_factory,
)
from .core.converters.base import SceneConv

_LOGGER = logging.getLogger(__name__)


def setuper(add_entities):
    def setup(device: XDevice, conv: Converter):
        if not (entity := device.entities.get(conv.attr)):
            if isinstance(conv, SceneConv):
                entity = XSceneEntity(device, conv)
            else:
                entity = XButtonEntity(device, conv)
        entity.queue_add(add_entities)
    return setup


async_setup_entry, async_setup_platform = platform_setup_factory(ENTITY_DOMAIN, setuper)


class XButtonEntity(XEntity, ButtonEntity):
    _attr_state = None


class XSceneEntity(XButtonEntity):
    def __init__(self, device: XDevice, conv: SceneConv, option=None):
        super().__init__(device, conv, option)
        self._attr_id = conv.node.get('id')
        self._attr_name = conv.node.get('n') or conv.attr

    async def async_press(self):
        """Press the button."""
        # Route through the device so retry/stats machinery applies, instead of
        # bypassing it with a direct gateway.send.
        activator = getattr(self.device, 'activate_scene', None)
        if activator is None:
            # Fallback for non-GatewayDevice owners (shouldn't happen today).
            await self.device.gateway.send('gateway_set.prop', scenes=[{'id': self._attr_id}])
            return
        await activator(self._attr_id)
