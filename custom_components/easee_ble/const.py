"""Constants for the Easee BLE integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "easee_ble"

# Address, PIN and scan interval reuse the keys from homeassistant.const.
CONF_SERIAL = "serial"

# Vendor signature, kept in step with the matchers in manifest.json.
MANUFACTURER_ID = 3118
SERVICE_UUID = "be312306-9797-2ebc-c947-08eff95544bc"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# Below this, polling occupies the single connection slot the retries need.
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600

# Backstop for a whole update, reconnect included; the poll has its own, below.
UPDATE_TIMEOUT = 240.0

# A poll on a live link takes about a second: well past that, the link is wedged.
POLL_TIMEOUT = 30.0

# Let a torn-down link settle: connecting into a teardown fails, slowly, with 133.
RECONNECT_SETTLE = 2.0

# Deadline for one user-initiated command; short because somebody is waiting.
COMMAND_TIMEOUT = 45.0

# Collapse a burst of commands into one read-back.
REFRESH_COOLDOWN = 1.0
