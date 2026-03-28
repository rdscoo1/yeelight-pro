# Testing Patterns

**Analysis Date:** 2026-03-29

## Test Framework

**Runner:**
- pytest >= 7.4.0
- pytest-asyncio >= 0.21.0
- Config: No explicit `pytest.ini` or `pyproject.toml` pytest section found; relies on defaults
- `.pytest_cache/` present at project root

**Assertion Library:**
- Built-in `assert` statements (pytest native)

**Additional plugins:**
- `pytest-cov` >= 4.1.0 (coverage reporting)
- `pytest-homeassistant-custom-component` >= 0.13.0 (HA test utilities)

**Run Commands:**
```bash
pytest tests/ -v                                          # Run all tests
pytest tests/ -v --cov=custom_components.yeelight_pro     # With coverage
pytest tests/ -v --cov=custom_components.yeelight_pro --cov-report=xml --cov-report=term  # CI mode
pytest tests/test_gateway.py -v                           # Single test file
pytest tests/test_gateway.py::test_gateway -v             # Single test
```

## Test File Organization

**Location:**
- All tests in `tests/` directory (separate from source)
- Root-level manual/interactive test scripts (not part of automated suite): `test_api_manual.py`, `test_api_interactive.py`, `test_gateway_interactive.py`, `test_gateway_manual.py`, `test_gateway_simple.py`

**Naming:**
- `test_{component}.py` pattern
- Test functions: `test_{description}` with snake_case

**Structure:**
```
tests/
  __init__.py                    # Package marker (empty)
  conftest.py                    # Shared fixtures
  test_gateway.py                # ProGateway unit tests (93 tests, largest file)
  test_device.py                 # XDevice and device subclass tests
  test_converters_base.py        # Converter encode/decode tests
  test_light_entity.py           # XLightEntity tests
  test_switch_entity.py          # XSwitchEntity tests
  test_binary_sensor.py          # XBinarySensorEntity tests
  test_sensor_entity.py          # XSensorEntity and XActionEntity tests
  test_button.py                 # XButtonEntity and XSceneEntity tests
  test_number_entity.py          # DelayoffEntity tests
  test_cover_entity.py           # XCoverEntity tests
  test_climate_entity.py         # XClimateEntity tests
  test_config_flow.py            # Config flow and options flow tests
  test_component_services.py     # ComponentServices (send_command, mock_incoming_message) tests
  test_init_integration.py       # async_setup, async_add_setuper tests
  test_integration_e2e.py        # End-to-end flow tests (topology -> device -> entity)
```

## Shared Fixtures (`tests/conftest.py`)

```python
@pytest.fixture(autouse=True)
def patch_setup_entities(request, monkeypatch):
    """Patches XDevice.setup_entities to no-op by default.
    Use @pytest.mark.no_patch_setup to opt out."""
    if "no_patch_setup" in request.keywords:
        return
    async def _noop(self):
        return
    monkeypatch.setattr(XDevice, "setup_entities", _noop)

@pytest.fixture
def gateway():
    return ProGateway("127.0.0.1")
```

**Key pattern:** `setup_entities` is patched to no-op globally because real entity setup requires full HA platform infrastructure. Tests that need real entity setup use `@pytest.mark.no_patch_setup`.

## Test Structure

**Suite Organization:**
- No `describe` blocks or nested classes; flat test functions at module level
- Related tests grouped by comments: `# ---------- send / topology ----------`
- Helper classes and factory functions defined at top of each test file

**Typical test pattern:**
```python
@pytest.mark.asyncio
async def test_send_topology_uses_post_cid_and_writes_json(monkeypatch):
    """Docstring describes what is tested (often in Russian)."""
    gtw = ProGateway("1.2.3.4")

    async def fake_connect(self):
        self.writer = DummyWriter()
        return True

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)

    await gtw.send("gateway_get.topology", wait_result=False)

    assert isinstance(gtw.writer, DummyWriter)
    assert len(gtw.writer.written) == 1
    raw = gtw.writer.written[0].rstrip(MSG_SPLIT)
    payload = json.loads(raw.decode("utf-8"))
    assert payload["method"] == "gateway_get.topology"
    assert payload["id"] == "gateway_post.topology"
```

