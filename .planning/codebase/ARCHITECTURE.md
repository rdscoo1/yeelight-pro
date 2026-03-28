# Architecture

**Analysis Date:** 2026-03-29

## Pattern Overview

**Overall:** Home Assistant Custom Integration (Hub-style plugin architecture)

**Key Characteristics:**
- Local-push IoT integration communicating with Yeelight Pro gateways over raw TCP
- Event-driven architecture: gateway pushes state changes, integration reacts
- Converter pattern translates between gateway wire protocol and HA entity attributes
- Device factory pattern: `XDevice.from_node()` maps gateway node types to typed device subclasses
- Dual setup paths: YAML-based (`async_setup`) and UI config entry (`async_setup_entry`)

## Layers

**Integration Layer (HA Glue):**
- Purpose: Registers the integration with Home Assistant, manages lifecycle
- Location: `custom_components/yeelight_pro/__init__.py`
- Contains: `async_setup`, `async_setup_entry`, `async_unload_entry`, `get_gateway_from_config`, `XEntity` base class, `ComponentServices`
- Depends on: `core/gateway.py`, `core/device.py`, `core/const.py`
- Used by: Home Assistant core, all platform modules

**Platform Layer (Entity Implementations):**
- Purpose: Implements HA entity types (light, switch, sensor, etc.)
- Location: `custom_components/yeelight_pro/{light,switch,sensor,binary_sensor,cover,climate,button,number,update}.py`
- Contains: Entity classes inheriting from both `XEntity` and HA platform base classes (e.g., `XLightEntity(XEntity, LightEntity)`)
- Depends on: `__init__.py` (for `XEntity`, `XDevice`, `Converter`, `async_add_setuper`)
- Used by: Home Assistant entity platform system

**Core Layer (Protocol + Device Model):**
- Purpose: TCP communication with gateway, device modeling, data conversion
- Location: `custom_components/yeelight_pro/core/`
- Contains: `ProGateway` (TCP client), `XDevice` hierarchy (device models), `Converter` hierarchy (data translation)
- Depends on: Python stdlib (`asyncio`, `json`), HA constants for `ColorMode`/`HVACMode`
- Used by: Integration layer, Platform layer

## Data Flow

**Inbound (Gateway -> HA entities):**

1. `ProGateway._read_loop()` reads TCP bytes, splits on `\r\n` delimiter
2. `ProGateway.on_message()` parses JSON, dispatches by `method` field:
   - `gateway_post.topology` / `device_post.topology`: Creates devices via `XDevice.from_node()`, calls `gateway.add_device()`
   - `gateway_post.prop` / `device_post.prop`: Calls `device.prop_changed(node)` which decodes and pushes to entities
   - `gateway_post.event` / `device_post.event`: Calls `device.event_fired(node)` which decodes and fires HA events
3. `XDevice.decode()` iterates device converters, each converter extracts its attribute from the raw node dict
4. `XDevice.update()` calls `entity.async_set_state(decoded_data)` then `entity.async_write_ha_state()` for each affected entity

**Outbound (HA entities -> Gateway):**

1. Entity method called (e.g., `XLightEntity.async_turn_on()`)
2. Entity calls `self.device_send_props(kwargs)` (defined in `XEntity`)
3. `XEntity.device_send_props()` calls `device.encode(value)` to translate HA attrs to wire format
4. `XDevice.encode()` iterates converters; `PropConv` subclasses nest values under `set` key
5. `XDevice.set_prop()` builds node dict, calls `gateway.send(cmd, nodes=[node])`
6. `ProGateway.send()` routes: topology/internal queries go direct, other commands go through `_send_with_retry()`
7. `ProGateway._send_internal()` serializes to JSON + `\r\n`, writes to TCP stream, creates `asyncio.Future` for response

**State Management:**
- Device state stored in `XDevice.prop` dict (raw gateway values)
- Entity state stored in HA entity attributes (`_attr_*` pattern)
- Converters bridge the two: `decode()` maps prop -> HA attrs, `encode()` maps HA attrs -> prop
- `hass.data[DOMAIN][CONF_GATEWAYS]` stores gateway instances keyed by entry_id or host

## Key Abstractions

**ProGateway (`core/gateway.py`):**
- Purpose: Persistent TCP connection to a Yeelight Pro gateway device
- Pattern: Async connection with reconnect loop, keepalive, exponential backoff
- Key methods: `start()`, `stop()`, `send()`, `on_message()`, `topology()`
- Manages: `devices` dict, `setups` dict (domain -> entity setup callbacks), `_msgs` dict (pending command futures)
- Statistics tracked via `GatewayStatistics` dataclass

**XDevice hierarchy (`core/device.py`):**
- Purpose: Represents a physical or logical device on the mesh network
- Factory: `XDevice.from_node()` inspects `nt` (node type) and `type` (device type) to instantiate correct subclass
- Subclasses: `GatewayDevice`, `LightDevice`, `SwitchPanelDevice`, `RelayDoubleDevice`, `KnobDevice`, `MotionDevice`, `ContactDevice`, `CoverDevice`, `ClimateDevice`, `GroupDevice`, `WifiPanelDevice`
- Each subclass overrides `setup_converters()` to register appropriate converters
- Passive state verification: after `set_prop()`, schedules `_verify_state_later()` that waits for `gateway_post.prop` confirmation

