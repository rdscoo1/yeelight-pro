# Yeelight Pro Integration for Home Assistant

[![CI](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/rdscoo1/yeelight-pro)](https://github.com/rdscoo1/yeelight-pro/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**English** | [Русский](README_RU.md)

Yeelight Pro is a local-push Home Assistant integration for Yeelight Pro gateways and WiFi panels. It connects to the device over the local TCP API, discovers the gateway topology, creates Home Assistant entities for supported devices, and keeps entity state updated from gateway push messages.

Current integration version: **1.3.5**.

## Highlights

- Local TCP connection, no cloud polling and no external Python requirements.
- UI config flow for **Gateway Pro** and **WiFi Panel** gateway types.
- Automatic topology discovery for devices, groups, scenes, and gateway entities.
- Reconnect handling with exponential backoff, keepalive checks, pending-command cleanup, and reconnect notifications.
- Command retry and passive state verification for power changes.
- Gateway diagnostics sensor, Home Assistant diagnostics export, and firmware update entities.
- Stale device cleanup service for devices no longer present in topology.
- Test suite under `tests/components/yeelight_pro/` with 180+ tests.

## Supported Platforms

The integration currently forwards these Home Assistant platforms:

- `light`
- `switch`
- `binary_sensor`
- `sensor`
- `number`
- `button`
- `cover`
- `climate`
- `update`

## Supported Devices and Entities

Entity creation is based on the gateway topology and each device's reported properties.

| Device area | Supported behavior |
|-------------|--------------------|
| Gateway | Connection binary sensor, firmware update entity, diagnostics sensor |
| Lights | On/off, brightness, color temperature, RGB, transition duration, delayed-off number |
| Light groups | Group light entities with capability detection from members where possible |
| Switch panels and relays | One or more switch entities, panel action sensor, optional backlight light |
| WiFi panels | Two relay switches and action sensor |
| Motion and presence sensors | Motion binary sensor, event sensors, optional luminance sensor for supported presence devices |
| Contact sensors | Contact binary sensor and open/close events |
| Knobs and switch sensors | Action sensor and button/knob events |
| Covers | Open, close, stop, position, current position, optional reverse switch |
| Air conditioners | HVAC mode, target/current temperature, fan mode, turn on/off |
| Scenes | Scene buttons created from gateway scene topology |

Unsupported device types are ignored and logged as unsupported.

## Installation

### HACS

1. Open **HACS** -> **Integrations** -> **Custom repositories**.
2. Add `https://github.com/rdscoo1/yeelight-pro.git`.
3. Select **Integration** as the category.
4. Install **Yeelight Pro**.
5. Restart Home Assistant.

### Manual

1. Download the latest release from [GitHub Releases](https://github.com/rdscoo1/yeelight-pro/releases).
2. Copy `custom_components/yeelight_pro` into `/config/custom_components/`.
3. Restart Home Assistant.

## Configuration

### UI setup

1. Go to **Settings** -> **Devices & services** -> **Add integration**.
2. Search for **Yeelight Pro**.
3. Enter the gateway IP address.
4. Choose gateway type:
   - `Gateway Pro`
   - `Wifi Panel`
5. The integration checks that the TCP endpoint is reachable before creating the entry.

### Options

Open the integration options to adjust:

| Option | Default | Range / values |
|--------|---------|----------------|
| Host | Current host | Any hostname or IP reachable from Home Assistant |
| Gateway type | `Gateway Pro` | `Gateway Pro`, `Wifi Panel` |
| Port | `65443` | `1`-`65535` |
| Keepalive | `30` seconds | `10`-`300` seconds |
| Transition time | `5.0` seconds | `0.5`-`30.0` seconds |

Changing options reloads the config entry so the gateway client restarts with the new settings.

### YAML setup

UI setup is recommended. YAML setup is still supported for gateway entries:

```yaml
yeelight_pro:
  gateways:
    - host: 192.168.1.100
      pid: 1
      port: 65443
      keepalive: 30
      transition_time: 5.0
```

`pid: 1` is Gateway Pro and `pid: 2` is WiFi Panel.

## Services

### `yeelight_pro.send_command`

Send a raw command to a gateway. The result is also fired on the Home Assistant event bus as `yeelight_pro.send_command`.

```yaml
service: yeelight_pro.send_command
data:
  host: 192.168.1.100
  method: gateway_get.node
  params:
    id: 0
  throw: true
```

Fields:

| Field | Required | Description |
|-------|----------|-------------|
| `host` | Yes | Gateway host to send to |
| `method` | Yes | Gateway API method |
| `params` | No | Command parameters object |
| `result` | No | Optional result payload override for the event/notification |
| `throw` | No | If true, show a persistent notification with the result |

### `yeelight_pro.mock_incoming_message`

Inject a JSON gateway message into the message handler for debugging.

```yaml
service: yeelight_pro.mock_incoming_message
data:
  host: 192.168.1.100
  message: >
    {"id": 8218, "method": "gateway_post.event",
     "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}
```

Invalid JSON and non-object JSON payloads are rejected with a persistent notification.

### `yeelight_pro.remove_stale_devices`

Remove device registry entries for devices that are no longer present in the gateway topology. Use `dry_run: true` first to preview the cleanup.

```yaml
service: yeelight_pro.remove_stale_devices
data:
  host: 192.168.1.100
  dry_run: true
```

`host` is optional. When omitted, all configured gateways are checked.

### `light.prestage_color_temp`

Set color temperature on a Yeelight Pro light while keeping the light off. This is an entity service registered on the `light` platform.

```yaml
service: light.prestage_color_temp
target:
  entity_id: light.bedroom_ceiling
data:
  color_temp_kelvin: 2700
```

## Events

Device events are fired on the Home Assistant bus as `yeelight_pro_event`.

Event data includes:

- `device_id`
- `device_name`
- `device_type`
- `event_type`
- `params`
- `decoded`
- `gateway_host`

Example automation:

```yaml
automation:
  - alias: "Yeelight panel action"
    trigger:
      - platform: event
        event_type: yeelight_pro_event
        event_data:
          event_type: panel.click
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room_main
```

## Reliability and Diagnostics

The gateway client is designed for long-running local connections:

- TCP reconnect loop with exponential backoff from 1 to 60 seconds.
- Keepalive pings using `gateway_get.node` or `device_get.node`.
- Reconnect after consecutive keepalive failures.
- Reconnect after repeated malformed JSON messages.
- Read buffer limit to avoid unbounded memory growth from incomplete payloads.
- Command retry for most write/query methods.
- Topology cache with 5 minute TTL.
- State reconciliation after reconnect.
- Removed topology devices are marked unavailable, not deleted, so entity IDs are preserved.
- Passive state verification retries power commands when the gateway reports a mismatched state.

The gateway diagnostics sensor reports connection health as:

- `OK`
- `Degraded`
- `Poor`
- `Disconnected`
- `No Gateway`

Diagnostics attributes include uptime, message counts, command success/failure counts, retry counts, success rate, reconnect count, keepalive results, last error, transition time, and topology cache age.

Home Assistant config-entry diagnostics are also implemented and redact host values.

## Automation Examples

### Turn on a light when motion is detected

```yaml
automation:
  - alias: "Motion: hallway light"
    trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway_ceiling
        data:
          brightness: 255
```

### Prestage color temperature before turning on a light

```yaml
automation:
  - alias: "Light: warm morning start"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: light.prestage_color_temp
        target:
          entity_id: light.bedroom_ceiling
        data:
          color_temp_kelvin: 2700
      - service: light.turn_on
        target:
          entity_id: light.bedroom_ceiling
        data:
          brightness: 128
```

### Preview stale registry cleanup

```yaml
service: yeelight_pro.remove_stale_devices
data:
  dry_run: true
```

## Troubleshooting

| Problem | What to check |
|---------|---------------|
| Cannot add integration | Verify gateway IP, port `65443`, network reachability, and selected gateway type |
| Gateway becomes unavailable | Check local network stability and gateway power |
| Device entity unavailable | Device disappeared from topology or reports offline |
| Device is missing | Check pairing/topology in the Yeelight Pro app, then reload the integration |
| Stale device remains in registry | Run `yeelight_pro.remove_stale_devices` with `dry_run: true`, then without dry run |
| Raw command does nothing | Use `yeelight_pro.send_command` with `throw: true` and enable debug logging |

### Debug logging

Add this to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.yeelight_pro: debug
    custom_components.yeelight_pro.core: debug
```

Then open **Settings** -> **System** -> **Logs** and filter by `yeelight_pro`.

## Development

### Local setup

```bash
git clone https://github.com/rdscoo1/yeelight-pro.git
cd yeelight-pro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Tests

```bash
pytest -q
pytest -q --cov=custom_components/yeelight_pro --cov-report=term-missing
```

Tests live in `tests/components/yeelight_pro/` and use `pytest-homeassistant-custom-component` for Home Assistant fixtures.

CI runs:

- HACS validation
- hassfest
- pytest on Python 3.11 and 3.12
- coverage upload to Codecov

### Release checklist

1. Update `version` in `custom_components/yeelight_pro/manifest.json`.
2. Update release notes/changelog.
3. Commit and tag:

   ```bash
   git tag -a v1.3.5 -m "Release 1.3.5"
   git push --tags
   ```

4. Create a GitHub Release.

## Credits

| Role | Contributor |
|------|-------------|
| Lead developer | [@rdscoo1](https://github.com/rdscoo1) |
| Original integration | [@hasscc](https://github.com/hasscc) |
| Platform | [Yeelight](https://www.yeelight.com/) |

## License

This project is licensed under the [MIT License](LICENSE).