## Mocking

**Framework:** `pytest.monkeypatch` (built-in)

**Patterns:**

1. **Instance method replacement:**
```python
monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
```

2. **Module-level function patching:**
```python
monkeypatch.setattr(
    "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
    fake_sleep,
)
```

3. **Instance attribute replacement:**
```python
monkeypatch.setattr(entity, "device_send_props", fake_send)
monkeypatch.setattr(entity, "async_write_ha_state", lambda *a, **k: None)
```

4. **Autouse fixture patching:**
```python
@pytest.fixture(autouse=True)
def patch_light_write_state(monkeypatch):
    monkeypatch.setattr(XLightEntity, "async_write_ha_state", lambda self, *_, **__: None)
```

**What to Mock:**
- `asyncio.sleep` (to avoid real delays in tests)
- `asyncio.open_connection` (to avoid real network connections)
- `async_write_ha_state` (to avoid HA platform requirements)
- `device_send_props` (to capture sent payloads without real gateway)
- `setup_entities` (autouse fixture, see conftest.py)
- `async_register_admin_service` (to avoid HA admin service registration)
- `persistent_notification.async_create` (to capture notifications)
- `get_gateway_from_config` (to provide fake gateways in config flow tests)

**What NOT to Mock:**
- `on_message` processing (tested with real JSON payloads)
- Converter `encode`/`decode` logic (tested directly)
- Device creation via `from_node` (tested with real node dicts)
- Entity `async_set_state` (tested with real data dicts)

## Fixtures and Factories

**Fake/Stub classes per test file** (not shared):
Each test file defines its own minimal fakes. This is a deliberate pattern:

```python
# In tests/test_device.py
class FakeGateway:
    def __init__(self, host="1.2.3.4", pid=1):
        self.host = host
        self.pid = pid
        self.devices = {}
        self.sent = []
        # ... minimal interface needed for tests

# In tests/test_light_entity.py
class FakeGateway:
    def __init__(self):
        self.host = "127.0.0.1"
        self.entry_id = "test-entry"
        self.device = type("DG", (), {"id": "gw-id"})()
```

**Factory functions** for creating test entities:
```python
def make_light_device(with_rgb=True, with_ct=True, with_brightness=True, with_transition=True):
    """Creates minimal XDevice suitable for XLightEntity tests."""
    node = {"id": 1, "nt": 2, "n": "Test Light", "type": 0}
    device = XDevice(node)
    device.hass = FakeHass()
    device.gateways.append(FakeGateway())
    # ... configure converters based on parameters
    return device, light_conv
```

**`DummyWriter` class** in `tests/test_gateway.py` used across multiple gateway tests:
```python
class DummyWriter:
    def __init__(self):
        self.written = []
        self.closed = False
    def write(self, data: bytes):
        self.written.append(data)
    async def drain(self):
        return
    def close(self):
        self.closed = True
    async def wait_closed(self):
        return
```

**`GatewayForTests`** subclass in `tests/test_gateway.py` that overrides `add_device` to skip `setup_entities`:
```python
class GatewayForTests(ProGateway):
    async def add_device(self, device):
        if not device.hass:
            device.hass = self.hass
        if device.id not in self.devices:
            self.devices[device.id] = device
        if self not in device.gateways:
            device.gateways.append(self)
        # No setup_entities call
```

## Coverage

**Requirements:** No enforced minimum threshold

**View Coverage:**
```bash
pytest tests/ -v --cov=custom_components.yeelight_pro --cov-report=term
pytest tests/ -v --cov=custom_components.yeelight_pro --cov-report=html  # HTML report
```

