# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Chore
- Added the MIT `LICENSE` file both READMEs already declared and linked to, clearing the only failing HACS validation check
- Bumped CI actions off the deprecated Node 20 runtime (`actions/checkout` v4 → v7, `actions/setup-python` v5 → v7, `codecov/codecov-action` v4 → v7, whose `file` input is now `files`)

## [1.4.1] - 2026-08-26

### Fixed
- Fixed the passive-verification retry chain never running past its first attempt. `hass.async_create_task` eager-starts the coroutine, so the verification task ran before `_verify_task` was assigned and could never recognise itself through `asyncio.current_task()`; ownership is now tracked with an explicit epoch counter. Symptoms in the log were a lone `retry 1/2` with no follow-up and a `_expected_state` that was never released
- Stopped reading gateway silence as command failure. `prop_params` is refreshed only by `gateway_post.prop`, so until the device reports back the cache still holds the pre-command snapshot; comparing against it did not measure the command at all, always "disagreed", and resent. Verification now requires an echo newer than the command before it will correct anything. This was firing hundreds of times a day, and every false correction put a duplicate `gateway_set.prop` on the mesh
- Cancelled a pending verification *before* the next command goes out instead of after. The old ordering left a window the length of the send (longer with retry backoff) in which a stale correction could fire and land after the new command, so the light received e.g. ON → OFF → ON and ended up obeying the previous intent — the user-visible "I pressed the switch and it did the opposite"
- Raised `STATE_VERIFY_TIMEOUT` from 2.5s to 8.0s. Measured `gateway_post.prop` echo latency on real hardware spans 0.97-4.34s (the gateway serialises mesh writes, so the second node of a two-node command waits behind the first), and the old 2.5s window sat inside that range
- Skipped the correction resend when the state has already caught up: the verification now yields once before acting, giving an echo that is on the wire but not yet dispatched a chance to land, and re-reads the merged params before resending
- Stopped swallowing `asyncio.CancelledError` in the verification task, which made a cancelled verification look like a completed one and broke cooperative cancellation on reload and shutdown

### Testing
- Switched the test `FakeHass` to eager task start, matching real `HomeAssistant.async_create_task`; the lazy `loop.create_task` it used before masked this whole class of bug
- Added regression coverage for the echo gate (a slow echo must not produce a duplicate command), a stale correction being unable to land after a newer command, the retry chain surviving eager task start, a superseded (stale-epoch) verification touching no shared state, and a late echo cancelling the correction resend

## [1.4.0] - 2026-07-15

### Fixed
- Fixed color temperature changes from the Home Assistant UI being silently dropped: `light.turn_on` delivers `color_temp_kelvin`, which was not mapped to the device's `color_temp` converter and never reached the gateway
- Made covers report their actual position (`cp`) instead of the target position (`tp`), so a moving or stalled curtain reflects reality rather than snapping to its destination
- Merged partial `params` updates from the gateway instead of replacing them, so previously known channel state (color temp, brightness, switch channels, cover position) is no longer wiped by partial messages
- Derived group light capabilities from the intersection of member modes at topology-finalize time, so on/off-only groups no longer expose a dead color-temperature slider and all-color groups correctly expose RGB

### Changed
- Generalized passive state verification to cover every property in a command (`ct`, brightness, RGB, switch channels), not just power, with retry on mismatch
- Stopped holding the global send lock during reconnect attempts, so a single slow connect no longer serializes commands from every entity
- Replaced random message correlation IDs with a monotonic counter (masked to signed 32-bit for gateway firmware compatibility)
- Removed the topology cache, which never served a cached response
- Simplified `ColorTempKelvin.encode` (dropped the now-unreachable mired heuristic) and collapsed the duplicated climate state-assignment path

### Testing
- Added regression coverage for color-temperature-from-UI, cover actual position, partial `params` merging, generalized verification (including a color-temp retry), monotonic message IDs, group capability derivation (on/off, RGB, and idempotency), and connect-outside-the-lock behavior

### Chore
- Untracked the `.coverage` artifact and ignored local tooling directories

## [1.3.5] - 2026-05-01

