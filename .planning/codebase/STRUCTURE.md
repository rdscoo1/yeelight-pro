# Codebase Structure

**Analysis Date:** 2026-03-29

## Directory Layout

```
yeelight-pro/
├── custom_components/
│   └── yeelight_pro/           # Main integration package
│       ├── core/               # Protocol, device model, converters
│       │   ├── __init__.py     # Empty
│       │   ├── const.py        # Domain constants, supported domains
│       │   ├── gateway.py      # ProGateway TCP client
│       │   ├── device.py       # XDevice hierarchy (all device types)
│       │   └── converters/
│       │       └── base.py     # Converter hierarchy (all converter types)
│       ├── translations/       # i18n files
│       │   ├── en.json
│       │   └── zh-Hans.json
│       ├── __init__.py         # Integration entry points, XEntity base, ComponentServices
│       ├── config_flow.py      # UI configuration flow + options flow
│       ├── manifest.json       # HA integration manifest (version, domain, etc.)
│       ├── services.yaml       # Service definitions for HA
│       ├── diagnostics.py      # HA diagnostics support
│       ├── light.py            # Light platform entities
│       ├── switch.py           # Switch platform entities
│       ├── sensor.py           # Sensor platform entities (action, diagnostics)
│       ├── binary_sensor.py    # Binary sensor platform entities (motion, contact, connection)
│       ├── cover.py            # Cover platform entities (curtains)
│       ├── climate.py          # Climate platform entities (AC/VRF)
│       ├── button.py           # Button platform entities (scenes)
│       ├── number.py           # Number platform entities (delay, angle)
│       └── update.py           # Firmware update entities
├── tests/                      # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures
│   ├── test_gateway.py
│   ├── test_device.py
│   ├── test_converters_base.py
│   ├── test_config_flow.py
│   ├── test_init_integration.py
│   ├── test_component_services.py
│   ├── test_integration_e2e.py
│   ├── test_light_entity.py
│   ├── test_switch_entity.py
│   ├── test_sensor_entity.py
│   ├── test_binary_sensor.py
│   ├── test_button.py
│   ├── test_cover_entity.py
│   ├── test_climate_entity.py
│   └── test_number_entity.py
├── .github/
│   └── workflows/
│       └── ci.yml              # CI pipeline
├── hacs.json                   # HACS repository metadata
├── requirements-dev.txt        # Dev dependencies (pytest, etc.)
├── CHANGELOG.md
├── README.md
├── README_RU.md
├── RELEASE_NOTES.md
├── test_api_interactive.py     # Manual/interactive test scripts (root level)
├── test_api_manual.py
├── test_gateway_interactive.py
├── test_gateway_manual.py
└── test_gateway_simple.py
```

## Directory Purposes

**`custom_components/yeelight_pro/`:**
- Purpose: The HA custom component package -- everything HA loads
- Contains: All integration source code
- Key files: `__init__.py` (entry points + base entity), `manifest.json` (integration metadata)

**`custom_components/yeelight_pro/core/`:**
- Purpose: Business logic independent of HA entity specifics
- Contains: Gateway TCP client, device models, data converters, constants
- Key files: `gateway.py` (829 lines, TCP client), `device.py` (752 lines, all device types), `converters/base.py` (217 lines, all converter types)

**`custom_components/yeelight_pro/core/converters/`:**
- Purpose: Data translation between gateway wire format and HA attributes
- Contains: Single `base.py` with all converter classes
- Note: Directory structure suggests future expansion but currently only has `base.py`

**`custom_components/yeelight_pro/translations/`:**
- Purpose: Localization strings for config flow UI
- Contains: English and Simplified Chinese translations

**`tests/`:**
- Purpose: Automated test suite
- Contains: Unit tests for each component, integration/E2E tests
- Key files: `conftest.py` (shared fixtures), `test_gateway.py`, `test_device.py`

## Key File Locations

**Entry Points:**
- `custom_components/yeelight_pro/__init__.py`: `async_setup()` (YAML), `async_setup_entry()` (UI config)
- `custom_components/yeelight_pro/config_flow.py`: `YeelightProConfigFlow` (UI setup wizard)

**Configuration:**
- `custom_components/yeelight_pro/manifest.json`: Integration metadata (version `1.3.2`, domain `yeelight_pro`, iot_class `local_push`)
- `custom_components/yeelight_pro/core/const.py`: All constants -- `DOMAIN`, `SUPPORTED_DOMAINS` list, PID values, keepalive/transition defaults
- `custom_components/yeelight_pro/services.yaml`: Service definitions (send_command, mock_incoming_message, remove_stale_devices)
- `hacs.json`: HACS store metadata

**Core Logic:**
- `custom_components/yeelight_pro/core/gateway.py`: `ProGateway` class -- TCP connection, reconnection, keepalive, message routing, topology management
- `custom_components/yeelight_pro/core/device.py`: `XDevice` base + all device subclasses, `from_node()` factory, encode/decode, passive state verification
- `custom_components/yeelight_pro/core/converters/base.py`: `Converter` base + all converter subclasses

