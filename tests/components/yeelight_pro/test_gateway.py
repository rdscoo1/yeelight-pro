import asyncio
import json

import pytest

from custom_components.yeelight_pro.core.gateway import (
    ProGateway,
    MSG_SPLIT,
    MIN_RECONNECT_DELAY,
    MAX_JSON_ERRORS,
    KEEPALIVE_FAILURE_THRESHOLD,
)
from custom_components.yeelight_pro.core.const import PID_WIFI_PANEL
from custom_components.yeelight_pro.core.device import GatewayDevice, WifiPanelDevice, XDevice


class Hass:
    """Простейший заглушечный hass для ProGateway в этих тестах."""
    def __init__(self):
        self.events = []


class GatewayForTests(ProGateway):
    async def add_device(self, device, setup: bool = True):
        """Подключаем девайс к шлюзу, но НЕ вызываем setup_entities()."""
        if not device.hass:
            device.hass = self.hass
        if device.id not in self.devices:
            self.devices[device.id] = device
        if self not in device.gateways:
            device.gateways.append(self)
        # никаких await device.setup_entities()


def get_gateway(host=None):
    if not host:
        host = "127.0.0.1"
    return GatewayForTests(host, hass=Hass())


def test_reconnect_notification_id_includes_reconnect_count(monkeypatch):
    gtw = get_gateway("1.2.3.4")
    notifications = []

    def fake_create(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(
        "homeassistant.components.persistent_notification.async_create",
        fake_create,
    )

    gtw.stats.reconnect_count = 1
    gtw._send_reconnect_notification()
    gtw.stats.reconnect_count = 2
    gtw._send_reconnect_notification()

    assert [
        kwargs["notification_id"] for _, kwargs in notifications
    ] == [
        "yeelight_pro-reconnect-1.2.3.4-1",
        "yeelight_pro-reconnect-1.2.3.4-2",
    ]


class DummyWriter:
    """Простейший writer, который только накапливает записанные байты."""

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


# ---------- send / topology ----------


@pytest.mark.asyncio
async def test_send_topology_uses_post_cid_and_writes_json(monkeypatch):
    """Для gateway_get.topology id должен быть 'gateway_post.topology', а не random int."""
    gtw = ProGateway("1.2.3.4")
    gtw.writer = DummyWriter()

    await gtw.send("gateway_get.topology", wait_result=False)

    assert isinstance(gtw.writer, DummyWriter)
    assert len(gtw.writer.written) == 1

    raw = gtw.writer.written[0].rstrip(MSG_SPLIT)
    payload = json.loads(raw.decode("utf-8"))

    assert payload["method"] == "gateway_get.topology"
    assert payload["id"] == "gateway_post.topology"


@pytest.mark.asyncio
async def test_send_wait_result_resolved_by_on_message(monkeypatch):
    """send(wait_result=True) ждёт ответа, который приходит через on_message."""
    gtw = ProGateway("1.2.3.4")
    gtw.writer = DummyWriter()  # считаем, что уже подключены

    # запускаем send в фоне
    send_task = asyncio.create_task(
        gtw.send("gateway_get.node", params={"id": 1}, wait_result=True)
    )

    # даём циклу чуть поработать, чтобы _msgs успел заполниться
    await asyncio.sleep(0)

    # cid теперь берётся из монотонного счётчика; читаем его из _msgs
    pending_ids = [k for k in gtw._msgs if isinstance(k, int)]
    assert len(pending_ids) == 1
    cid = pending_ids[0]
    assert cid in gtw._msgs  # future зарегистрирован

    # имитируем приход ответа
    reply = {"id": cid, "result": {"ok": True}}
    await gtw.on_message(json.dumps(reply).encode("utf-8"))

    res = await send_task
    assert res == reply
    assert cid not in gtw._msgs  # future удалён


# ---------- check_available ----------


@pytest.mark.asyncio
async def test_check_available_returns_exception_on_failure(monkeypatch):
    """check_available возвращает исключение при ошибке подключения."""
    gtw = ProGateway("1.2.3.4")

    async def fake_open_connection(_host, _port):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.open_connection",
        fake_open_connection,
    )

    err = await gtw.check_available()
    assert isinstance(err, RuntimeError)


@pytest.mark.asyncio
async def test_check_available_closes_temporary_socket(monkeypatch):
    """check_available() закрывает тестовое TCP-соединение после проверки."""
    gtw = ProGateway("1.2.3.4")

    class FakeWriter:
        def __init__(self):
            self.closed = False
            self.wait_closed_called = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            self.wait_closed_called = True

    writer = FakeWriter()

    async def fake_open_connection(_host, _port):
        return object(), writer

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.open_connection",
        fake_open_connection,
    )

    err = await gtw.check_available()

    assert err is None
    assert writer.closed is True
    assert writer.wait_closed_called is True


# ---------- get_scene ----------