### Fixed
- Prevented Home Assistant service kwargs from leaking into climate, cover, and light gateway payloads
- Stabilized light color-mode reporting by honoring user color intent and avoiding guessed RGB/CT mode before real state arrives
- Preserved WiFi panel names reported by the gateway instead of replacing them with a hardcoded label
- Restored gateway connection and diagnostics entity state propagation
- Made reconnect notifications unique per reconnect attempt so repeated reconnects remain visible
- Documented the `send_command.result` service field and added `pid` to the options flow

### Changed
- Routed scene activation through the gateway device abstraction for retry/stat accounting
- Derived group light color modes from member capabilities when members are available
- Hardened gateway send handling around fire-and-forget commands and reserved wire-protocol keys

### Testing
- Added and updated regression coverage for kwargs filtering, light color-mode behavior, WiFi panel names, reconnect notifications, options flow, and service metadata

## [1.3.4] - 2026-03-31

### Fixed
- Preserved Home Assistant registry identity when the gateway host changes by deriving device and entity identifiers from the config entry unique ID
- Prevented `remove_stale_devices` from misclassifying live devices or the gateway itself when identifiers use legacy host-based or stable unique-ID-based prefixes
- Cancelled pending passive state verification tasks during cleanup to avoid lingering retry tasks on unload, reload, and shutdown
- Restored gateway node handling for `id=0` messages so gateway firmware and name updates are applied from topology and prop payloads

### Testing
- Added regressions for host-change identity stability, stale-device cleanup identifier parsing, gateway `id=0` routing, and verification-task cleanup

## [1.3.0] - 2026-02-24

### Fixed
- Hardened TCP message parsing in `ProGateway` to safely handle partial reads and multi-message chunks
- Fixed potential future-state races in `_msgs` handling (late/duplicate/cancelled responses no longer raise `InvalidStateError`)
- Improved reconnect lifecycle after disconnects with explicit reconnect delay and safer connection closing
- Stabilized keepalive behavior with consecutive-failure threshold to avoid false-positive reconnects
- Fixed availability checks in config/options flow by using a temporary probe connection that is always closed

### Changed
- Added connection/send locks in gateway transport layer to reduce concurrent connect/send races
- Tracked and cancelled background gateway tasks during stop/unload for cleaner lifecycle
- Prevented duplicate entity add storms by introducing one-shot queueing before `async_added_to_hass`
- Made scene topology handling idempotent to avoid duplicate scene setup on repeated topology payloads
- Redacted gateway host values in diagnostics output

### Testing
- Added deterministic regression tests for reconnect/keepalive behavior, partial reads, cancelled waiter handling, and duplicate topology requests
- Added tests for entity add deduplication and idempotent scene registration

## [1.1.1] - 2026-01-31

### Fixed
- **State verification now correctly reads power state** - fixed bug where `gateway_post.prop` data was expected in `params` but comes directly as `{'p': true/false}`
- Verification now only triggers when power state is present in update (ignores brightness-only updates)

## [1.1.0] - 2026-01-31

### 🔒 Passive State Verification & Auto-Retry

Addresses the race condition bug where gateway acknowledges commands but doesn't execute them.

### Added
- **Passive state verification** - waits for `gateway_post.prop` after sending power commands
- **Auto-retry on mismatch** - automatically retries command up to 2 times if state doesn't match within 1.5s
- **Zero overhead** - no additional gateway requests, uses existing `gateway_post.prop` messages
- **New diagnostics metrics**:
  - `state_mismatches` - count of detected state mismatches
  - `state_corrections` - count of successful auto-corrections

### Technical
- Verification only triggers for power state (`p`) commands to minimize overhead
- Can be disabled per-command with `verify=False` parameter
- Constants: `STATE_VERIFY_TIMEOUT=1.5s`, `STATE_VERIFY_RETRIES=2`
- Verification task is cancelled early if `gateway_post.prop` arrives with matching state
- No polling - purely event-driven verification

### How it works
1. Send command to gateway
2. Schedule verification task that waits 1.5s
3. If `gateway_post.prop` arrives with matching state → cancel task (success)
4. If timeout occurs and state doesn't match → retry command
5. Repeat up to 2 times

