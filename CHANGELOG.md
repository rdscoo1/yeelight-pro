# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
