"""Support for light."""
import logging
import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import async_get_current_platform
from homeassistant.core import callback
from homeassistant.components.light import (
    LightEntity,
    DOMAIN as ENTITY_DOMAIN,
    ColorMode,
    LightEntityFeature,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
)

from . import (
    XDevice,
    XEntity,
    Converter,
    async_add_setuper,
)

_LOGGER = logging.getLogger(__name__)


def setuper(add_entities):
    def setup(device: XDevice, conv: Converter):
        if not (entity := device.entities.get(conv.attr)):
            entity = XLightEntity(device, conv)
        entity.queue_add(add_entities)
    return setup


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_add_setuper(hass, config_entry, ENTITY_DOMAIN, setuper(async_add_entities))
    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "prestage_color_temp",
        {
            vol.Required(ATTR_COLOR_TEMP_KELVIN): vol.Coerce(int),
            **cv.ENTITY_SERVICE_FIELDS,
        },
        "async_prestage_color_temp",
    )


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_add_setuper(hass, config or discovery_info, ENTITY_DOMAIN, setuper(async_add_entities))
    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "prestage_color_temp",
        {
            vol.Required(ATTR_COLOR_TEMP_KELVIN): vol.Coerce(int),
            **cv.ENTITY_SERVICE_FIELDS,
        },
        "async_prestage_color_temp",
    )


class XLightEntity(XEntity, LightEntity):
    _attr_is_on = None

    def __init__(self, device: XDevice, conv: Converter, option=None):
        super().__init__(device, conv, option)

        # Initialize flags first
        self._attr_supported_color_modes = set()
        self._attr_supported_features = LightEntityFeature(0)

        # Supported color modes
        if device.converters.get(ATTR_RGB_COLOR):
            self._attr_supported_color_modes.add(ColorMode.RGB)

        if cov := device.converters.get('color_temp'):
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
            if hasattr(cov, "minm") and hasattr(cov, "maxm"):
                self._attr_min_mireds = cov.minm
                self._attr_max_mireds = cov.maxm
            elif hasattr(cov, "mink") and hasattr(cov, "maxk"):
                self._attr_min_mireds = int(1_000_000 / cov.maxk)
                self._attr_max_mireds = int(1_000_000 / cov.mink)
                self._attr_min_color_temp_kelvin = cov.mink
                self._attr_max_color_temp_kelvin = cov.maxk

        if not self._attr_supported_color_modes:
            self._attr_supported_color_modes = (
                {ColorMode.BRIGHTNESS}
                if device.converters.get(ATTR_BRIGHTNESS)
                else {ColorMode.ONOFF}
            )

        if device.converters.get(ATTR_TRANSITION):
            self._attr_supported_features |= LightEntityFeature.TRANSITION

        # Initialize color_mode to prevent warnings
        if ColorMode.RGB in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.RGB
        elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_color_mode = ColorMode.ONOFF

    def _clamp_ct_kelvin(self, k: int) -> int:
        lo = getattr(self, "_attr_min_color_temp_kelvin", None)
        hi = getattr(self, "_attr_max_color_temp_kelvin", None)
        return max(lo, min(hi, k)) if lo and hi else k

    def _clamp_mired(self, m: int) -> int:
        lo = getattr(self, "_attr_min_mireds", None)
        hi = getattr(self, "_attr_max_mireds", None)
        return max(lo, min(hi, m)) if lo and hi else m

    @callback
    def async_set_state(self, data: dict):
        super().async_set_state(data)
        if self._name in data:
            self._attr_is_on = data[self._name]
        if ATTR_BRIGHTNESS in data:
            self._attr_brightness = data[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in data:
            self._attr_color_temp_kelvin = data[ATTR_COLOR_TEMP_KELVIN]
            self._attr_color_temp = int(1_000_000 / max(1, data[ATTR_COLOR_TEMP_KELVIN]))
            if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.COLOR_TEMP
        if ATTR_RGB_COLOR in data:
            self._attr_rgb_color = data[ATTR_RGB_COLOR]
            if ColorMode.RGB in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.RGB

        # Ensure color_mode is always set
        if not self._attr_color_mode:
            if ColorMode.RGB in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.RGB
            elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.COLOR_TEMP
            elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.BRIGHTNESS
            else:
                self._attr_color_mode = ColorMode.ONOFF

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        kwargs[self._name] = True
        if ATTR_RGB_COLOR in kwargs:
            self._attr_color_mode = ColorMode.RGB
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_mode = ColorMode.COLOR_TEMP
        elif not self._attr_color_mode:
            if ColorMode.RGB in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.RGB
            elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.COLOR_TEMP
            elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.BRIGHTNESS
            else:
                self._attr_color_mode = ColorMode.ONOFF

        return await self.async_turn(kwargs[self._name], **kwargs)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        return await self.async_turn(False, **kwargs)

    async def async_turn(self, on: bool = True, **kwargs):
        """Turn the entity on/off."""
        kwargs[self._name] = on
        ret = await self.device_send_props(kwargs)
        if ret:
            self._attr_is_on = on
            if self.added:
                self.async_write_ha_state()
        else:
            _LOGGER.warning('%s: Turn %s failed', self.entity_id, 'on' if on else 'off')
        return ret

    async def async_prestage_color_temp(self, **kwargs):
        """Set color temperature while the light is OFF (no power change)."""
        payload: dict = {}

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            k = self._clamp_ct_kelvin(int(kwargs[ATTR_COLOR_TEMP_KELVIN]))

            # Optimization: skip if color temp is already set and light is OFF
            if self._attr_is_on is False and self._attr_color_temp_kelvin == k:
                return True

            payload["color_temp"] = k
            self._attr_color_temp_kelvin = k
            self._attr_color_temp = int(1_000_000 / max(1, k))
            self._attr_color_mode = ColorMode.COLOR_TEMP

        if not payload:
            return False

        ret = await self.device_send_props(payload)
        if ret and self.added:
            self.async_write_ha_state()
        return ret

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