**Converter hierarchy (`core/converters/base.py`):**
- Purpose: Bidirectional translation between gateway wire values and HA entity attributes
- Base: `Converter` dataclass with `attr`, `domain`, `prop`, `parent`, `device_class`, `unit_of_measurement`
- Key subclasses:
  - `PropConv`: Converter for values nested under `params` in gateway messages
  - `PropBoolConv(BoolConv, PropConv)`: Boolean property (on/off)
  - `PropMapConv(MapConv, PropConv)`: Enum mapping (e.g., HVAC modes)
  - `BrightnessConv`: Scales 0-100 gateway range to 0-255 HA range
  - `ColorTempKelvin`: Converts between Kelvin (gateway) and Mired (HA)
  - `ColorRgbConv`: Packs/unpacks RGB from single integer
  - `EventConv`: Decodes events (motion, button clicks, knob spins)
  - `DurationConv`: Converts milliseconds (gateway) to seconds (HA)
  - `MotorConv`: Encodes cover motor commands
  - `SceneConv`: Scene activation button

**XEntity (`__init__.py`):**
- Purpose: Base entity bridging `XDevice` + `Converter` to HA `Entity`
- Pattern: Multiple inheritance -- platform entities inherit from both `XEntity` and HA platform class
- Key responsibilities: unique_id generation (with legacy migration), device_info construction, state dispatch via `async_set_state()`, command encoding via `device_send_props()`
- Entity registration: `device.entities[conv.attr] = self` in constructor

## Entry Points

**async_setup (`__init__.py` line 63):**
- Triggers: YAML configuration loading
- Responsibilities: Creates gateways from YAML config, discovers platforms, starts gateways, registers `ComponentServices`

**async_setup_entry (`__init__.py` line 87):**
- Triggers: UI config entry created/loaded
- Responsibilities: Forwards platform setup, creates and starts gateway, registers cleanup handlers

**config_flow.py:**
- Triggers: User adds integration via UI
- Responsibilities: `YeelightProConfigFlow.async_step_user()` validates gateway connectivity, creates config entry
- Options: `OptionsFlowHandler` allows changing host, keepalive interval, transition time

**Platform async_setup_entry / async_setup_platform (each platform file):**
- Triggers: Called by HA during platform forwarding
- Responsibilities: Registers `setuper` callback with gateway via `async_add_setuper()`
- The `setuper` pattern: returns a closure that creates entity instances when devices are discovered

## Error Handling

**Strategy:** Resilient connection with automatic recovery

**Patterns:**
- **Exponential backoff reconnection**: `run_forever()` in `ProGateway` retries connections with delay growing from 1s to 60s (`MIN_RECONNECT_DELAY` to `MAX_RECONNECT_DELAY`)
- **Keepalive monitoring**: `_keepalive_loop()` sends periodic pings; 2 consecutive failures trigger reconnect
- **JSON error threshold**: After 5 consecutive JSON decode errors (`MAX_JSON_ERRORS`), forces reconnect
- **Command retry**: `_send_with_retry()` retries failed commands up to 3 times with exponential backoff (0.5s base)
- **Passive state verification**: After `set_prop()`, device waits 1.5s for `gateway_post.prop` confirmation; retries command up to 2 times on mismatch
- **Buffer overflow protection**: Read buffer limited to 1MB (`READ_BUFFER_LIMIT`)
- **Lock ordering**: `_send_lock` and `_connect_lock` carefully ordered to prevent deadlocks (comment at line 659 in gateway.py)
- **Topology cache**: 5-minute TTL to reduce redundant topology requests; invalidated on reconnect

## Cross-Cutting Concerns

**Logging:** Python `logging` module, logger per module (`_LOGGER = logging.getLogger(__name__)`). Gateway logs prefixed with `[host]` for multi-gateway disambiguation.

**Validation:** `voluptuous` schemas for config (`CONFIG_SCHEMA`, `GATEWAY_SCHEMA`) and service calls. Config flow validates gateway connectivity before accepting.

**Authentication:** None -- Yeelight Pro gateways use unauthenticated local TCP on port 65443.

**Diagnostics:** `diagnostics.py` implements HA diagnostics with host redaction. `GatewayStatistics` dataclass tracks uptime, message counts, success rates, reconnect counts. `XDiagnosticsSensor` exposes stats as HA sensor entity with 60s periodic updates.

**Services:** Three custom services registered in `ComponentServices`:
- `send_command`: Send arbitrary method+params to gateway
- `mock_incoming_message`: Inject fake gateway message for debugging
- `remove_stale_devices`: Clean up devices no longer in topology

**Internationalization:** Translation files at `translations/en.json` and `translations/zh-Hans.json`.

---

*Architecture analysis: 2026-03-29*
