"""Support for climate."""
import logging

from homeassistant.core import callback
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    DOMAIN as ENTITY_DOMAIN,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
)
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import UnitOfTemperature
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
            entity = XClimateEntity(device, conv)
        entity.queue_add(add_entities)
    return setup


async_setup_entry, async_setup_platform = platform_setup_factory(ENTITY_DOMAIN, setuper)


class XClimateEntity(XEntity, ClimateEntity, RestoreEntity):
    def __init__(self, device: XDevice, conv: Converter, option=None):
        super().__init__(device, conv, option)
        self.mode = None
        self.is_on = False

        # https://developers.home-assistant.io/docs/core/entity/climate#supported-features
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ]
        self._attr_fan_modes = [
            FAN_LOW,
            FAN_MEDIUM,
            FAN_HIGH,
        ]

        self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features |= ClimateEntityFeature.TURN_ON
        self._attr_supported_features |= ClimateEntityFeature.TURN_OFF

        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = None
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 1

    @callback
    def async_set_state(self, data: dict):
        super().async_set_state(data)
        if 'is_on' in data:
            self.is_on = data['is_on']
        if 'mode' in data:
            self.mode = data['mode']
        if 'fan_mode' in data:
            self._attr_fan_mode = data['fan_mode']
        if 'current_temperature' in data:
            self._attr_current_temperature = data['current_temperature']
        if 'target_temperature' in data:
            self._attr_target_temperature = data['target_temperature']
        self._attr_hvac_mode = self.mode if self.is_on else HVACMode.OFF

    @callback
    def async_restore_last_state(self, state: str, attrs: dict):
        pass

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        t = kwargs.get("temperature")
        if t is None:
            return
        await self.device_send_props({"target_temperature": t})

    async def async_set_hvac_mode(self, hvac_mode, **kwargs):
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self.device_send_props({"is_on": False})
        else:
            await self.device_send_props({"is_on": True, "mode": hvac_mode})
    
    async def async_set_fan_mode(self, fan_mode, **kwargs):
        """Set new target fan mode."""
        await self.device_send_props({'fan_mode': fan_mode})

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await self.device_send_props({'is_on': True})

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.device_send_props({'is_on': False})
