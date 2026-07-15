from __future__ import annotations

import asyncio
import itertools
import logging
import random
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Coroutine, Dict, Set, Union, Optional, Any

from .const import PID_WIFI_PANEL, DOMAIN, DEFAULT_PORT
from .device import XDevice, GatewayDevice, WifiPanelDevice
from .converters.base import Converter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
MSG_SPLIT = b'\r\n'

# Reconnect backoff settings
MIN_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 60.0
RECONNECT_BACKOFF_FACTOR = 2.0

# Error thresholds
MAX_JSON_ERRORS = 5  # Reconnect after N consecutive JSON decode errors
KEEPALIVE_INTERVAL = 30  # Seconds between keepalive pings
KEEPALIVE_FAILURE_THRESHOLD = 2  # Reconnect after N consecutive failed keepalive pings

# Retry settings
DEFAULT_RETRIES = 3
RETRY_DELAY_BASE = 0.5  # Base delay between retries (exponential backoff)

# Topology cache settings
TOPOLOGY_CACHE_TTL = 300  # 5 minutes
READ_CHUNK_SIZE = 4096
READ_BUFFER_LIMIT = 1024 * 1024

@dataclass
class GatewayStatistics:
    """Gateway statistics for diagnostics."""
    start_time: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0
    commands_success: int = 0
    commands_failed: int = 0
    commands_retried: int = 0
    reconnect_count: int = 0
    keepalive_count: int = 0
    keepalive_success: int = 0
    keepalive_failed: int = 0
    state_mismatches: int = 0
    state_corrections: int = 0
    last_message_time: float = 0
    last_error: Optional[str] = None
    last_error_time: float = 0
    
    @property
    def uptime(self) -> float:
        """Return uptime in seconds."""
        return time.time() - self.start_time
    
    @property
    def success_rate(self) -> float:
        """Return command success rate as percentage."""
        total = self.commands_success + self.commands_failed
        return (self.commands_success / total * 100) if total > 0 else 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for diagnostics."""
        return {
            'uptime_seconds': round(self.uptime, 1),
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'commands_success': self.commands_success,
            'commands_failed': self.commands_failed,
            'commands_retried': self.commands_retried,
            'success_rate': round(self.success_rate, 1),
            'reconnect_count': self.reconnect_count,
            'keepalive_total': self.keepalive_count,
            'keepalive_success': self.keepalive_success,
            'keepalive_failed': self.keepalive_failed,
            'state_mismatches': self.state_mismatches,
            'state_corrections': self.state_corrections,
            'last_error': self.last_error,
            'last_error_time': self.last_error_time,
        }


class ProGateway:
    """Yeelight Pro Gateway TCP client."""
    
    host: str
    port: int = DEFAULT_PORT
    device: Optional[XDevice] = None

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    main_task: Optional[asyncio.Task] = None
    _keepalive_task: Optional[asyncio.Task] = None
    _stopping: bool  # initialised in __init__; class-level annotation only

    def __init__(self, host: str, **options: Any) -> None:
        self.host = host
        self.port = int(options.get('port', DEFAULT_PORT))
        self.pid: int = options.get('pid', 1)
        self.hass: Optional[HomeAssistant] = options.get('hass')
        self.config_entry = options.get('config_entry')
        self.timeout: float = options.get('timeout', 5)
        self.keepalive: float = options.get('keepalive', KEEPALIVE_INTERVAL)
        self.entry_id: Optional[str] = options.get('entry_id')
        self.devices: Dict[Union[str, int], XDevice] = {}
        self.setups: Dict[str, Callable] = {}
        self.log = options.get('logger', _LOGGER)
        self._msgs: Dict[Union[int, str], asyncio.Future] = {}
        # Monotonic correlation ids; random start avoids colliding with a
        # gateway that still remembers ids from a previous session.
        self._cid_counter = itertools.count(random.randint(1_000_000_000, 1_500_000_000))
        self._reconnect_delay: float = MIN_RECONNECT_DELAY
        self._stopping: bool = False
        self._json_error_count: int = 0
        self._last_topology_devices: Set[Union[str, int]] = set()
        self._was_connected: bool = False
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._background_tasks: Set[asyncio.Task] = set()
        
        # Statistics for diagnostics
        self.stats = GatewayStatistics()

        # Topology cache
        self._topology_cache: Optional[Dict] = None
        self._topology_cache_time: float = 0
        self._topology_cache_ttl: float = options.get('topology_cache_ttl', TOPOLOGY_CACHE_TTL)
        
        # Configurable transition time (default 5 seconds)
        self.transition_time: float = options.get('transition_time', 5.0)
        
        # Retry settings
        self._default_retries: int = options.get('retries', DEFAULT_RETRIES)

        self.log.debug('[%s] Gateway initialized, pid=%s', self.host, self.pid)

    def add_setup(self, domain: str, handler: Callable) -> None:
        """Add hass entity setup function."""
        if '.' in domain:
            _, domain = domain.rsplit('.', 1)
        self.setups[domain] = handler
        self.log.debug('[%s] Setup handler added: %s', self.host, domain)

    async def setup_entity(self, domain: str, device: XDevice, conv: Converter) -> None:
        """Setup a single entity for a device."""
        handler = self.setups.get(domain)
        if handler:
            handler(device, conv)
        else:
            self.log.warning('[%s] Setup handler not ready: domain=%s, device=%s', 
                           self.host, domain, device.id)

    async def add_device(self, device: XDevice) -> None:
        """Add a device to this gateway."""
        if not device.hass:
            device.hass = self.hass
        if device.id not in self.devices:
            self.devices[device.id] = device
            self.log.debug('[%s] Device added: id=%s, name=%s, type=%s',
                          self.host, device.id, device.name, device.type)
        if self not in device.gateways:
            device.gateways.append(self)

        # Don't setup device from second gateway
        if len(device.gateways) > 1:
            return
        await device.setup_entities()

    async def start(self) -> None:
        """Start the gateway connection."""
        if self.main_task and not self.main_task.done():
            self.log.debug('[%s] Gateway already running', self.host)
            return

        self._stopping = False
        self._reconnect_delay = MIN_RECONNECT_DELAY
        self._json_error_count = 0
        self.stats = GatewayStatistics()  # Reset statistics on start
        self._cancel_pending_messages(cancel_ready=True)
        self._msgs['ready'] = asyncio.get_running_loop().create_future()
        
        self.main_task = asyncio.create_task(self.run_forever())
        self.log.info('[%s] Gateway starting', self.host)
        await self.ready()

    async def ready(self) -> bool:
        """Wait for gateway to be ready and request topology."""
        if not self.writer:
            if not (fut := self._msgs.get('ready')):
                return False
            try:
                await asyncio.wait_for(fut, self.timeout)
            except asyncio.TimeoutError:
                self.log.warning('[%s] Gateway ready timeout', self.host)
                return False
            except asyncio.CancelledError:
                self.log.debug('[%s] Gateway ready future cancelled', self.host)
                return False

        await self.topology()
        return True

    async def stop(self, *args: Any) -> None:
        """Stop the gateway connection and cleanup. Idempotent - safe to call multiple times."""
        if self._stopping:
            return
        self._stopping = True
        self.log.info('[%s] Gateway stopping', self.host)
        
        # Cancel keepalive task
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        self._keepalive_task = None

        await self._cancel_background_tasks()

        for device in list(self.devices.values()):
            cancel_verify = getattr(device, "async_cancel_verify_task", None)
            if cancel_verify is not None:
                await cancel_verify()
        
        # Cancel all pending futures to avoid leaks
        self._cancel_pending_messages(cancel_ready=True)
        
        # Cancel main task
        if self.main_task and not self.main_task.done():
            self.main_task.cancel()
            try:
                await self.main_task
            except asyncio.CancelledError:
                pass
        self.main_task = None
        
        # Close connection
        await self._close_connection()
        
        # Remove gateway from devices
        for device in list(self.devices.values()):
            if self in device.gateways:
                device.gateways.remove(self)
        
        self.log.info('[%s] Gateway stopped', self.host)

    async def run_forever(self) -> None:
        """Main connection loop with exponential backoff."""
        while not self._stopping:
            try:
                if not await self.connect():
                    delay = self._reconnect_delay
                    self.log.debug('[%s] Reconnect in %.1f seconds', self.host, delay)
                    await asyncio.sleep(delay)
                    # Branch 1 backoff: failed to connect at all.
                    self._reconnect_delay = min(
                        self._reconnect_delay * RECONNECT_BACKOFF_FACTOR,
                        MAX_RECONNECT_DELAY
                    )
                    continue

                # Successful connect: reset backoff so the *first* post-disconnect
                # wait (Branch 2 below) always starts from MIN_RECONNECT_DELAY.
                self._reconnect_delay = MIN_RECONNECT_DELAY
                self._json_error_count = 0
                
                # Start keepalive task
                self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                
                # Read messages in loop until disconnect
                await self._read_loop()
                
                # Cancel keepalive on disconnect
                if self._keepalive_task and not self._keepalive_task.done():
                    self._keepalive_task.cancel()
                    try:
                        await self._keepalive_task
                    except asyncio.CancelledError:
                        pass

                # Branch 2 backoff: was connected, then lost the connection.
                # _reconnect_delay was reset to MIN on successful connect above,
                # so the first wait here is always the minimum delay.
                if not self._stopping and not self.writer:
                    delay = self._reconnect_delay
                    self.log.debug(
                        '[%s] Reconnect in %.1f seconds after disconnect',
                        self.host,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    # Re-check after sleep: stop() may have been called during the wait.
                    # Without this guard, the backoff would advance even on clean shutdown.
                    if self._stopping:
                        break
                    self._reconnect_delay = min(
                        self._reconnect_delay * RECONNECT_BACKOFF_FACTOR,
                        MAX_RECONNECT_DELAY,
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log.error('[%s] Main loop error: %s', self.host, exc, exc_info=exc)
        self.log.debug('[%s] Main loop stopped', self.host)

    async def connect(self) -> bool:
        """Establish connection to gateway."""
        try:
            res = await asyncio.wait_for(self._connect(), self.timeout)
        except asyncio.TimeoutError:
            self.log.error('[%s] Connection timeout', self.host)
            res = False
        except (ConnectionError, OSError) as exc:
            self.log.error('[%s] Connection error: %s', self.host, exc)
            res = False
        except Exception as exc:
            self.log.error('[%s] Unexpected connection error: %s', self.host, exc, exc_info=exc)
            res = False
        return res

    async def _connect(self) -> bool:
        """Internal connect implementation."""
        async with self._connect_lock:
            if self._writer_alive():
                return True

            self.log.debug('[%s] Connecting to port %d', self.host, self.port)
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            if not self.writer:
                return False

            self.log.info('[%s] Connected successfully', self.host)

            if fut := self._msgs.pop('ready', None):
                if not fut.done():
                    fut.set_result(True)

            self._update_connection_state(True)
            if self._was_connected:
                self.stats.reconnect_count += 1
                self._send_reconnect_notification()
                self._track_background_task(self._create_task(self._reconcile_state()))
            self._was_connected = True
        return True

    async def check_available(self) -> Optional[Exception]:
        """Check if gateway is reachable."""
        writer: Optional[asyncio.StreamWriter] = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                self.timeout,
            )
        except Exception as exc:
            self.log.error('[%s] Availability check failed: %s', self.host, exc)
            return exc
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
        return None
    
    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive pings to detect dead connections."""
        failures = 0
        method = 'device_get.node' if self.pid == PID_WIFI_PANEL else 'gateway_get.node'

        while not self._stopping and self.writer:
            try:
                await asyncio.sleep(self.keepalive)
                if self._stopping or not self.writer:
                    break
                # Send a lightweight node request as keepalive.
                result = await self._send_internal(method, params={'id': 0}, wait_result=True)
                self.stats.keepalive_count += 1
                if result is None:
                    failures += 1
                    self.stats.keepalive_failed += 1
                    self.log.warning(
                        '[%s] Keepalive failed (%d consecutive, %d/%d total)',
                        self.host,
                        failures,
                        self.stats.keepalive_failed,
                        self.stats.keepalive_count,
                    )
                    if failures >= KEEPALIVE_FAILURE_THRESHOLD:
                        await self._close_connection()
                        break
                    continue

                failures = 0
                self.stats.keepalive_success += 1
                # Log keepalive success only every 10th check to reduce noise
                if self.stats.keepalive_count % 10 == 0:
                    self.log.debug('[%s] Keepalive: %d/%d checks OK', 
                                  self.host, self.stats.keepalive_success, self.stats.keepalive_count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.log.debug('[%s] Keepalive error: %s', self.host, exc)
                await self._close_connection()
                break
    
    async def _reconcile_state(self) -> None:
        """Reconcile device states after reconnection.

        Requests fresh topology which triggers prop_changed → update → async_write_ha_state
        for all devices automatically.
        """
        self.log.info('[%s] Reconciling device states after reconnect', self.host)
        try:
            self.invalidate_topology_cache()
            await self.topology(wait_result=True)
            self.log.info('[%s] State reconciliation complete, %d devices', self.host, len(self.devices))
        except Exception as exc:
            self.log.warning('[%s] State reconciliation failed: %s', self.host, exc)
    
    async def _send_with_retry(self, method: str, retries: int = DEFAULT_RETRIES, **kwargs: Any) -> Optional[Dict]:
        """Send command with retry logic."""
        last_error = None
        # Fire-and-forget: a None return from _send_internal is normal - don't
        # treat it as failure and don't retry.
        wait_result = kwargs.get('wait_result', True)

        for attempt in range(retries):
            try:
                result = await self._send_internal(method, **kwargs)
                if result is not None:
                    self.stats.commands_success += 1
                    return result
                if not wait_result:
                    self.stats.commands_success += 1
                    return None

                # None result with wait_result=True indicates a real failure
                # (timeout, connection issue, etc.) - retry.
                if attempt < retries - 1:
                    self.stats.commands_retried += 1
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    self.log.debug('[%s] Command %s returned None, retry %d/%d in %.1fs',
                                  self.host, method, attempt + 1, retries, delay)
                    await asyncio.sleep(delay)
            except (ConnectionError, BrokenPipeError, OSError) as exc:
                last_error = exc
                if attempt < retries - 1:
                    self.stats.commands_retried += 1
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    self.log.debug('[%s] Command %s failed with %s, retry %d/%d in %.1fs', 
                                  self.host, method, type(exc).__name__, attempt + 1, retries, delay)
                    await asyncio.sleep(delay)
            except Exception as exc:
                last_error = exc
                self.log.error('[%s] Command %s unexpected error: %s', self.host, method, exc)
                break
        
        # All retries failed
        self.stats.commands_failed += 1
        self.stats.last_error = str(last_error) if last_error else 'Command returned None'
        self.stats.last_error_time = time.time()
        self.log.warning('[%s] Command %s failed after %d attempts: %s', 
                        self.host, method, retries, last_error)
        return None

    async def _read_loop(self) -> None:
        """Read messages continuously until disconnect."""
        if not self.reader:
            return

        buffer = b""
        while not self._stopping:
            try:
                chunk = await self.reader.read(READ_CHUNK_SIZE)
                if not chunk:
                    if buffer:
                        self.log.debug(
                            '[%s] Dropping %d bytes of unfinished payload on disconnect',
                            self.host,
                            len(buffer),
                        )
                    self.log.warning('[%s] Connection closed by gateway', self.host)
                    break

                buffer += chunk
                if len(buffer) > READ_BUFFER_LIMIT:
                    self.log.warning(
                        '[%s] Read buffer exceeded limit (%d), forcing reconnect',
                        self.host,
                        READ_BUFFER_LIMIT,
                    )
                    break

                while MSG_SPLIT in buffer:
                    msg, buffer = buffer.split(MSG_SPLIT, 1)
                    if msg:
                        await self.on_message(msg)
            except asyncio.CancelledError:
                raise
            except (ConnectionError, BrokenPipeError, OSError) as exc:
                self.log.error('[%s] Read error: %s', self.host, exc)
                break
            except Exception as exc:
                self.log.error('[%s] Unexpected read error: %s', self.host, exc, exc_info=exc)
                break
        
        await self._close_connection()
    
    async def _close_connection(self) -> None:
        """Close the current connection."""
        async with self._connect_lock:
            writer = self.writer
            self.writer = None
            self.reader = None

        if writer:
            self.log.debug('[%s] Closing connection', self.host)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self._update_connection_state(False)

        self._cancel_pending_messages(cancel_ready=False)

    async def on_message(self, msg: bytes) -> None:
        """Handle incoming message from gateway."""
        try:
            dat = json.loads(msg.decode()) or {}
            # Reset error count on successful parse
            self._json_error_count = 0
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json_error_count += 1
            self.log.error('[%s] JSON decode error (%d/%d): %s; raw=%r', 
                          self.host, self._json_error_count, MAX_JSON_ERRORS, exc, msg[:200])
            if self._json_error_count >= MAX_JSON_ERRORS:
                self.log.error('[%s] Too many JSON errors, forcing reconnect', self.host)
                await self._close_connection()
            return

        cmd = dat.get("method")
        cid = cmd if cmd in ("gateway_post.topology", "device_post.topology") else dat.get("id")
        nodes = dat.get("nodes") or []
        is_topology = cmd in ("gateway_post.topology", "device_post.topology")

        self.stats.messages_received += 1
        self.stats.last_message_time = time.time()
        
        if cid is not None and self._resolve_waiter(cid, dat):
            pass
        elif cmd:
            self.log.debug('[%s] Message: method=%s, nodes=%d', self.host, cmd, len(nodes))

        if is_topology and not self.device:
            if self.pid == PID_WIFI_PANEL and nodes:
                self.device = WifiPanelDevice(nodes[0])
            else:
                self.device = GatewayDevice(self)
            self.log.debug('[%s] Gateway device created: type=%s', self.host, type(self.device).__name__)
            await self.add_device(self.device)

        if not nodes and "params" in dat:
            nodes = [dat["params"]]

        # Track devices in topology for stale device detection
        if is_topology:
            self.log.debug('[%s] Topology update: %d nodes', self.host, len(nodes))
            current_topology_devices: Set[Union[str, int]] = set()
            for node in nodes:
                nid = node.get("id")
                if nid is not None:
                    current_topology_devices.add(nid)
            
            # Detect removed devices (P1.5)
            if self._last_topology_devices:
                removed = self._last_topology_devices - current_topology_devices
                for removed_id in removed:
                    if removed_id in self.devices and removed_id != self.device.id:
                        self.log.warning('[%s] Device disappeared from topology: %s', 
                                        self.host, removed_id)
                        # Mark device as unavailable (don't remove to preserve entity_id)
                        device = self.devices[removed_id]
                        device.prop['o'] = False  # Mark offline
                        device.update({'available': False})
            
            self._last_topology_devices = current_topology_devices

        for node in nodes:
            nid = node.get("id")
            if nid is None:
                continue
            if is_topology:
                dvc = await XDevice.from_node(self, node)
            else:
                dvc = None

            if not dvc:
                dvc = self.device if nid == 0 else self.devices.get(nid)
            if not dvc:
                self.log.debug('[%s] Device not found for node: %s', self.host, nid)
                continue

            if cmd in ("gateway_post.prop", "device_post.prop"):
                await dvc.prop_changed(node)
            elif cmd in ("gateway_post.event", "device_post.event"):
                await dvc.event_fired(node)

    async def send(self, method: str, wait_result: bool = True, **kwargs: Any) -> Optional[Dict]:
        """Send a command to the gateway with retry."""
        # For topology and internal queries, send directly without retry
        if method in (
            "gateway_get.topology",
            "device_get.topology",
            "gateway_get.node",
            "device_get.node",
        ):
            return await self._send_internal(method, wait_result=wait_result, **kwargs)

        return await self._send_with_retry(method, self._default_retries, wait_result=wait_result, **kwargs)

    async def _send_internal(self, method: str, wait_result: bool = True, **kwargs: Any) -> Optional[Dict]:
        """Internal send implementation without queue or retry."""
        fut: Optional[asyncio.Future] = None
        own_waiter = False
        should_send = True
        _close_after = False  # set inside lock, acted on after lock is released
        cid: Union[str, int]

        # Guard reserved wire-protocol keys. Caller bugs that pass `id` or
        # `method` via kwargs would otherwise silently overwrite cid/method
        # because of dict-merge precedence below.
        for reserved in ('id', 'method'):
            if reserved in kwargs:
                raise TypeError(
                    f"_send_internal got reserved kwarg {reserved!r}; "
                    f"pass via the appropriate parameter instead"
                )

        # Connect outside the send lock: connect() can block up to `timeout`
        # seconds and must not serialize unrelated senders behind it.
        # connect() is internally guarded by _connect_lock.
        if not self.writer:
            if not await self.connect():
                self.log.warning('[%s] Cannot send %s: not connected', self.host, method)
                return None

        async with self._send_lock:
            if not self.writer:
                # Connection died between the check above and acquiring the lock.
                self.log.warning('[%s] Cannot send %s: connection lost', self.host, method)
                return None

            if method in ("gateway_get.topology", "device_get.topology"):
                cid = method.replace("_get.", "_post.")
            else:
                # Mask to signed 32-bit range: the gateway firmware parses `id`
                # as an int32, so keep ids within the bound the original code used.
                cid = next(self._cid_counter) & 0x7FFF_FFFF

            if wait_result:
                existing = self._msgs.get(cid)
                if isinstance(cid, str) and existing and not existing.done():
                    fut = existing
                    should_send = False
                else:
                    fut = asyncio.get_running_loop().create_future()
                    self._msgs[cid] = fut
                    own_waiter = True

            if should_send:
                dat = {
                    'id': cid,
                    'method': method,
                    **kwargs,
                }
                self.log.debug('[%s] Send: %s id=%s', self.host, method, cid)

                try:
                    self.writer.write(json.dumps(dat).encode() + MSG_SPLIT)
                    await self.writer.drain()
                    self.stats.messages_sent += 1
                except Exception as exc:
                    self.log.error('[%s] Send error for %s: %s', self.host, method, exc)
                    if own_waiter:
                        self._msgs.pop(cid, None)
                    if fut and not fut.done():
                        fut.cancel()
                    # Do NOT await _close_connection() here - it acquires _connect_lock
                    # which would be held under _send_lock, risking a lock-ordering issue.
                    _close_after = True
            else:
                self.log.debug(
                    '[%s] Join in-flight request: %s id=%s',
                    self.host,
                    method,
                    cid,
                )

        # _send_lock is released - safe to close the connection now.
        if _close_after:
            await self._close_connection()
            return None

        if not fut:
            return None

        try:
            result = await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            self.log.debug('[%s] Timeout waiting for %s', self.host, method)
            if own_waiter and not fut.done():
                fut.cancel()
            return None
        except asyncio.CancelledError:
            return None
        finally:
            if own_waiter:
                self._msgs.pop(cid, None)

        return result

    async def topology(self, wait_result: bool = False, use_cache: bool = True) -> Optional[Dict]:
        """Request topology from gateway with optional caching."""
        # Check cache first
        if use_cache and self._topology_cache:
            cache_age = time.time() - self._topology_cache_time
            if cache_age < self._topology_cache_ttl:
                self.log.debug('[%s] Using cached topology (age: %.1fs)', self.host, cache_age)
                return self._topology_cache
        
        cmd = 'device_get.topology' if self.pid == PID_WIFI_PANEL else 'gateway_get.topology'
        result = await self._send_internal(cmd, wait_result=wait_result)
        
        # Update cache on success
        if result:
            self._topology_cache = result
            self._topology_cache_time = time.time()
        
        return result
    
    def invalidate_topology_cache(self) -> None:
        """Invalidate the topology cache."""
        self._topology_cache = None
        self._topology_cache_time = 0

    async def get_node(self, nid: int = 0, wait_result: bool = True) -> Optional[Dict]:
        """Get node information."""
        cmd = 'device_get.node' if self.pid == PID_WIFI_PANEL else 'gateway_get.node'
        return await self.send(cmd, params={'id': nid}, wait_result=wait_result)

    async def get_room(self, rid: int = 0, wait_result: bool = True) -> Optional[Dict]:
        """Get room information."""
        return await self.send('gateway_get.room', params={'id': rid}, wait_result=wait_result)

    async def get_scene(self, rid: int = 0, wait_result: bool = True) -> Optional[list]:
        """Get scenes list."""
        res = await self.send('gateway_get.scene', params={'id': rid}, wait_result=wait_result)
        if res:
            return res.get('scenes', [])
        return None
    
    @property
    def is_connected(self) -> bool:
        """Return True if gateway is connected."""
        return self.writer is not None and not self._stopping
    
    @property
    def device_count(self) -> int:
        """Return number of devices."""
        return len(self.devices)
    
    @property
    def stopping(self) -> bool:
        """Return True if gateway is in the process of stopping."""
        return self._stopping

    @property
    def reconnect_delay(self) -> float:
        """Return current reconnect backoff delay."""
        return self._reconnect_delay

    @property
    def json_error_count(self) -> int:
        """Return consecutive JSON decode error count."""
        return self._json_error_count

    @property
    def pending_message_count(self) -> int:
        """Return number of pending command futures."""
        return len(self._msgs)

    @property
    def last_topology_device_ids(self) -> set:
        """Return device IDs from the last topology response."""
        return set(self._last_topology_devices)

    @property
    def diagnostics(self) -> Dict[str, Any]:
        """Return diagnostics data."""
        return {
            'host': self.host,
            'connected': self.is_connected,
            'device_count': self.device_count,
            'pid': self.pid,
            'transition_time': self.transition_time,
            'topology_cache_age': time.time() - self._topology_cache_time if self._topology_cache else None,
            **self.stats.to_dict(),
        }

    def _update_connection_state(self, connected: bool) -> None:
        """Update gateway device connection state."""
        if self.device:
            self.device.update({'connection': connected, 'available': connected})

    def _send_reconnect_notification(self) -> None:
        """Send persistent notification on reconnect."""
        if not self.hass:
            return
        try:
            from homeassistant.components import persistent_notification
            persistent_notification.async_create(
                self.hass,
                f"Gateway {self.host} reconnected (attempt #{self.stats.reconnect_count})",
                title="Yeelight Pro Reconnected",
                notification_id=f"{DOMAIN}-reconnect-{self.host}-{self.stats.reconnect_count}",
            )
        except Exception as exc:
            self.log.debug('[%s] Failed to send reconnect notification: %s', self.host, exc)

    def _create_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Create a background task bound to HA loop when available."""
        if self.hass:
            return self.hass.async_create_task(coro)
        return asyncio.create_task(coro)

    def _track_background_task(self, task: asyncio.Task) -> None:
        """Track a background task to guarantee cleanup on stop()."""
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _cancel_background_tasks(self) -> None:
        """Cancel tracked background tasks."""
        if not self._background_tasks:
            return

        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    def _writer_alive(self) -> bool:
        """Return True if writer is open and usable."""
        if not self.writer:
            return False
        is_closing = getattr(self.writer, "is_closing", None)
        if callable(is_closing):
            return not is_closing()
        return True

    def _cancel_pending_messages(self, cancel_ready: bool) -> None:
        """Cancel pending command futures and optionally ready future."""
        for cid, fut in list(self._msgs.items()):
            if cid == 'ready' and not cancel_ready:
                continue
            if not fut.done():
                fut.cancel()
            self._msgs.pop(cid, None)

    def _resolve_waiter(self, cid: Union[str, int], data: Dict[str, Any]) -> bool:
        """Resolve pending waiter if it exists and is still active.

        Always pops the entry from _msgs so callers do not need to clean up,
        including the join-in-flight path where own_waiter is False.
        """
        fut = self._msgs.pop(cid, None)
        if not fut:
            return False
        if fut.done():
            return False
        fut.set_result(data)
        return True