## [0.7.1] - 2026-01-28

### Fixed
- **Gateway firmware version** now correctly retrieved from topology
  - Gateway node (id=0, nt=GATEWAY) is now processed in `XDevice.from_node()`
  - Gateway properties (including firmware version) are updated from topology data
  - Firmware update entity now displays actual version instead of "unknown"

## [0.7.0] - 2026-01-28

### Added
- **Retry mechanism** for failed commands with exponential backoff (3 retries by default)
- **Command queue** for sequential command processing and race condition prevention
- **Debouncing** for rapid changes (prevents command flooding during slider adjustments)
- **Topology caching** with configurable TTL (5 minutes default) to reduce gateway load
- **State reconciliation** after reconnection - automatically syncs device states
- **Diagnostics sensor** for gateway monitoring with detailed statistics:
  - Uptime, messages sent/received, success rate
  - Command statistics (success, failed, retried)
  - Keepalive and reconnect counters
  - Last error information
- **Configurable transition time** in integration options (0.5-30 seconds)
- **GatewayStatistics dataclass** for comprehensive metrics tracking

### Changed
- Commands now go through a queue for sequential processing (topology/node requests bypass queue)
- Keepalive now uses internal send method to bypass queue for reliability
- Statistics reset on gateway start

## [0.6.1] - 2026-01-28

### Fixed
- Fixed AttributeError in debug logging when accessing device attributes that may not exist
- Gateway device creation now safely handles missing model, pid, and firmware_version attributes

## [0.6.0] - 2026-01-28

### Added
- **Enhanced debug logging** across all components
  - Gateway: JSON dumps of device details, topology, responses, and messages
  - Entities: Detailed logging of entity creation, state updates, and property changes
  - Lights: Comprehensive logging of turn on/off, color mode changes, and transitions
  - All debug logs include JSON-formatted data for easy inspection

## [0.5.4] - 2026-01-28

### Fixed
- Fixed color_mode persistence during state updates
- Ensured color_mode is always set and preserved in async_set_state

## [0.5.3] - 2026-01-28

### Fixed
- Fixed entity service schema error for `prestage_color_temp` service
- Fixed missing color_mode reporting in light entities (HA 2025.3 compatibility)
- Updated bug report URLs to point to correct repository

## [0.5.2] - 2026-01-28

### Changed
- Fixed manifest key ordering to satisfy Home Assistant validation

## [0.5.1] - 2026-01-28

### Changed
- Release maintenance: retagged 0.5.0 without the `v` prefix
- No code changes compared to 0.5.0

## [0.5.0] - 2026-01-28

### Added
- **Backward-compatible migration system** for smooth transition from old integration versions
- Dual device identifiers support (old + new format) to prevent device loss during migration
- Smart unique_id selection that prefers existing registry entries to avoid entity duplicates

### Changed
- Device identifiers now include both legacy format (`device.id`) and new format (`{gateway_host}-{device.id}`)
- Entity unique_id generation now checks registry for existing entries before creating new ones
- Gateway host is now preferred over entry_id for better stability across reinstalls
- Simplified `async_added_to_hass` method - migration logic moved to `__init__` for better reliability

### Migration Notes
This release enables seamless migration from older versions:
- **Existing users**: All devices and entities will be preserved automatically
- **New users**: Will use the new identifier format from the start
- **Rollback support**: Can safely revert to older versions if needed

The migration strategy:
1. Device identifiers include both old (`str(device.id)`) and new (`{host}-{device.id}`) formats
2. Home Assistant matches devices by old identifier but also registers the new one
3. Entity unique_ids check the registry - if old format exists, it's reused; otherwise new format is used
4. This prevents entity duplication and allows smooth forward/backward migration

### Technical Details
- Changed device identifier from single `(DOMAIN, f"{host_or_entry}-{device.id}")` to dual set
- Added registry lookup in `XEntity.__init__` to check for existing unique_ids
- Removed one-way migration logic from `async_added_to_hass` in favor of smarter initialization

## [0.4.0] - Previous Release
- Various improvements and bug fixes
- Enhanced stability and diagnostics
- Comprehensive test coverage (100+ tests)