**CI Coverage:** Uploaded to Codecov via GitHub Actions (see `.github/workflows/ci.yml:56-61`)

**`.coverage` file** present at project root (from previous runs)

## Test Types

**Unit Tests (majority):**
- Converter encode/decode: `tests/test_converters_base.py`
- Device creation, type detection, property handling: `tests/test_device.py`
- Gateway protocol: send, receive, reconnect, keepalive: `tests/test_gateway.py`
- Entity state management: `tests/test_light_entity.py`, `tests/test_switch_entity.py`, etc.
- Config flow: `tests/test_config_flow.py`

**Integration Tests:**
- `tests/test_integration_e2e.py`: Full flow from topology message through device creation to entity state updates
- `tests/test_init_integration.py`: Tests `async_setup` and `async_add_setuper` with mocked HA
- `tests/test_component_services.py`: Tests `ComponentServices` with mocked gateways

**E2E Tests:**
- `tests/test_integration_e2e.py` uses `E2EGateway` (extends `ProGateway`) to test full message processing pipeline
- Tests include: topology -> device creation, prop changes, event firing to HA bus, device disappearance handling

**Manual/Interactive Tests (not in CI):**
- `test_api_manual.py`, `test_api_interactive.py` at project root
- `test_gateway_interactive.py`, `test_gateway_manual.py`, `test_gateway_simple.py` at project root
- These require real hardware/network and are not part of automated suite

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_something(monkeypatch):
    gtw = ProGateway("1.2.3.4")
    # ... setup
    result = await gtw.some_method()
    assert result == expected
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_check_available_returns_exception_on_failure(monkeypatch):
    gtw = ProGateway("1.2.3.4")

    async def fake_open_connection(_host, _port):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.open_connection",
        fake_open_connection,
    )

    err = await gtw.check_available()
    assert isinstance(err, RuntimeError)
```

**State verification pattern (regression tests):**
```python
@pytest.mark.asyncio
async def test_prop_changed_cancels_verify_task_when_state_matches():
    """Regression test for bug: actual p=None because code read
    data.get('p') instead of data.get('params', {}).get('p')."""
    dev = _make_light_device()
    # ... setup expected state and verify task
    node = {"id": 42, "nt": 2, "pid": 1, "params": {"p": True, "l": 80}}
    await dev.prop_changed(node)
    assert dev._expected_state is None
```

**Capturing sent data:**
```python
sent = {}
async def fake_send(payload):
    sent.update(payload)
    return True
monkeypatch.setattr(entity, "device_send_props", fake_send)

await entity.async_turn_on(**{ATTR_RGB_COLOR: (255, 0, 0)})
assert sent[ATTR_RGB_COLOR] == (255, 0, 0)
```

**Opting out of autouse fixture:**
```python
@pytest.mark.no_patch_setup
@pytest.mark.asyncio
async def test_topology_creates_light_device_with_converters():
    """Needs real setup_entities for full flow test."""
```

## CI/CD Configuration

**File:** `.github/workflows/ci.yml`

**Jobs:**
1. `validate`: HACS validation + Hassfest validation
2. `test`: Runs on Python 3.11 and 3.12 matrix

**Test step:**
```yaml
- name: Install dependencies
  run: pip install -r requirements-dev.txt

- name: Run tests
  run: pytest tests/ -v --cov=custom_components.yeelight_pro --cov-report=xml --cov-report=term

- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
```

**Triggers:** Push to `main`, `master`, `feature/*`; PRs to `main`, `master`; manual dispatch

## Bilingual Test Documentation

Test docstrings are written in both Russian and English. Russian is more common in older tests:
```python
"""Простейший заглушечный hass для ProGateway в этих тестах."""  # Russian
"""Full flow: topology message -> LightDevice created -> converters set up."""  # English
```

When writing new tests, use English docstrings for consistency with newer code.

---

*Testing analysis: 2026-03-29*