@pytest.mark.asyncio
async def test_get_scene_unwraps_scenes(monkeypatch):
    """get_scene разворачивает поле 'scenes' из ответа send."""
    gtw = ProGateway("1.2.3.4")

    async def fake_send(method, params=None, wait_result=True):
        assert method == "gateway_get.scene"
        assert params == {"id": 42}
        assert wait_result is True
        return {"scenes": [1, 2, 3]}

    monkeypatch.setattr(gtw, "send", fake_send)

    res = await gtw.get_scene(42)
    assert res == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_scene_none_when_no_result(monkeypatch):
    """Если send вернул None, get_scene тоже возвращает None."""
    gtw = ProGateway("1.2.3.4")

    async def fake_send(method, params=None, wait_result=True):
        return None

    monkeypatch.setattr(gtw, "send", fake_send)

    res = await gtw.get_scene(1)
    assert res is None


# ---------- on_message / создание устройств ----------


@pytest.mark.asyncio
async def test_on_message_creates_gateway_device(monkeypatch):
    """При topology-сообщении создаётся GatewayDevice, если pid != PID_WIFI_PANEL."""
    gtw = ProGateway("1.2.3.4")

    added = {}

    async def fake_add_device(self, device):
        added["device"] = device
        self.devices[device.id] = device
        device.gateways.append(self)
        device.hass = self.hass

    monkeypatch.setattr(ProGateway, "add_device", fake_add_device, raising=True)

    topo = {
        "id": "gateway_post.topology",
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": -1, "pid": "gateway", "type": "gateway"},
        ],
    }

    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    assert isinstance(gtw.device, GatewayDevice)
    assert added["device"] is gtw.device
    # GatewayDevice в коде переопределяет id на host
    assert "1.2.3.4" in gtw.devices
    assert gtw.devices["1.2.3.4"] is gtw.device


@pytest.mark.asyncio
async def test_on_message_updates_existing_gateway_device_from_zero_id_topology():
    """Gateway topology nodes with id=0 should update the existing gateway device."""
    gtw = ProGateway("1.2.3.4")
    gtw.device = GatewayDevice(gtw)
    gtw.devices[gtw.device.id] = gtw.device

    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 0, "nt": -1, "n": "Gateway Renamed", "prop": {"fv": "2.0.1"}},
        ],
    }

    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    assert gtw.device.name == "Gateway Renamed"
    assert gtw.device.firmware_version == "2.0.1"


@pytest.mark.asyncio
async def test_on_message_routes_zero_id_prop_to_gateway_device():
    """gateway_post.prop with id=0 should resolve to the gateway device."""
    gtw = ProGateway("1.2.3.4")
    gtw.device = GatewayDevice(gtw)
    gtw.devices[gtw.device.id] = gtw.device

    prop_msg = {
        "method": "gateway_post.prop",
        "nodes": [
            {"id": 0, "nt": -1, "fv": "3.1.4"},
        ],
    }

    await gtw.on_message(json.dumps(prop_msg).encode("utf-8"))

    assert gtw.device.firmware_version == "3.1.4"


@pytest.mark.asyncio
async def test_on_message_creates_device_for_pid_wifi_panel(monkeypatch):
    """
    При pid=PID_WIFI_PANEL на topology-сообщении создаётся какое-то устройство
    (в текущей реализации это GatewayDevice, но нам важно, что оно вообще есть
    и привязано к gateway).
    """
    gtw = ProGateway("1.2.3.4", pid=PID_WIFI_PANEL)

    async def fake_add_device(self, device):
        self.devices[device.id] = device
        device.gateways.append(self)

    monkeypatch.setattr(ProGateway, "add_device", fake_add_device, raising=True)

    topo = {
        "id": "gateway_post.topology",
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 123, "nt": 2, "pid": "wifi_panel", "type": 7},
        ],
    }

    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    # Важно: устройство создано и привязано к gateway
    assert gtw.device is not None
    # id у WifiPanelDevice — 123, у GatewayDevice — host; проверяем оба варианта
    dev_id = gtw.device.id
    assert dev_id in gtw.devices
    assert gtw.devices[dev_id] is gtw.device
    # Если реализацию поменяют на WifiPanelDevice — тест останется валиден
    assert isinstance(gtw.device, (GatewayDevice, WifiPanelDevice))


@pytest.mark.asyncio
async def test_stop_cancels_task_closes_writer_and_clears_devices():
    """stop() должен отменять main_task, закрывать writer и убирать gateway из device.gateways."""
    gtw = ProGateway("1.2.3.4")

    class FakeWriter:
        def __init__(self):
            self.closed = False
            self.wait_closed_called = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            self.wait_closed_called = True

    async def fake_main_task():
        await asyncio.sleep(100)

    writer = FakeWriter()
    task = asyncio.create_task(fake_main_task())

    gtw.writer = writer
    gtw.main_task = task

    class DummyDevice:
        def __init__(self):
            self.gateways = [gtw]

    dev = DummyDevice()
    gtw.devices = {1: dev}

    await gtw.stop()

    assert task.cancelled() is True
    assert writer.closed is True
    assert writer.wait_closed_called is True
    assert gtw.writer is None
    assert gtw.main_task is None
    assert gtw not in dev.gateways


