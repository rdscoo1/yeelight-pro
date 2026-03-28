# Coding Conventions

**Analysis Date:** 2026-03-29

## Naming Patterns

**Files:**
- Snake_case for all Python modules: `config_flow.py`, `binary_sensor.py`, `core/gateway.py`
- Test files prefixed with `test_`: `tests/test_gateway.py`, `tests/test_device.py`
- One HA platform entity per file: `light.py`, `switch.py`, `cover.py`, `climate.py`, `sensor.py`, `number.py`, `button.py`, `binary_sensor.py`, `update.py`

**Classes:**
- PascalCase with prefix patterns:
  - Entity classes: `X` prefix + entity type: `XEntity`, `XLightEntity`, `XSwitchEntity`, `XBinarySensorEntity`, `XClimateEntity`, `XCoverEntity`, `XSensorEntity`, `XActionEntity`, `XSceneEntity`, `XButtonEntity`
  - Device classes: descriptive PascalCase: `XDevice`, `LightDevice`, `MotionDevice`, `CoverDevice`, `ClimateDevice`, `GroupDevice`, `GatewayDevice`, `WifiPanelDevice`
  - Converter classes: suffix `Conv`: `Converter`, `PropConv`, `PropBoolConv`, `BoolConv`, `MapConv`, `PropMapConv`, `BrightnessConv`, `ColorTempKelvin`, `ColorRgbConv`, `EventConv`, `MotorConv`, `SceneConv`, `DurationConv`
  - Gateway: `ProGateway`
  - Enums: `NodeType`, `DeviceType` (both `IntEnum`)

**Functions/Methods:**
- Snake_case throughout
- HA lifecycle async methods: `async_setup`, `async_setup_entry`, `async_unload_entry`, `async_added_to_hass`, `async_will_remove_from_hass`
- Entity action methods: `async_turn_on`, `async_turn_off`, `async_set_state`, `async_set_temperature`, `async_press`
- Internal/private methods: single underscore prefix: `_read_loop`, `_send_internal`, `_close_connection`, `_keepalive_loop`, `_verify_state_later`
- Factory pattern for entity setup: `setuper(add_entities)` returns a `setup(device, conv)` closure (see `custom_components/yeelight_pro/light.py:29`)

**Variables:**
- Snake_case for local variables and instance attributes
- Constants: UPPER_SNAKE_CASE in `custom_components/yeelight_pro/core/const.py` and at module level
- Private instance attrs: single underscore prefix: `self._msgs`, `self._stopping`, `self._reconnect_delay`
- HA attribute pattern: `self._attr_*` (following HA entity conventions): `self._attr_is_on`, `self._attr_brightness`, `self._attr_unique_id`

**Constants:**
- Domain and config constants in `custom_components/yeelight_pro/core/const.py`: `DOMAIN`, `DEFAULT_NAME`, `CONF_GATEWAYS`, `SUPPORTED_DOMAINS`
- Protocol/timing constants at module level in relevant files: `MSG_SPLIT`, `MIN_RECONNECT_DELAY`, `MAX_RECONNECT_DELAY`, `KEEPALIVE_INTERVAL` in `core/gateway.py`
- Device type enums in `custom_components/yeelight_pro/core/device.py`: `DeviceType.LIGHT`, `NodeType.MESH`, etc.

## Code Style

**Formatting:**
- Ruff (v0.1.0+) is the linter/formatter, cache present at `.ruff_cache/0.14.4/`
- No explicit ruff config file found (uses defaults)
- 4-space indentation (Python standard)
- Single quotes for strings in most places, but inconsistent (both `'string'` and `"string"` used)
- Line length appears to follow ruff defaults (~88 chars) but some lines exceed this

**Linting:**
- Ruff (specified in `requirements-dev.txt`)
- `noqa: BLE001` used for broad exception catches (see `custom_components/yeelight_pro/__init__.py:235`)
- No explicit ruff configuration file; relies on defaults

## Import Organization

**Order:**
1. `from __future__ import annotations` (when used, e.g., `core/gateway.py`)
2. Standard library: `asyncio`, `json`, `logging`, `time`, `random`, `ast`
3. Third-party: `voluptuous as vol`
4. Home Assistant core: `from homeassistant.core import HomeAssistant, callback`
5. Home Assistant helpers: `from homeassistant.helpers import ...`
6. Home Assistant components: `from homeassistant.components.light import ...`
7. Local relative imports: `from .core.const import ...`, `from . import XDevice, XEntity`

**Path Style:**
- Relative imports within the component: `from .core.gateway import ProGateway`, `from . import XEntity`
- Absolute imports from HA: `from homeassistant.core import HomeAssistant`
- `TYPE_CHECKING` guards used in `core/gateway.py` and `core/device.py` for circular import prevention

**Pattern:**
```python
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.light import LightEntity, ColorMode

from . import XDevice, XEntity, Converter, async_add_setuper
from .core.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
```

## Error Handling

**Patterns:**
- Broad exception catching with logging for non-critical paths:
  ```python
  except Exception as exc:
      self.log.error('[%s] Unexpected connection error: %s', self.host, exc, exc_info=exc)
  ```
