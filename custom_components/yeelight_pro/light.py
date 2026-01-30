"""Support for light."""
import logging
import asyncio
import time
import json
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
        if not entity.added:
            add_entities([entity])
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
    target_task: asyncio.Task = None

    def __init__(self, device: XDevice, conv: Converter, option=None):
        super().__init__(device, conv, option)
        
        _LOGGER.debug('Initializing light entity: device=%s, converter=%s', device.id, conv.attr)

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
        
        _LOGGER.debug('Light entity initialized: supported_modes=%s, color_mode=%s, features=%s', 
                     list(self._attr_supported_color_modes), self._attr_color_mode, self._attr_supported_features)

        self._target_attrs = {}

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
        _LOGGER.debug('%s: async_set_state called with data: %s', self.entity_id, json.dumps(data, ensure_ascii=False, default=str))
        
        if self.target_task:
            _LOGGER.debug('%s: Cancelling previous target_task', self.entity_id)
            self.target_task.cancel()

        diff = time.time() - self._target_attrs.get("time", 0)
        # Use gateway's configurable transition time, fallback to 5 seconds
        default_transition = getattr(self.device.gateway, 'transition_time', 5.0) if self.device.gateway else 5.0
        delay = float(self._target_attrs.get(ATTR_TRANSITION) or default_transition)
        
        _LOGGER.debug('%s: Transition check: diff=%.2fs, delay=%.2fs, target_attrs=%s', 
                     self.entity_id, diff, delay, json.dumps(self._target_attrs, ensure_ascii=False, default=str))

        async def _apply_state_later():
            _LOGGER.debug('%s: _apply_state_later started, waiting %.2fs', self.entity_id, max(0, delay - diff) + 0.01)
            await asyncio.sleep(max(0, delay - diff) + 0.01)
            _LOGGER.debug('%s: _apply_state_later finished waiting', self.entity_id)
            # Do nothing - the state should already be updated by gateway messages
            # Clearing _target_attrs here causes issues with subsequent updates

        if diff < delay and self._target_attrs:
            watched = {
                self._name,
                ATTR_BRIGHTNESS,
                ATTR_COLOR_TEMP_KELVIN,
                ATTR_RGB_COLOR,
            }
            pending = {
                k: v for k, v in self._target_attrs.items() if k in watched
            }
            _LOGGER.debug('%s: Pending attrs before match: %s', self.entity_id, json.dumps(pending, ensure_ascii=False, default=str))
            for k in list(pending):
                if data.get(k) == pending[k]:
                    _LOGGER.debug('%s: Matched pending attr %s=%s, removing from pending', self.entity_id, k, pending[k])
                    self._target_attrs.pop(k, None)
                    pending.pop(k, None)
            if pending:
                _LOGGER.debug('%s: IGNORING state update during transition, pending=%s, incoming_data=%s', 
                             self.entity_id, json.dumps(pending, ensure_ascii=False, default=str),
                             json.dumps(data, ensure_ascii=False, default=str))
                self.target_task = asyncio.create_task(_apply_state_later())
                return

        _LOGGER.debug('%s: APPLYING state update: %s', self.entity_id, json.dumps(data, ensure_ascii=False, default=str))
        super().async_set_state(data)
        if self._name in data:
            self._attr_is_on = data[self._name]
        if ATTR_BRIGHTNESS in data:
            self._attr_brightness = data[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in data:
            self._attr_color_temp_kelvin = data[ATTR_COLOR_TEMP_KELVIN]
            # Also update mired for backward compatibility
            self._attr_color_temp = int(1_000_000 / max(1, data[ATTR_COLOR_TEMP_KELVIN]))
            # Update color mode when color temp changes
            if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.COLOR_TEMP
        if ATTR_RGB_COLOR in data:
            self._attr_rgb_color = data[ATTR_RGB_COLOR]
            # Update color mode when RGB changes
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
        _LOGGER.debug('%s: Turn on called with: %s', self.entity_id, json.dumps(kwargs, ensure_ascii=False, default=str))
        
        kwargs[self._name] = True
        self._target_attrs = {
            **kwargs,
            "time": time.time(),
        }
        if ATTR_RGB_COLOR in kwargs:
            self._attr_color_mode = ColorMode.RGB
            _LOGGER.debug('%s: Color mode set to RGB: %s', self.entity_id, kwargs[ATTR_RGB_COLOR])
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            _LOGGER.debug('%s: Color mode set to COLOR_TEMP: %s K', self.entity_id, kwargs[ATTR_COLOR_TEMP_KELVIN])
        elif not self._attr_color_mode:
            # Set default color mode based on supported modes
            if ColorMode.RGB in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.RGB
            elif ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.COLOR_TEMP
            elif ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
                self._attr_color_mode = ColorMode.BRIGHTNESS
            else:
                self._attr_color_mode = ColorMode.ONOFF
            _LOGGER.debug('%s: Color mode set to default: %s', self.entity_id, self._attr_color_mode)
        
        return await self.async_turn(kwargs[self._name], **kwargs)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        _LOGGER.debug('%s: Turn off called with: %s', self.entity_id, json.dumps(kwargs, ensure_ascii=False, default=str))
        return await self.async_turn(False, **kwargs)

    async def async_turn(self, on: bool = True, **kwargs):
        """Turn the entity on/off."""
        _LOGGER.debug('%s: Turning %s with kwargs: %s', self.entity_id, 'on' if on else 'off', 
                     json.dumps(kwargs, ensure_ascii=False, default=str))
        kwargs[self._name] = on
        ret = await self.device_send_props(kwargs)
        if ret:
            self._attr_is_on = on
            _LOGGER.debug('%s: Turn %s successful, writing state', self.entity_id, 'on' if on else 'off')
            self.async_write_ha_state()
        else:
            _LOGGER.warning('%s: Turn %s failed', self.entity_id, 'on' if on else 'off')
        return ret

    async def async_prestage_color_temp(self, **kwargs):
        """
        Set color temperature while the light is OFF (no power change).

        Accepts ATTR_COLOR_TEMP_KELVIN.
        """
        _LOGGER.debug('%s: Prestage color temp called with: %s', self.entity_id, 
                     json.dumps(kwargs, ensure_ascii=False, default=str))
        payload: dict = {}

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            k = self._clamp_ct_kelvin(int(kwargs[ATTR_COLOR_TEMP_KELVIN]))
            payload["color_temp"] = k
            self._attr_color_temp_kelvin = k
            self._attr_color_temp = int(1_000_000 / max(1, k))
            self._attr_color_mode = ColorMode.COLOR_TEMP
            _LOGGER.debug('%s: Prestage color temp: %s K (clamped from %s)', 
                         self.entity_id, k, kwargs[ATTR_COLOR_TEMP_KELVIN])

        if not payload:
            _LOGGER.warning('%s: Prestage color temp: no payload generated', self.entity_id)
            return False

        # send props directly; do NOT include power flag
        ret = await self.device_send_props(payload)
        if ret:
            _LOGGER.debug('%s: Prestage color temp successful', self.entity_id)
            self.async_write_ha_state()
        else:
            _LOGGER.warning('%s: Prestage color temp failed', self.entity_id)
        return ret

    async def async_will_remove_from_hass(self):
        if self.target_task:
            self.target_task.cancel()
        await super().async_will_remove_from_hass()