@pytest.mark.asyncio
async def test_stop_cancels_pending_futures():
    """stop() должен отменять все pending futures в _msgs."""
    gtw = ProGateway("1.2.3.4")

    loop = asyncio.get_running_loop()
    fut1 = loop.create_future()
    fut2 = loop.create_future()
    fut2.set_result("done")  # already done

    gtw._msgs = {1: fut1, 2: fut2}

    await gtw.stop()

    assert fut1.cancelled() is True
    assert gtw._msgs == {}
    assert gtw._stopping is True


@pytest.mark.asyncio
async def test_send_handles_drain_error(monkeypatch):
    """send() должен корректно обрабатывать ошибки в drain()."""
    gtw = ProGateway("1.2.3.4")

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def write(self, data):
            pass

        async def drain(self):
            raise ConnectionError("Broken pipe")

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    gtw.writer = FakeWriter()

    # Use _send_internal to test drain error handling directly (bypasses command queue)
    result = await gtw._send_internal("test_method", wait_result=True)

    assert result is None
    assert gtw.writer is None  # connection closed
    assert len(gtw._msgs) == 0  # future cleaned up


@pytest.mark.asyncio
async def test_send_internal_returns_none_when_not_connected(monkeypatch):
    """_send_internal() должен возвращать None если не удалось подключиться."""
    gtw = ProGateway("1.2.3.4")

    async def fake_connect(self):
        return False

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)

    # Test _send_internal directly — it checks connection before sending
    result = await gtw._send_internal("test_method", wait_result=True)

    assert result is None


@pytest.mark.asyncio
async def test_send_retries_on_failure(monkeypatch):
    """send() должен повторять попытки и возвращать None при исчерпании."""
    gtw = ProGateway("1.2.3.4", retries=2)

    attempt_count = [0]

    async def fake_send_internal(*_args, **_kwargs):
        attempt_count[0] += 1
        return None  # Always fail

    async def fake_sleep(_delay):
        pass  # Skip actual sleep in tests

    monkeypatch.setattr(gtw, "_send_internal", fake_send_internal)
    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
        fake_sleep,
    )

    result = await gtw.send("gateway_set.prop", nodes=[{"id": 1}])

    assert result is None
    assert attempt_count[0] == 2  # retries=2 → 2 attempts total
    assert gtw.stats.commands_failed == 1


# ---------- run_forever ----------


