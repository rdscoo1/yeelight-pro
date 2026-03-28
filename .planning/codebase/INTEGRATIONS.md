# External Integrations

**Analysis Date:** 2026-03-29

## APIs & External Services

**Yeelight Pro Gateway (Local TCP):**
- The sole external integration. Communicates with Yeelight Pro Gateway hardware over local TCP.
- SDK/Client: Custom `ProGateway` class in `custom_components/yeelight_pro/core/gateway.py`
- Protocol: JSON over TCP with `\r\n` message delimiter on port 65443
- Auth: None (unauthenticated local network connection)
- Connection: Persistent TCP with automatic reconnection and exponential backoff

**Gateway Protocol Methods (defined in `custom_components/yeelight_pro/core/gateway.py`):**

| Method | Direction | Purpose |
|--------|-----------|---------|
| `gateway_get.topology` | Request | Fetch device topology (all connected devices) |
| `gateway_post.topology` | Push | Gateway pushes topology updates |
| `gateway_set.prop` | Request | Set device properties (turn on/off, brightness, etc.) |
| `gateway_post.prop` | Push | Gateway pushes property changes |
| `gateway_post.event` | Push | Gateway pushes device events (motion, button press) |
| `gateway_get.node` | Request | Get single node info / keepalive ping |
| `gateway_get.room` | Request | Get room information |
| `gateway_get.scene` | Request | Get scenes list |
| `device_get.*` / `device_set.*` / `device_post.*` | Mixed | Wifi Panel variants of above methods |

**No Cloud Services:**
- This integration is entirely local (`iot_class: local_push` in `manifest.json`)
- No cloud APIs, no internet dependency, no OAuth flows

## Data Storage

**Databases:**
- None. All state is managed by Home Assistant's built-in state machine.

**File Storage:**
- Local filesystem only (Home Assistant default storage)
- No custom file I/O

**Caching:**
- In-memory topology cache with 5-minute TTL in `ProGateway` (`custom_components/yeelight_pro/core/gateway.py`, line ~36: `TOPOLOGY_CACHE_TTL = 300`)
- Cache invalidated on reconnect via `invalidate_topology_cache()`

## Authentication & Identity

**Auth Provider:**
- None. Gateway communication is unauthenticated over local TCP.
- Config flow validates connectivity by attempting TCP connection (`check_available()` in `custom_components/yeelight_pro/core/gateway.py`)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or similar)

**Diagnostics:**
- Built-in HA diagnostics support in `custom_components/yeelight_pro/diagnostics.py`
- Exposes gateway statistics: uptime, message counts, success rate, reconnect count, keepalive stats
- `GatewayStatistics` dataclass in `custom_components/yeelight_pro/core/gateway.py` tracks:
  - Messages sent/received
  - Command success/failure/retry counts
  - Keepalive health
  - State mismatch corrections
  - Last error details
- Host IP is redacted in diagnostics output (`TO_REDACT` in `diagnostics.py`)

**Logs:**
- Python `logging` module throughout (logger name: `custom_components.yeelight_pro`)
- Loggers declared in `manifest.json`: `custom_components.yeelight_pro`, `custom_components.yeelight_pro.core`
- Structured log format with gateway host prefix: `[{host}] message`

**Persistent Notifications:**
- Reconnect events create HA persistent notifications (`_send_reconnect_notification` in `gateway.py`)
- Command results shown via persistent notifications (`async_send_command` in `__init__.py`)
- Stale device removal results shown via persistent notifications

## CI/CD & Deployment

**Hosting:**
- Distributed via HACS (Home Assistant Community Store)
- `hacs.json` configuration present at project root

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`)
- Two jobs:
  1. `validate` - HACS validation + Hassfest validation
  2. `test` - pytest on Python 3.11 and 3.12 with coverage upload to Codecov
- Triggers: push to main/master/feature/*, PRs to main/master, manual dispatch

## Home Assistant Integration Points

**Supported HA Platforms:**
Defined in `custom_components/yeelight_pro/core/const.py` (`SUPPORTED_DOMAINS`):

| Platform | File | Entity Types |
|----------|------|-------------|
| `light` | `custom_components/yeelight_pro/light.py` | Lights with brightness, color temp, RGB |
| `switch` | `custom_components/yeelight_pro/switch.py` | Relay switches, panel switches |
| `binary_sensor` | `custom_components/yeelight_pro/binary_sensor.py` | Motion, contact, gateway connectivity |
| `sensor` | `custom_components/yeelight_pro/sensor.py` | Action sensors, diagnostics, illuminance |
| `cover` | `custom_components/yeelight_pro/cover.py` | Curtain/motor control |
| `climate` | `custom_components/yeelight_pro/climate.py` | Air conditioner control |
| `button` | `custom_components/yeelight_pro/button.py` | Scene activation buttons |
| `number` | `custom_components/yeelight_pro/number.py` | Delay-off timer, zoom angle |
| `update` | `custom_components/yeelight_pro/update.py` | Firmware update entities |

**Custom HA Services:**
Defined in `custom_components/yeelight_pro/services.yaml` and registered in `__init__.py`:

| Service | Purpose |
|---------|---------|
| `yeelight_pro.send_command` | Send raw command to gateway (debugging) |
| `yeelight_pro.mock_incoming_message` | Simulate gateway message (debugging) |
| `yeelight_pro.remove_stale_devices` | Clean up devices no longer in topology |
| `yeelight_pro.prestage_color_temp` | Set color temp while light is off (entity service on lights) |

**HA Event Bus:**
- Fires `yeelight_pro_event` events for device actions (button presses, motion, etc.)
  - Implementation: `_fire_ha_event()` in `custom_components/yeelight_pro/core/device.py`
  - Event data includes: device_id, device_name, event_type, params, gateway_host

**Config Flow:**
- User-initiated setup via `custom_components/yeelight_pro/config_flow.py`
- Options flow for modifying keepalive and transition time after setup
- Validates gateway reachability before creating entry

**Device Registry:**
- Devices registered with HA device registry via `DeviceInfo` in `XEntity.__init__()` (`__init__.py`)
- Supports device removal via `async_remove_config_entry_device()` (`__init__.py`)
- Stale device cleanup via `remove_stale_devices` service

**Translations:**
- English: `custom_components/yeelight_pro/translations/en.json`
- Chinese (Simplified): `custom_components/yeelight_pro/translations/zh-Hans.json`

## Webhooks & Callbacks

**Incoming:**
- None (no HTTP webhooks)

**Outgoing:**
- None

## Environment Configuration

**Required env vars:**
- None. All configuration is through HA UI or YAML.

**Secrets location:**
- No secrets required. Gateway uses unauthenticated local TCP.

---

*Integration audit: 2026-03-29*
