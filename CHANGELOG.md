# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