@pytest.mark.asyncio
async def test_run_forever_retries_with_exponential_backoff(monkeypatch):
    """
    run_forever:
    - при первых connect() получаем False → делается sleep с exponential backoff;
    - при успешном connect() вызывается _read_loop();
    - _read_loop бросает CancelledError → выходим из цикла.
    """
    gtw = ProGateway("1.2.3.4")

    connect_calls = []
    sleep_calls = []

    async def fake_connect(self):
        connect_calls.append("call")
        # первые 3 вызова -> False, четвертый -> True
        return len(connect_calls) > 3

    async def fake_read_loop(self):
        # сразу прерываем цикл
        raise asyncio.CancelledError()

    async def fake_backoff_sleep(self, delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
    monkeypatch.setattr(ProGateway, "_read_loop", fake_read_loop, raising=True)
    monkeypatch.setattr(ProGateway, "_backoff_sleep", fake_backoff_sleep, raising=True)

    await gtw.run_forever()

    # Было 4 попытки connect()
    assert len(connect_calls) == 4
    # Exponential backoff: 1.0, 2.0, 4.0
    assert sleep_calls == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_run_forever_resets_backoff_on_success(monkeypatch):
    """После успешного connect() backoff сбрасывается."""
    gtw = ProGateway("1.2.3.4")
    gtw._reconnect_delay = 16.0  # simulate previous failures

    connect_calls = []

    async def fake_connect(self):
        connect_calls.append("call")
        return True

    async def fake_read_loop(self):
        # Check that backoff was reset
        assert self._reconnect_delay == MIN_RECONNECT_DELAY
        raise asyncio.CancelledError()

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
    monkeypatch.setattr(ProGateway, "_read_loop", fake_read_loop, raising=True)

    await gtw.run_forever()

    assert len(connect_calls) == 1


@pytest.mark.asyncio
async def test_run_forever_waits_before_reconnect_after_disconnect(monkeypatch):
    """После разрыва активного соединения применяется reconnect delay."""
    gtw = ProGateway("1.2.3.4")
    sleep_calls = []

    async def fake_connect(self):
        self.writer = DummyWriter()
        return True

    async def fake_read_loop(self):
        self.writer = None  # emulate disconnected socket

    async def fake_backoff_sleep(self, delay):
        sleep_calls.append(delay)
        gtw._stopping = True

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
    monkeypatch.setattr(ProGateway, "_read_loop", fake_read_loop, raising=True)
    monkeypatch.setattr(ProGateway, "_backoff_sleep", fake_backoff_sleep, raising=True)

    await gtw.run_forever()

    assert sleep_calls == [MIN_RECONNECT_DELAY]


@pytest.mark.asyncio
async def test_read_loop_handles_connection_closed():
    """_read_loop должен корректно обрабатывать закрытие соединения."""
    gtw = ProGateway("1.2.3.4")

    class FakeReader:
        def __init__(self):
            self.call_count = 0

        async def read(self, _size):
            self.call_count += 1
            if self.call_count == 1:
                return b'{"id": 1}\r\n'
            # Simulate connection closed
            return b""

    class FakeWriter:
        def close(self):
            pass

        async def wait_closed(self):
            pass

    gtw.reader = FakeReader()
    gtw.writer = FakeWriter()

    await gtw._read_loop()

    assert gtw.writer is None
    assert gtw.reader is None


@pytest.mark.asyncio
async def test_read_loop_handles_partial_reads_and_multiple_messages(monkeypatch):
    """_read_loop собирает partial chunks и парсит несколько сообщений подряд."""
    gtw = ProGateway("1.2.3.4")
    received = []

    class FakeReader:
        def __init__(self):
            self.chunks = [
                b'{"id": 1',
                b'}\r\n{"id": 2}\r',
                b"\n",
                b"",
            ]

        async def read(self, _size):
            return self.chunks.pop(0)

    class FakeWriter:
        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def fake_on_message(msg):
        received.append(msg)

    monkeypatch.setattr(gtw, "on_message", fake_on_message)

    gtw.reader = FakeReader()
    gtw.writer = FakeWriter()

    await gtw._read_loop()

    assert received == [b'{"id": 1}', b'{"id": 2}']


@pytest.mark.asyncio
async def test_read_loop_handles_connection_error():
    """_read_loop должен корректно обрабатывать ошибки соединения."""
    gtw = ProGateway("1.2.3.4")

    class FakeReader:
        async def read(self, _size):
            raise ConnectionError("Connection lost")

    class FakeWriter:
        def close(self):
            pass

        async def wait_closed(self):
            pass

    gtw.reader = FakeReader()
    gtw.writer = FakeWriter()

    await gtw._read_loop()

    assert gtw.writer is None
    assert gtw.reader is None


# ---------- JSON error counter ----------


@pytest.mark.asyncio
async def test_json_error_counter_resets_on_success():
    """Счётчик JSON ошибок сбрасывается при успешном парсинге."""
    gtw = ProGateway("1.2.3.4")
    gtw._json_error_count = 3

    # Valid JSON message
    await gtw.on_message(b'{"id": 1, "method": "test"}')

    assert gtw._json_error_count == 0


@pytest.mark.asyncio
async def test_json_error_counter_increments_on_error():
    """Счётчик JSON ошибок увеличивается при ошибке."""
    gtw = ProGateway("1.2.3.4")
    gtw._json_error_count = 0

    # Invalid JSON
    await gtw.on_message(b'not valid json {')

    assert gtw._json_error_count == 1


@pytest.mark.asyncio
async def test_json_error_triggers_reconnect_after_max():
    """После MAX_JSON_ERRORS ошибок соединение закрывается."""
    gtw = ProGateway("1.2.3.4")
    gtw._json_error_count = MAX_JSON_ERRORS - 1

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    gtw.writer = FakeWriter()

    # This should trigger reconnect
    await gtw.on_message(b'invalid json')

    assert gtw._json_error_count == MAX_JSON_ERRORS
    assert gtw.writer is None  # Connection closed


# ---------- Keepalive ----------


@pytest.mark.asyncio
async def test_keepalive_loop_stops_on_stopping_flag(monkeypatch):
    """Keepalive останавливается при _stopping=True."""
    gtw = ProGateway("1.2.3.4", keepalive=0.1)
    gtw.writer = DummyWriter()

    sleep_count = [0]

    async def fake_sleep(delay):
        sleep_count[0] += 1
        gtw._stopping = True  # Stop after first sleep

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
        fake_sleep,
    )

    await gtw._keepalive_loop()

    assert sleep_count[0] == 1


@pytest.mark.asyncio
async def test_keepalive_closes_connection_on_failure(monkeypatch):
    """Keepalive закрывает соединение при неудаче."""
    gtw = ProGateway("1.2.3.4", keepalive=0.01)

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    gtw.writer = FakeWriter()

    async def fake_sleep(_delay):
        return

    async def fake_send_internal(*_args, **_kwargs):
        return None  # Simulate failure

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
        fake_sleep,
    )
    monkeypatch.setattr(gtw, "_send_internal", fake_send_internal)

    await gtw._keepalive_loop()

    assert gtw.writer is None


@pytest.mark.asyncio
async def test_keepalive_requires_consecutive_failures(monkeypatch):
    """Keepalive закрывает соединение только после порога подряд идущих фейлов."""
    gtw = ProGateway("1.2.3.4", keepalive=0.01)
    gtw.writer = DummyWriter()

    attempts = {"count": 0}

    async def fake_sleep(_delay):
        return

    async def fake_send_internal(*_args, **_kwargs):
        attempts["count"] += 1
        return None

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
        fake_sleep,
    )
    monkeypatch.setattr(gtw, "_send_internal", fake_send_internal)

    await gtw._keepalive_loop()

    assert attempts["count"] == KEEPALIVE_FAILURE_THRESHOLD
    assert gtw.writer is None


# ---------- Topology device tracking ----------


@pytest.mark.asyncio
async def test_topology_tracks_devices():
    """Топология отслеживает устройства."""
    gtw = ProGateway("1.2.3.4")
    gtw.device = GatewayDevice(gtw)
    gtw.devices[gtw.device.id] = gtw.device

    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 100, "nt": 2, "type": 1},
            {"id": 200, "nt": 2, "type": 2},
        ],
    }

    await gtw.on_message(json.dumps(topo).encode())

    assert gtw._last_topology_devices == {100, 200}


