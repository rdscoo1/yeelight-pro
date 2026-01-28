# Release Notes

## [0.6.0] - 2026-01-28

### ✨ New Features

- **Enhanced Debug Logging**
  - Added comprehensive JSON-formatted debug logging throughout the integration
  - **Gateway logging** (`core/gateway.py`):
    - Device discovery with full device details (id, name, type, model, pid, firmware, properties)
    - Topology updates with complete node data
    - All incoming/outgoing messages with full JSON payloads
    - Property changes and events with detailed data
  - **Entity logging** (`__init__.py`):
    - Entity creation with device info and unique_id details
    - State updates with old/new value comparisons
    - Attribute changes with full data
    - Property encoding and sending with payloads
  - **Light logging** (`light.py`):
    - Turn on/off operations with all parameters
    - Color mode changes (RGB, COLOR_TEMP, BRIGHTNESS, ONOFF)
    - Brightness and color temperature adjustments
    - Prestage operations
  
  Enable debug logging in Home Assistant configuration:
  ```yaml
  logger:
    default: info
    logs:
      custom_components.yeelight_pro: debug
      custom_components.yeelight_pro.core: debug
  ```

**Full Changelog**: [0.5.4...0.6.0](https://github.com/rdscoo1/yeelight-pro/compare/0.5.4...0.6.0)

---

## [0.5.4] - 2026-01-28

### 🐛 Bug Fixes

- **Fixed color_mode persistence during state updates**
  - Color mode is now properly maintained when device state changes
  - Added fallback logic to ensure color_mode is always set
  - Resolves remaining "does not report a color mode" warnings

**Full Changelog**: [0.5.3...0.5.4](https://github.com/rdscoo1/yeelight-pro/compare/0.5.3...0.5.4)

---

## [0.5.3] - 2026-01-28

### 🐛 Bug Fixes

- **Fixed entity service schema error** for `prestage_color_temp` service
  - Added proper `ENTITY_SERVICE_FIELDS` to service schema
  - Resolves: "The yeelight_pro.prestage_color_temp service registers an entity service with a non entity service schema"

- **Fixed missing color_mode reporting** in light entities
  - All light entities now properly report their color mode
  - Ensures compatibility with Home Assistant Core 2025.3
  - Color mode is initialized based on supported features (RGB → COLOR_TEMP → BRIGHTNESS → ONOFF)

- **Updated repository URLs**
  - Documentation and issue tracker now point to `rdscoo1/yeelight-pro`
  - Bug reports will be directed to the correct repository

**Full Changelog**: [0.5.2...0.5.3](https://github.com/rdscoo1/yeelight-pro/compare/0.5.2...0.5.3)

---

## [0.5.2] - 2026-01-28

### 🛠️ Maintenance

- Fixed manifest key ordering to satisfy Home Assistant validation

**Full Changelog**: [0.5.1...0.5.2](https://github.com/rdscoo1/yeelight-pro/compare/0.5.1...0.5.2)

---

## [0.5.1] - 2026-01-28

### 🛠️ Release Maintenance

- Retagged the 0.5.0 release without the `v` prefix
- No code changes compared to 0.5.0

**Full Changelog**: [0.5.0...0.5.1](https://github.com/rdscoo1/yeelight-pro/compare/0.5.0...0.5.1)

---

## [0.5.0] - 2026-01-28

### 🎯 Backward-Compatible Migration System

This release implements a robust migration strategy that allows seamless transition from older integration versions to your fork, with full rollback support.

### ✨ What's New

#### Dual Device Identifiers
- Devices now have **both old and new identifiers** in the device registry
- Home Assistant matches by the old identifier but also registers the new one
- Prevents device loss during migration
- Format: `{device.id}` (old) + `{gateway_host}-{device.id}` (new)

#### Smart Unique ID Selection
- Entities check the registry for existing `unique_id` before creation
- If old format exists → reuse it (prevents duplicates)
- If not → use new format
- No manual intervention required

#### Improved Stability
- Gateway **host** is now preferred over `entry_id`
- Better stability across Home Assistant reinstalls
- Consistent identifiers even if config entries change

### 🔄 Migration Behavior

#### For Existing Users
✅ All devices and entities preserved automatically  
✅ No need to re-add devices  
✅ No entity duplicates  
✅ Seamless upgrade experience  

#### For New Users
✅ Clean installation with new identifier format  
✅ No migration overhead  

#### Rollback Support
✅ Can safely revert to older versions  
✅ Old identifiers remain in registry  
✅ Devices won't be lost  

### 🔧 Technical Implementation

#### Device Info Changes
```python
# Before (0.4.0)
DeviceInfo(
    identifiers={(DOMAIN, f"{host_or_entry}-{device.id}")},
    ...
)

# After (0.5.0)
DeviceInfo(
    identifiers={
        (DOMAIN, str(device.id)),              # Old anchor
        (DOMAIN, f"{gw_id}-{device.id}"),     # New format
    },
    ...
)
```

#### Entity Unique ID Logic
```python
# Check registry for existing entity
old_uid = f"{device.id}-{attr}"
new_uid = f"{gateway_host}-{device.id}-{attr}"

existing = registry.get_entity_id(domain, DOMAIN, old_uid)
unique_id = old_uid if existing else new_uid
```

### 📊 Test Coverage

✅ **104 tests passing**  
✅ All entity types tested  
✅ Migration logic verified  
✅ No regressions  

### 📝 Upgrade Instructions

#### From v0.4.0 or Earlier

1. **Backup your Home Assistant** (recommended)
2. Update the integration via HACS or manually
3. Restart Home Assistant
4. **That's it!** All devices and entities will work automatically

#### If Issues Occur

1. Check logs: `Settings → System → Logs` (filter by `yeelight_pro`)
2. If needed, revert to previous version
3. Report issue with logs on GitHub

### 🐛 Bug Fixes

- Fixed test compatibility with registry access
- Improved error handling in entity initialization
- Better handling of missing gateway references

### 📚 Documentation

- Added comprehensive CHANGELOG.md
- Updated migration notes
- Improved code comments

### 🙏 Credits

Migration strategy inspired by Home Assistant best practices for integration forks.

**Full Changelog**: [v0.4.0...v0.5.0](https://github.com/rdscoo1/yeelight-pro/compare/v0.4.0...v0.5.0)

---

## [0.4.0] - Previous Release

- Various improvements and bug fixes
- Enhanced stability and diagnostics
- Comprehensive test coverage (100+ tests)

---

## How to Add New Release Notes

When creating a new release, add a new section at the top following this format:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### 🎯 Main Feature/Theme

Brief description of the release focus.

### ✨ What's New
- Feature 1
- Feature 2

### 🐛 Bug Fixes
- Fix 1
- Fix 2

### 📚 Documentation
- Doc update 1

**Full Changelog**: [vX.Y.Z-1...vX.Y.Z](link)

---
```