- Specific exception types for network operations: `ConnectionError`, `BrokenPipeError`, `OSError`
- `asyncio.CancelledError` explicitly re-raised in read loops (see `core/gateway.py:492-493`)
- Graceful degradation: operations return `None` on failure rather than raising
- Try/except around JSON parsing with fallback to `ast.literal_eval` (see `__init__.py:278-280`)
- Encoder/decoder methods use try/except to handle invalid values, defaulting to 0 (see `core/converters/base.py:95-97`)

**Gateway error recovery:**
- Exponential backoff for reconnection (`MIN_RECONNECT_DELAY` to `MAX_RECONNECT_DELAY`)
- JSON error counter triggers reconnect after `MAX_JSON_ERRORS` consecutive failures
- Keepalive failure threshold triggers reconnect after `KEEPALIVE_FAILURE_THRESHOLD` consecutive failures
- Command retry with exponential backoff via `_send_with_retry()` in `core/gateway.py:421`

## Logging

**Framework:** Python `logging` module

**Logger initialization:**
```python
_LOGGER = logging.getLogger(__name__)
```
Used in every module. Gateway also supports injectable logger via `options.get('logger', _LOGGER)`.

**Level usage:**
- `debug`: Normal operations, message flow, entity creation, keepalive success
- `info`: Gateway start/stop, reconnection, state reconciliation
- `warning`: Connection issues, missing handlers, state mismatches, device disappearance, command failures
- `error`: Connection errors, JSON decode failures, send errors, unexpected exceptions

**Format pattern:**
- Gateway messages include host prefix: `'[%s] Message text', self.host`
- Device messages include device ID: `'[%s] State verified', self.id`
- Uses `%s` string formatting (not f-strings) for lazy evaluation in logging calls
- `exc_info=exc` passed for unexpected errors to include traceback

**Examples from `core/gateway.py`:**
```python
self.log.debug('[%s] Gateway initialized, pid=%s', self.host, self.pid)
self.log.info('[%s] Connected successfully', self.host)
self.log.warning('[%s] Keepalive failed (%d consecutive, %d/%d total)', self.host, failures, ...)
self.log.error('[%s] JSON decode error (%d/%d): %s; raw=%r', self.host, count, max, exc, msg[:200])
```

## Comments

**When to Comment:**
- Docstrings on public methods and classes, but not consistently on all methods
- Inline comments for non-obvious logic, especially protocol details
- Chinese comments present in some places (original developer's language): `# 兼容python字典打印复制` in `__init__.py:276`
- Russian comments in test files (bilingual codebase): `"""Простейший заглушечный hass"""` in `tests/test_gateway.py`
- `# NYI` marker for not-yet-implemented features (see `core/device.py:721`)

**Docstring style:**
```python
async def stop(self, *args: Any) -> None:
    """Stop the gateway connection and cleanup. Idempotent -- safe to call multiple times."""
```

**No JSDoc/TSDoc** (Python project)

## Function Design

**Size:** Most methods are under 30 lines. Larger methods exist in gateway (`_send_internal` ~80 lines, `on_message` ~80 lines)

**Parameters:**
- `**kwargs` used extensively for flexible parameter passing in entity turn_on/turn_off methods
- `**options: Any` in `ProGateway.__init__` for configuration
- Type hints used in core modules (`core/gateway.py`, `core/device.py`) but not consistently in entity modules

**Return Values:**
- `Optional[Dict]` for gateway send operations (None on failure)
- `bool` for setup/unload operations
- Entities return result of `device_send_props()` from action methods

## Module Design

**Exports:**
- `__init__.py` serves as both integration entry point and base entity definition (`XEntity`)
- `core/__init__.py` is empty (package marker only)
- No `__all__` definitions

**Barrel Files:**
- `custom_components/yeelight_pro/__init__.py` exports `XEntity`, `XDevice`, `Converter`, `async_add_setuper` implicitly via imports
- Entity modules import from `__init__.py`: `from . import XDevice, XEntity, Converter, async_add_setuper`

## Configuration Patterns

**Voluptuous schemas** for:
- Config entry validation: `GATEWAY_SCHEMA`, `CONFIG_SCHEMA` in `__init__.py`
- Service schemas: inline in `ComponentServices.__init__`
- Config flow schemas: `get_flow_schema()`, `get_options_schema()` in `config_flow.py`

**Constants pattern:** All config keys defined in `core/const.py` with defaults and min/max ranges:
```python
DEFAULT_KEEPALIVE = 30
MIN_KEEPALIVE = 10
MAX_KEEPALIVE = 300
```

## Dataclass Usage

- `@dataclass` used for converters (`Converter`, `MapConv`, `DurationConv`, `BrightnessConv`, etc.) in `core/converters/base.py`
- `@dataclass` used for `GatewayStatistics` in `core/gateway.py`
- Note: `Converter` uses `childs = None` without type annotation to avoid dataclass field ordering issues

## Async Patterns

- All gateway I/O operations are async
- `asyncio.Lock` used for connection (`_connect_lock`) and send (`_send_lock`) serialization
- Background tasks tracked via `_background_tasks: Set[asyncio.Task]` with done callbacks for cleanup
- `hass.async_create_task()` preferred when hass is available, fallback to `asyncio.create_task()`
- Entity state updates use `@callback` decorator (synchronous HA callback pattern)

---

*Convention analysis: 2026-03-29*