@pytest.mark.asyncio
async def test_topology_detects_removed_devices():
    """Топология обнаруживает удалённые устройства."""
    gtw = ProGateway("1.2.3.4")
    gtw.device = GatewayDevice(gtw)
    gtw.devices[gtw.device.id] = gtw.device

    # Create a device that will be "removed"
    device = XDevice({"id": 100, "nt": 2, "type": 1, "n": "Test"})
    device.prop = {"o": True}
    gtw.devices[100] = device
    gtw._last_topology_devices = {100, 200}

    # New topology without device 100
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 200, "nt": 2, "type": 2},
        ],
    }

    await gtw.on_message(json.dumps(topo).encode())

    # Device 100 should be marked offline
    assert device.prop.get("o") is False


@pytest.mark.asyncio
async def test_on_message_ignores_cancelled_waiter():
    """Поздний ответ на отменённый future не должен ронять обработчик сообщений."""
    gtw = ProGateway("1.2.3.4")
    fut = asyncio.get_running_loop().create_future()
    fut.cancel()
    gtw._msgs[42] = fut

    await gtw.on_message(b'{"id": 42}')

    assert 42 not in gtw._msgs


@pytest.mark.asyncio
async def test_send_topology_joins_inflight_request():
    """Повторный topology wait_result ждёт текущий future и не шлёт второй пакет."""
    gtw = ProGateway("1.2.3.4")
    gtw.writer = DummyWriter()

    task1 = asyncio.create_task(gtw.send("gateway_get.topology", wait_result=True))
    await asyncio.sleep(0)
    task2 = asyncio.create_task(gtw.send("gateway_get.topology", wait_result=True))
    await asyncio.sleep(0)

    await gtw.on_message(b'{"id": "gateway_post.topology", "ok": true}')

    result1 = await task1
    result2 = await task2

    assert result1 == {"id": "gateway_post.topology", "ok": True}
    assert result2 == {"id": "gateway_post.topology", "ok": True}
    assert len(gtw.writer.written) == 1
    assert "gateway_post.topology" not in gtw._msgs



# ---------- Critical: _send_lock released during _close_connection ----------


@pytest.mark.asyncio
async def test_send_internal_releases_send_lock_before_close_connection():
    """_send_lock должен быть освобождён до вызова _close_connection при ошибке записи."""
    gtw = ProGateway("1.2.3.4")
    lock_held_during_close = []

    class BrokenWriter:
        def write(self, data):
            pass

        async def drain(self):
            raise ConnectionError("broken pipe")

        def close(self):
            pass

        async def wait_closed(self):
            # Snapshot lock state at the moment connection is being closed
            lock_held_during_close.append(gtw._send_lock.locked())

        def is_closing(self):
            return False

    gtw.writer = BrokenWriter()  # type: ignore[assignment]
    await gtw._send_internal("gateway_set.prop", wait_result=False)

    assert lock_held_during_close == [False], (
        "_send_lock should be released before _close_connection is awaited"
    )


# ---------- Important: reconnect delay must check _stopping after sleep ----------


@pytest.mark.asyncio
async def test_run_forever_does_not_advance_backoff_if_stopping_during_sleep(monkeypatch):
    """После остановки во время reconnect sleep backoff-задержка не должна вырасти."""
    gtw = ProGateway("1.2.3.4")

    async def fake_connect(self):
        self.writer = DummyWriter()
        return True

    async def fake_read_loop(self):
        self.writer = None  # simulate unclean disconnect

    async def fake_backoff_sleep(self, delay):
        gtw._stopping = True  # stop() called while sleeping

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
    monkeypatch.setattr(ProGateway, "_read_loop", fake_read_loop, raising=True)
    monkeypatch.setattr(ProGateway, "_backoff_sleep", fake_backoff_sleep, raising=True)

    await gtw.run_forever()

    from custom_components.yeelight_pro.core.gateway import MIN_RECONNECT_DELAY
    assert gtw._reconnect_delay == MIN_RECONNECT_DELAY, (
        "backoff should not be advanced when stopping during reconnect sleep"
    )


# ---------- Important: _resolve_waiter must remove entry from _msgs ----------


@pytest.mark.asyncio
async def test_resolve_waiter_removes_entry_from_msgs_on_success():
    """_resolve_waiter должен удалять запись из _msgs сразу после resolve."""
    gtw = ProGateway("1.2.3.4")
    fut = asyncio.get_running_loop().create_future()
    gtw._msgs[42] = fut

    resolved = gtw._resolve_waiter(42, {"id": 42, "ok": True})

    assert resolved is True
    assert 42 not in gtw._msgs, "_msgs should be cleared after successful resolve"
    assert fut.result() == {"id": 42, "ok": True}


# ---------- Minor: keepalive failure counter resets on success ----------


