# Yeelight Pro Integration for Home Assistant

[![CI](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rdscoo1/yeelight-pro/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/rdscoo1/yeelight-pro)](https://github.com/rdscoo1/yeelight-pro/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**English** | [Русский](README_RU.md)

## Overview

Yeelight Pro is a custom integration for [Home Assistant](https://www.home-assistant.io/) that connects your **Yeelight Pro Gateway** and all connected devices to the Home Assistant ecosystem. It provides comprehensive control and monitoring of lights, sensors, switches, climate devices, and more through a local TCP connection.

> 🧩 Originally developed by [@hasscc](https://github.com/hasscc), extensively refactored and modernized by [@rdscoo1](https://github.com/rdscoo1) with improved stability, comprehensive diagnostics, and 100+ automated tests.

## Features

### Device Support
- **Lights** — full control (brightness, color temperature, RGB, transitions)
- **Climate** — air conditioners via Yeelight Pro
- **Covers** — curtains and blinds
- **Switches** — wall switches, panels, relays
- **Sensors** — motion, contact, illumination, temperature, humidity
- **Buttons** — scene buttons and panel controls
- **Groups** — light groups from gateway

### Monitoring & Diagnostics
- **Entity availability** based on device online status
- **Gateway connection** status as dedicated binary sensor
- **Firmware update** entity showing available updates
- **Event bus integration** for automations

### Reliability
- **Configurable keepalive** (10-300 seconds)
- **Reconnect notifications** with persistent alerts
- **Automatic device discovery** from gateway topology
- **Stale device removal** service

### Automation Support
- Custom services: `send_command`, `mock_incoming_message`, `remove_stale_devices`
- Full entity state exposure for triggers and conditions
- Event bus publishing for advanced automations
- Works with scripts, automations, and voice assistants

## Installation

### Option 1 — via HACS (Recommended)

1. Open **HACS** → **Integrations** → **⋮** (menu) → **Custom repositories**
2. Add repository URL: `https://github.com/rdscoo1/yeelight-pro.git`
3. Select **Integration** as the category
4. Click **Add**, then find **Yeelight Pro** and click **Install**
5. Restart Home Assistant

### Option 2 — Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/rdscoo1/yeelight-pro/releases)
2. Copy `custom_components/yeelight_pro` to your `/config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Yeelight Pro**
3. Enter your gateway IP address (e.g., `192.168.1.100`)
4. All connected devices will appear automatically

### Options

After setup, you can configure:
- **Keepalive interval** (10–300 seconds) — how often to ping the gateway

## Entities

Each device creates entities based on its capabilities:

| Platform | Entity ID Example | Description |
|----------|-------------------|-------------|
| `light` | `light.bedroom_ceiling` | Light control: power, brightness, color temp, RGB |
| `climate` | `climate.living_room_ac` | AC control: mode, temperature, fan speed |
| `cover` | `cover.bedroom_curtain` | Curtain control: open, close, position |
| `switch` | `switch.hallway_relay` | Switch control: on/off |
| `binary_sensor` | `binary_sensor.door_contact` | Contact sensor: open/closed |
| `sensor` | `sensor.living_room_motion` | Motion sensor with action attribute |
| `button` | `button.scene_movie_mode` | Scene activation button |
| `binary_sensor` | `binary_sensor.gateway_connection` | Gateway connectivity status |
| `update` | `update.gateway_firmware` | Firmware update availability |

## Services

### send_command

Send a raw command to the gateway and optionally show the result as a persistent notification.

```yaml
service: yeelight_pro.send_command
data:
  host: 192.168.1.100
  method: gateway_get.node
  params:
    id: 0
  throw: true
```

### mock_incoming_message

Mock an incoming JSON message from the gateway for testing.

```yaml
service: yeelight_pro.mock_incoming_message
data:
  host: 192.168.1.100
  message: >
    {"id": 8218, "method": "gateway_post.event",
     "nodes": [{"params": {}, "value": "motion.false", "id": 301809111, "nt": 2}]}
```

### remove_stale_devices

Remove devices that are no longer present in the gateway topology.

```yaml
service: yeelight_pro.remove_stale_devices
data:
  host: 192.168.1.100  # Optional, removes from all gateways if not specified
  dry_run: true  # Optional, shows what would be removed without actually removing
```

## Automation Examples

### 1. Turn on Light When Motion Detected

```yaml
automation:
  - alias: "Motion: Turn on hallway light"
    description: "Turn on light when motion is detected"
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

### 2. Panel Button Control

```yaml
automation:
  - alias: "Panel: Toggle living room light"
    description: "Toggle light on single button press"
    trigger:
      - platform: state
        entity_id: sensor.living_room_panel_action
        to: "button1_single"
    action:
      - service: light.toggle
        target:
          entity_id: light.living_room_main
```

### 3. Climate Control Based on Temperature

```yaml
automation:
  - alias: "Climate: Cool down when hot"
    description: "Turn on AC when temperature exceeds threshold"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_temperature
        above: 26
    action:
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.living_room_ac
        data:
          hvac_mode: cool
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room_ac
        data:
          temperature: 23
```

### 4. Gateway Reconnect Alert

```yaml
automation:
  - alias: "Gateway: Reconnect notification"
    description: "Send notification when gateway reconnects"
    trigger:
      - platform: state
        entity_id: binary_sensor.gateway_connection
        from: "off"
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Yeelight Pro gateway reconnected"
```

### 5. Light Group Control

```yaml
automation:
  - alias: "Group: All lights off at night"
    description: "Turn off all light groups at bedtime"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.yp_group_1_light
```

### 6. Prestage Color Temperature Before Turning On

Use the `prestage_color_temp` service to set color temperature while the light is OFF, then turn it on. This ensures the light turns on with the desired color temperature immediately.

```yaml
automation:
  - alias: "Light: Warm morning light"
    description: "Set warm color temperature before turning on morning light"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      # First, set color temperature while light is OFF
      - service: yeelight_pro.prestage_color_temp
        target:
          entity_id: light.bedroom_ceiling
        data:
          color_temp_kelvin: 2700  # Warm white
      # Then turn on the light
      - service: light.turn_on
        target:
          entity_id: light.bedroom_ceiling
        data:
          brightness: 128
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Integration fails to load | Old or corrupted files | Reinstall from HACS |
| Cannot connect to gateway | Wrong IP or network issue | Verify gateway IP and network connectivity |
| Device shows unavailable | Device offline or disconnected | Check device power and connection |
| Entities not appearing | Device not in topology | Check gateway app and device pairing |
| Deprecated warnings | Using old constants | Update to latest version |

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.yeelight_pro: debug
    custom_components.yeelight_pro.core: debug
```

View logs at: **Settings** → **System** → **Logs** → filter by `yeelight_pro`

## Development

### Local Setup

```bash
git clone https://github.com/rdscoo1/yeelight-pro.git
cd yeelight-pro
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### Running Tests

```bash
pytest              # Quick run
pytest -vv          # Verbose output
pytest --cov        # With coverage report
```

### Test Coverage

The test suite includes **100+ tests** covering:

| Module | Coverage |
|--------|----------|
| `__init__.py` | Setup, coordinator, entity management |
| `core/device.py` | Device classes, converters, state updates |
| `core/gateway.py` | TCP connection, message parsing, keepalive |
| `light.py` | Light entity, color modes, transitions |
| `binary_sensor.py` | Binary sensors, gateway connection |
| `config_flow.py` | Config and options flow |
| `update.py` | Firmware update entities |

### CI/CD

This repository uses GitHub Actions for:
- **pytest** — automated testing on Python 3.11 and 3.12
- **HACS validation** — ensures HACS compatibility
- **hassfest** — validates Home Assistant manifest

### Releasing

1. Update `version` in `manifest.json`
2. Commit and push changes
3. Create a tag:
   ```bash
   git tag -a v0.3.0 -m "Release 0.3.0"
   git push --tags
   ```
4. Create a GitHub Release

## Credits

| Role | Contributor |
|------|-------------|
| Lead Developer | [@rdscoo1](https://github.com/rdscoo1) |
| Original Integration | [@hasscc](https://github.com/hasscc) |
| Platform | [Yeelight](https://www.yeelight.com/) |

## License

This project is licensed under the [MIT License](LICENSE).
