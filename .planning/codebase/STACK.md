# Technology Stack

**Analysis Date:** 2026-03-29

## Languages

**Primary:**
- Python 3.11 / 3.12 - All source code (CI matrix tests both versions)

**Secondary:**
- JSON - Configuration files (`hacs.json`, `manifest.json`, translation files)
- YAML - Service definitions (`custom_components/yeelight_pro/services.yaml`), CI config (`.github/workflows/ci.yml`)

## Runtime

**Environment:**
- Home Assistant Core >= 2024.1.0 (dev dependency in `requirements-dev.txt`)
- Home Assistant >= 2022.7.0 (minimum required, declared in `hacs.json`)
- Python 3.11+ (CI matrix: 3.11, 3.12)

**Package Manager:**
- pip (standard Python package manager)
- Lockfile: Not present (uses `requirements-dev.txt` with minimum version pins)

## Frameworks

**Core:**
- Home Assistant Core - Custom integration framework
  - `homeassistant.core` - Core HA runtime
  - `homeassistant.config_entries` - Config flow system
  - `homeassistant.helpers` - Entity, device registry, service registration
  - `homeassistant.components` - Platform base classes (light, switch, cover, climate, etc.)

**Testing:**
- pytest >= 7.4.0 - Test runner (`requirements-dev.txt`)
- pytest-asyncio >= 0.21.0 - Async test support (`requirements-dev.txt`)
- pytest-cov >= 4.1.0 - Coverage reporting (`requirements-dev.txt`)
- pytest-homeassistant-custom-component >= 0.13.0 - HA test fixtures and helpers (`requirements-dev.txt`)

**Build/Dev:**
- ruff >= 0.1.0 - Linting and code formatting (`requirements-dev.txt`, `.ruff_cache/` present with version 0.14.4)
- GitHub Actions - CI/CD pipeline (`.github/workflows/ci.yml`)

## Key Dependencies

**Critical (runtime):**
- `voluptuous` - Schema validation for config flows, services, and YAML config (imported as `vol` throughout)
  - Used in: `custom_components/yeelight_pro/__init__.py`, `custom_components/yeelight_pro/config_flow.py`, `custom_components/yeelight_pro/light.py`
- `homeassistant` - The entire HA framework; this is a custom integration, not standalone
  - No pip-installable runtime requirements declared in `manifest.json` (`"requirements": []`)

**Infrastructure:**
- `asyncio` - Core async networking (TCP client in `custom_components/yeelight_pro/core/gateway.py`)
- `json` - Message serialization/deserialization for gateway TCP protocol
- `dataclasses` - Data structures (`GatewayStatistics` in `custom_components/yeelight_pro/core/gateway.py`)

**CI/Validation:**
- `hacs/action@main` - HACS store validation (`.github/workflows/ci.yml`)
- `home-assistant/actions/hassfest@master` - HA manifest/integration validation (`.github/workflows/ci.yml`)
- `codecov/codecov-action@v4` - Coverage upload (`.github/workflows/ci.yml`)

## Configuration

**Environment:**
- No `.env` files detected; no environment variables required
- All configuration is done through Home Assistant UI (config flow) or YAML
- Config flow defined in `custom_components/yeelight_pro/config_flow.py`
- YAML schema defined in `custom_components/yeelight_pro/__init__.py` (`CONFIG_SCHEMA`)

**Key configuration parameters:**
- `host` - Gateway IP address (required)
- `pid` - Gateway type: 1 = Gateway Pro, 2 = Wifi Panel (defined in `custom_components/yeelight_pro/core/const.py`)
- `keepalive` - Keepalive interval in seconds, default 30 (range 10-300)
- `transition_time` - Light transition time, default 5.0s (range 0.5-30.0)

**Build:**
- No build step required; integration is installed directly into HA `custom_components/` directory
- HACS is the primary distribution mechanism (`hacs.json`)

## Integration Metadata

**Manifest:** `custom_components/yeelight_pro/manifest.json`
- Domain: `yeelight_pro`
- Version: 1.3.2
- IoT class: `local_push` (local network, push-based updates)
- Integration type: `hub`
- Config flow: enabled

## Platform Requirements

**Development:**
- Python 3.11 or 3.12
- `pip install -r requirements-dev.txt`
- Home Assistant development environment (provided by `pytest-homeassistant-custom-component`)

**Production:**
- Home Assistant instance >= 2022.7.0
- Yeelight Pro Gateway or Wifi Panel on local network (TCP port 65443)
- No cloud services or internet required

---

*Stack analysis: 2026-03-29*