@pytest.mark.asyncio
async def test_keepalive_resets_failure_count_on_success(monkeypatch):
    """Провал-успех-провал: счётчик фейлов сбрасывается, реконнект не триггерится."""
    gtw = ProGateway("1.2.3.4")
    gtw.writer = DummyWriter()

    close_calls = {"count": 0}
    original_close = ProGateway._close_connection

    async def tracking_close(self):
        close_calls["count"] += 1
        await original_close(self)

    monkeypatch.setattr(ProGateway, "_close_connection", tracking_close, raising=True)

    # fail, success, fail → 1 consecutive at end, below threshold (2) → no reconnect
    call_idx = {"n": 0}
    responses = [None, {"ok": True}, None]

    async def fake_sleep(_delay):
        if call_idx["n"] >= len(responses):
            gtw._stopping = True  # stop after sequence exhausted

    async def fake_send_internal(*_args, **_kwargs):
        n = call_idx["n"]
        call_idx["n"] += 1
        return responses[n] if n < len(responses) else {"ok": True}

    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.sleep",
        fake_sleep,
    )
    monkeypatch.setattr(gtw, "_send_internal", fake_send_internal)

    await gtw._keepalive_loop()

    assert call_idx["n"] >= 3
    assert close_calls["count"] == 0, "reconnect should not fire on non-consecutive failures"


# ---------- Group capabilities derived from members ----------


@pytest.mark.asyncio
async def test_group_capabilities_derived_from_members():
    """A group of on/off-only lights must not grow brightness/CT converters."""
    gtw = get_gateway()
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 100, "nt": 4, "n": "Group", "type": 0, "cids": [1, 2]},
            {"id": 1, "nt": 2, "n": "L1", "type": 1},  # DeviceType.LIGHT = 1: on/off only
            {"id": 2, "nt": 2, "n": "L2", "type": 1},
        ],
    }
    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    group = gtw.devices[100]
    assert "light" in group.converters
    assert "color_temp" not in group.converters
    assert "brightness" not in group.converters


@pytest.mark.asyncio
async def test_group_falls_back_to_defaults_when_member_unknown():
    gtw = get_gateway()
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 100, "nt": 4, "n": "Group", "type": 0, "cids": [1, 999]},
            {"id": 1, "nt": 2, "n": "L1", "type": 1},
            # member 999 never appears
        ],
    }
    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    group = gtw.devices[100]
    # Unknown member -> broad default (historical behavior), CT stays available
    assert "color_temp" in group.converters


@pytest.mark.asyncio
async def test_group_all_rgb_exposes_rgb():
    """An all-RGB group must expose RGB (the other half of the bug)."""
    gtw = get_gateway()
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 100, "nt": 4, "n": "Group", "type": 0, "cids": [1, 2]},
            {"id": 1, "nt": 2, "n": "L1", "type": 4},  # LIGHT_WITH_COLOR = 4: RGB + CT + brightness
            {"id": 2, "nt": 2, "n": "L2", "type": 4},
        ],
    }
    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    group = gtw.devices[100]
    assert "rgb_color" in group.converters
    assert "color_temp" in group.converters
    assert "brightness" in group.converters


@pytest.mark.asyncio
async def test_group_finalize_is_idempotent_and_freezes_once_entities_exist():
    """A second topology pass must not recreate the group nor shrink its converters."""
    gtw = get_gateway()
    topo = {
        "method": "gateway_post.topology",
        "nodes": [
            {"id": 100, "nt": 4, "n": "Group", "type": 0, "cids": [1, 2]},
            {"id": 1, "nt": 2, "n": "L1", "type": 4},
            {"id": 2, "nt": 2, "n": "L2", "type": 4},
        ],
    }
    await gtw.on_message(json.dumps(topo).encode("utf-8"))
    group = gtw.devices[100]
    first_keys = set(group.converters)

    # GatewayForTests never creates real entities, so simulate one to prove the
    # freeze guard: once entities exist, neither a second topology pass nor a
    # direct setup_converters() call may rebuild/shrink the live converter set.
    sentinel = object()
    group.entities["light"] = sentinel

    await gtw.on_message(json.dumps(topo).encode("utf-8"))

    assert gtw.devices[100] is group  # same instance, not recreated
    assert set(group.converters) == first_keys  # converters unchanged
    assert group.entities["light"] is sentinel  # existing entity preserved

    # Direct guard check (Fix 1): setup_converters is a no-op when entities exist.
    before = dict(group.converters)
    group.setup_converters()
    assert group.converters == before


@pytest.mark.asyncio
async def test_message_ids_are_monotonic():
    """Non-topology sends use consecutive, unique correlation ids."""
    gtw = get_gateway()

    written = []

    class RecordingWriter:
        def write(self, data):
            written.append(data)

        async def drain(self):
            return

        def is_closing(self):
            return False

        def close(self):
            return

        async def wait_closed(self):
            return

    gtw.writer = RecordingWriter()

    for _ in range(3):
        await gtw._send_internal("gateway_set.prop", wait_result=False, nodes=[])

    ids = [json.loads(m.split(MSG_SPLIT)[0])["id"] for m in written]
    assert ids == sorted(ids)
    assert len(set(ids)) == 3
    assert ids[1] == ids[0] + 1
    assert ids[2] == ids[1] + 1


# ---------- cancellation vs. lost reply ----------


