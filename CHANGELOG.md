# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-30

### 🎉 Stable Release

This is the first stable release of Yeelight Pro integration with comprehensive bug fixes and improvements.

### Added
- **Russian README** (`README_RU.md`) with full documentation
- **Prestage color temperature service** - set color temp while light is OFF
- **Prestage color temperature example** in automation documentation
- Complete automation examples for common use cases
- **Smart optimization** - `prestage_color_temp` skips gateway request if temperature already set (when light is OFF)

### Fixed
- **UI state synchronization** - removed transition-blocking logic that caused UI to show stale values
- **Color temperature rounding** - gateway now trusted as source of truth for all state updates
- **Entity platform errors** - added `self.added` check before `async_write_ha_state()`
- **ATTR_TRANSITION import** - restored missing import

### Changed
- Simplified state update logic - all gateway updates applied immediately
- Removed unused code: `target_task`, `_target_attrs`, transition delays
- Improved logging for better debugging

### Performance
- Reduced network traffic in `prestage_color_temp` by skipping redundant requests
- Faster response time when color temperature is already set

### Technical
- 104 passing tests
- Full test coverage for light entity
- CI/CD with GitHub Actions

## [0.7.7] - 2026-01-30

### Fixed
- **NameError: ATTR_TRANSITION is not defined**
  - Restored `ATTR_TRANSITION` import that was accidentally removed in 0.7.6
- **Entity None does not have a platform error**
  - Added `self.added` check before calling `async_write_ha_state()` in `async_turn()` and `async_prestage_color_temp()`

## [0.7.6] - 2026-01-30

### Fixed
- **UI not updating color temperature after change**
  - Root cause: color_temp values don't match exactly due to rounding in converter
  - Example: UI sends 5161K, converter rounds to 5181K, gateway returns 5181K
  - Comparison 5181 != 5161 failed, so update was ignored
  - Solution: removed entire transition-blocking logic
  - Now gateway is always trusted as source of truth
  - Removed unused code: `target_task`, `_target_attrs`, related imports

## [0.7.5] - 2026-01-30

### Fixed
- **Brightness/color updates blocked by on/off state**
  - Removed `light` (on/off state) from watched transition attributes
  - Gateway doesn't always send `p:true` when changing brightness on already-on light
  - This caused `pending={"light": true}` to remain forever and block all attribute updates
  - Now only `brightness`, `color_temp_kelvin`, and `rgb_color` are watched during transitions

## [0.7.4] - 2026-01-30

### Fixed
- **State updates not being applied after transition**
  - Removed clearing of `_target_attrs` in `_apply_state_later()`
  - Clearing `_target_attrs` was breaking `diff` calculation (became huge number)
  - Now `_apply_state_later()` does nothing - just waits for transition to complete
  - Transition mechanism handles clearing pending attrs as they match incoming data

## [0.7.3] - 2026-01-30

### Fixed
- **UI jumping back to old values after state changes**
  - Fixed `_apply_state_later()` sending stale attributes via `async_write_ha_state()`
  - Now only clears `_target_attrs` without triggering UI update with outdated data
  - Resolves issue where brightness/color temp would revert to old values in UI while physical device had correct values

## [0.7.2] - 2026-01-30

### Fixed
- **UI state jumping back** after changing color temperature on physical device
  - Fixed `_apply_state_later()` applying stale data from closure during transition
  - Now only refreshes UI state without overwriting with potentially outdated values

### Added
- **Enhanced debug logging** in `async_set_state` for light entities
  - Logs incoming data, transition timing, pending attributes
  - Logs when state updates are ignored or applied during transitions
  - Helps diagnose state synchronization issues

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