**Platform Entities:**
- `custom_components/yeelight_pro/light.py`: `XLightEntity` -- most complex entity with color modes, transitions, prestage service
- `custom_components/yeelight_pro/climate.py`: `XClimateEntity` -- HVAC modes, fan modes, temperature control
- `custom_components/yeelight_pro/cover.py`: `XCoverEntity` -- position, open/close/stop
- `custom_components/yeelight_pro/sensor.py`: `XSensorEntity`, `XActionEntity` (auto-clearing), `XDiagnosticsSensor` (periodic gateway stats)
- `custom_components/yeelight_pro/switch.py`: `XSwitchEntity` -- simple on/off
- `custom_components/yeelight_pro/binary_sensor.py`: `XBinarySensorEntity`, `XGatewayConnectionEntity`
- `custom_components/yeelight_pro/button.py`: `XButtonEntity`, `XSceneEntity` -- scene activation
- `custom_components/yeelight_pro/number.py`: `XNumberEntity`, `DelayoffEntity` -- numeric controls
- `custom_components/yeelight_pro/update.py`: `XUpdateEntity`, `XGatewayUpdateEntity` -- firmware version tracking

**Testing:**
- `tests/conftest.py`: Shared test fixtures (mock gateway, mock devices, mock hass)
- `tests/test_gateway.py`: Gateway connection, reconnection, keepalive, message handling tests
- `tests/test_device.py`: Device creation, converter setup, state decode/encode tests
- `tests/test_integration_e2e.py`: End-to-end integration tests

## Naming Conventions

**Files:**
- Platform files: lowercase domain name matching HA platform (`light.py`, `switch.py`, `climate.py`)
- Test files: `test_` prefix + component name (`test_gateway.py`, `test_light_entity.py`)
- Core files: descriptive lowercase (`gateway.py`, `device.py`, `const.py`)

**Classes:**
- Entity classes: `X` prefix + HA entity type (`XLightEntity`, `XSwitchEntity`, `XClimateEntity`)
- Device classes: Descriptive name + `Device` suffix (`LightDevice`, `MotionDevice`, `CoverDevice`)
- Converter classes: Descriptive name + `Conv` suffix (`PropBoolConv`, `BrightnessConv`, `ColorTempKelvin`)
- Special entities: Descriptive prefix (`XGatewayConnectionEntity`, `XDiagnosticsSensor`, `DelayoffEntity`)

**Functions:**
- HA lifecycle: `async_setup_entry`, `async_setup_platform` (HA convention)
- Entity setup factory: `setuper(add_entities)` returns closure `setup(device, conv)` -- used in all platform files
- Helper: `async_add_setuper` -- registers setup callback with gateway

## Where to Add New Code

**New Device Type:**
1. Add `DeviceType` enum value in `custom_components/yeelight_pro/core/device.py`
2. Create new `XDevice` subclass in `custom_components/yeelight_pro/core/device.py` with `setup_converters()` override
3. Add type mapping in `XDevice.from_node()` factory method (same file, around line 148-169)
4. If new converter type needed, add to `custom_components/yeelight_pro/core/converters/base.py`
5. Tests in `tests/test_device.py`

**New HA Platform:**
1. Create `custom_components/yeelight_pro/{platform}.py` following the `setuper` pattern from existing platforms
2. Add domain string to `SUPPORTED_DOMAINS` in `custom_components/yeelight_pro/core/const.py`
3. Implement entity class as `class XNewEntity(XEntity, HAPlatformEntity)`
4. Tests in `tests/test_{platform}_entity.py`

**New Converter:**
- Add class to `custom_components/yeelight_pro/core/converters/base.py`
- Follow existing pattern: inherit from `Converter` or `PropConv`, implement `decode()` and `encode()`
- Tests in `tests/test_converters_base.py`

**New Service:**
- Add service handler method to `ComponentServices` class in `custom_components/yeelight_pro/__init__.py`
- Register in `ComponentServices.__init__()` with `hass.services.async_register()`
- Add service definition to `custom_components/yeelight_pro/services.yaml`

**New Gateway Feature:**
- Modify `custom_components/yeelight_pro/core/gateway.py`
- Tests in `tests/test_gateway.py`

## Special Directories

**`.planning/codebase/`:**
- Purpose: Architecture and analysis documentation (this file)
- Generated: Yes (by codebase mapper)
- Committed: Varies

**Root-level `test_*.py` files:**
- Purpose: Manual/interactive test scripts for direct gateway communication (not part of pytest suite)
- Files: `test_api_interactive.py`, `test_api_manual.py`, `test_gateway_interactive.py`, `test_gateway_manual.py`, `test_gateway_simple.py`
- Note: These are developer tools, not automated tests -- they connect to real hardware

**`.github/workflows/`:**
- Purpose: CI pipeline configuration
- Contains: `ci.yml`

## Module Organization

The codebase is organized **by layer** with platform files at the integration root:

- **Root** (`custom_components/yeelight_pro/`): HA integration glue + one file per HA platform domain
- **Core** (`core/`): Protocol and domain logic, isolated from HA entity specifics
- **Converters** (`core/converters/`): Data translation (currently single file, directory ready for expansion)

All platform files follow an identical structure:
1. `setuper()` factory function
2. `async_setup_entry()` for config entry setup
3. `async_setup_platform()` for YAML setup
4. Entity class(es) with `async_set_state()` and action methods

---

*Structure analysis: 2026-03-29*