@pytest.mark.asyncio
async def test_cancelled_send_is_not_retried():
    """Cancelling the caller must cancel the send, not look like a timeout.

    _send_internal used to turn CancelledError into None, so _send_with_retry
    resent the command and the cancel only landed after the whole retry chain.
    """
    gtw = ProGateway("1.2.3.4", timeout=5)
    gtw.writer = DummyWriter()

    task = asyncio.create_task(
        gtw.send("gateway_set.prop", nodes=[{"id": 1, "nt": 2, "set": {"p": True}}])
    )
    await asyncio.sleep(0)  # written; now waiting for the ack
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(gtw.writer.written) == 1
    assert gtw._msgs == {}


@pytest.mark.asyncio
async def test_send_returns_none_when_connection_drops_mid_wait():
    """A waiter cancelled by _close_connection is a lost reply, not a cancelled caller."""
    gtw = ProGateway("1.2.3.4", timeout=5)
    gtw.writer = DummyWriter()

    task = asyncio.create_task(gtw._send_internal("gateway_set.prop", nodes=[]))
    await asyncio.sleep(0)
    await gtw._close_connection()

    assert await task is None


# ---------- topology on every connect ----------


@pytest.mark.asyncio
async def test_first_connect_after_failed_start_requests_topology(monkeypatch):
    """Gateway offline when HA starts: the late first connect must still fetch topology.

    ready() used to be the only startup topology request and it gives up after
    `timeout`. The main loop then connected without asking, leaving a connected
    gateway with zero devices until a manual reload.
    """
    gtw = ProGateway("1.2.3.4")
    requested = []

    async def fake_topology(self, wait_result=False):
        requested.append(wait_result)

    async def fake_open_connection(host, port):
        return object(), DummyWriter()

    monkeypatch.setattr(ProGateway, "topology", fake_topology)
    monkeypatch.setattr(
        "custom_components.yeelight_pro.core.gateway.asyncio.open_connection",
        fake_open_connection,
    )

    assert await gtw.connect() is True
    await asyncio.sleep(0)  # let the background reconcile task run

    assert requested == [True]
    assert gtw.stats.reconnect_count == 0  # a first connect is not a reconnect


@pytest.mark.asyncio
async def test_ready_only_waits_for_connection(monkeypatch):
    """Topology now comes from every connect; ready() must not ask a second time."""
    gtw = ProGateway("1.2.3.4")
    calls = []

    async def fake_topology(self, wait_result=False):
        calls.append(wait_result)

    monkeypatch.setattr(ProGateway, "topology", fake_topology)
    gtw.writer = DummyWriter()  # already connected

    assert await gtw.ready() is True
    assert calls == []


# ---------- connection ownership ----------


@pytest.mark.asyncio
async def test_send_while_disconnected_wakes_main_loop_instead_of_connecting(monkeypatch):
    """A command during reconnect backoff must not wait out the backoff, and must
    not open a socket the read loop does not know about."""
    gtw = ProGateway("1.2.3.4", timeout=1)
    gtw._reconnect_delay = 10.0  # deep in backoff after an outage
    connects = []

    async def fake_connect(self):
        connects.append(True)
        if len(connects) == 1:
            return False  # still down: run_forever enters its backoff sleep
        self.writer = DummyWriter()
        self._connected.set()
        return True

    async def idle(self):
        await asyncio.sleep(3600)  # "connected" until cancelled

    monkeypatch.setattr(ProGateway, "connect", fake_connect, raising=True)
    monkeypatch.setattr(ProGateway, "_read_loop", idle, raising=True)
    monkeypatch.setattr(ProGateway, "_keepalive_loop", idle, raising=True)

    gtw.main_task = asyncio.create_task(gtw.run_forever())
    await asyncio.sleep(0)  # first connect failed; loop sleeps 10 s

    await asyncio.wait_for(
        gtw._send_internal("gateway_set.prop", wait_result=False, nodes=[]),
        2,  # far less than the 10 s backoff
    )

    assert len(connects) == 2  # the main loop reconnected, not the sender
    assert len(gtw.writer.written) == 1
    await gtw.stop()


@pytest.mark.asyncio
async def test_send_internal_never_opens_its_own_connection(monkeypatch):
    """Connecting is the main loop's job: only it starts a reader for the socket."""
    gtw = get_gateway()

    async def fail_connect(self):
        raise AssertionError("_send_internal must not connect")

    monkeypatch.setattr(type(gtw), "connect", fail_connect, raising=True)

    assert await gtw._send_internal("gateway_set.prop", wait_result=True, nodes=[]) is None


@pytest.mark.asyncio
async def test_connected_event_tracks_the_link():
    gtw = ProGateway("1.2.3.4")
    gtw.writer = DummyWriter()
    gtw._connected.set()

    await gtw._close_connection()

    assert not gtw._connected.is_set()


@pytest.mark.asyncio
async def test_send_from_main_task_does_not_wait_for_its_own_reconnect():
    """on_message runs inside main_task; a send from there must not wait for a
    reconnect that only main_task itself can make."""
    gtw = ProGateway("1.2.3.4", timeout=5)
    gtw.main_task = asyncio.current_task()
    gtw.writer = None

    result = await asyncio.wait_for(
        gtw._send_internal("gateway_get.node", wait_result=False, nodes=[]),
        0.5,
    )

    assert result is None


# ---------- retry superseding ----------


@pytest.mark.asyncio
async def test_retry_is_dropped_once_a_newer_command_targets_the_same_node(monkeypatch):
    """Wire order ON -> OFF -> ON-retry left the light on after the user turned it off."""
    gtw = ProGateway("1.2.3.4")
    wire = []
    first = [True]

    async def fake_send_internal(method, wait_result=True, **kwargs):
        wire.append("ON" if kwargs["nodes"][0]["set"]["p"] else "OFF")
        if first[0]:  # the ON's ack is lost
            first[0] = False
            await asyncio.sleep(0.05)
            return None
        return {"ok": True}

    monkeypatch.setattr(gtw, "_send_internal", fake_send_internal)
    monkeypatch.setattr("custom_components.yeelight_pro.core.gateway.RETRY_DELAY_BASE", 0.01)

    on = asyncio.create_task(
        gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": {"p": True}}])
    )
    await asyncio.sleep(0.01)
    await gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": {"p": False}}])

    assert await on is None
    assert wire == ["ON", "OFF"]
    assert gtw.stats.commands_failed == 0  # superseded is not failed


def _lossy_first_ack(wire):
    """Fake _send_internal recording each node's set; the first ack is lost."""
    first = [True]

    async def fake_send_internal(method, wait_result=True, **kwargs):
        wire.append(kwargs["nodes"][0]["set"])
        if first[0]:
            first[0] = False
            await asyncio.sleep(0.05)
            return None
        return {"ok": True}

    return fake_send_internal


@pytest.mark.asyncio
async def test_retry_survives_a_newer_command_on_another_channel(monkeypatch):
    """Channel 2 on a multi-channel switch must not drop channel 1's retry."""
    gtw = ProGateway("1.2.3.4")
    wire = []
    monkeypatch.setattr(gtw, "_send_internal", _lossy_first_ack(wire))
    monkeypatch.setattr("custom_components.yeelight_pro.core.gateway.RETRY_DELAY_BASE", 0.01)

    ch1 = asyncio.create_task(
        gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": {"1-p": True}}])
    )
    await asyncio.sleep(0.01)
    await gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": {"2-p": True}}])

    assert await ch1
    assert wire == [{"1-p": True}, {"2-p": True}, {"1-p": True}]


@pytest.mark.asyncio
async def test_retry_keeps_only_keys_not_superseded(monkeypatch):
    """Colour change then power change: the retry resends the colour only."""
    gtw = ProGateway("1.2.3.4")
    wire = []
    monkeypatch.setattr(gtw, "_send_internal", _lossy_first_ack(wire))
    monkeypatch.setattr("custom_components.yeelight_pro.core.gateway.RETRY_DELAY_BASE", 0.01)

    first_set = {"p": True, "c": 255}
    first = asyncio.create_task(
        gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": first_set}])
    )
    await asyncio.sleep(0.01)
    await gtw.send("gateway_set.prop", nodes=[{"id": 7, "nt": 2, "set": {"p": False}}])

    assert await first
    assert wire == [{"p": True, "c": 255}, {"p": False}, {"c": 255}]
    assert first_set == {"p": True, "c": 255}  # caller's dict untouched


# ---------- dead-link detection ----------


@pytest.mark.asyncio
async def test_link_with_no_traffic_back_is_dropped_after_two_silent_timeouts():
    """Half-open TCP: writes succeed, nothing comes back. Don't wait ~70 s for keepalive."""
    gtw = ProGateway("1.2.3.4", timeout=0.01)
    gtw.writer = DummyWriter()

    assert await gtw._send_internal("gateway_set.prop", nodes=[]) is None
    assert gtw.writer is not None  # one silent timeout can be a busy gateway

    assert await gtw._send_internal("gateway_set.prop", nodes=[]) is None
    assert gtw.writer is None


@pytest.mark.asyncio
async def test_any_inbound_message_resets_the_silent_timeout_count():
    gtw = ProGateway("1.2.3.4", timeout=0.01)
    gtw.writer = DummyWriter()

    await gtw._send_internal("gateway_set.prop", nodes=[])
    await gtw.on_message(b'{"method": "gateway_post.prop", "nodes": []}')
    await gtw._send_internal("gateway_set.prop", nodes=[])

    assert gtw.writer is not None


@pytest.mark.asyncio
async def test_overlapping_silent_requests_count_as_one_silent_window():
    gtw = ProGateway("1.2.3.4", timeout=0.01)
    gtw.writer = DummyWriter()

    await asyncio.gather(
        gtw._send_internal("gateway_set.prop", nodes=[]),
        gtw._send_internal("gateway_set.prop", nodes=[]),
    )

    assert gtw.writer is not None


@pytest.mark.asyncio
async def test_joined_topology_request_does_not_count_as_a_second_silent_timeout():
    gtw = ProGateway("1.2.3.4", timeout=0.01)
    gtw.writer = DummyWriter()

    await asyncio.gather(gtw.topology(wait_result=True), gtw.topology(wait_result=True))

    assert gtw.writer is not None
