# Changelog

Notable changes per release. Versions follow [SemVer](https://semver.org).

## 0.1.1 - 2026-09-09

### Fixed

- The connection is no longer retired once an hour. Dropping a working link
  handed the charger's only connection slot away, and getting it back took
  minutes of failed connects when something else claimed it first.
- A reconnect now waits for the previous teardown to finish. Connecting into
  that window failed with GATT error 133 after 20 seconds per attempt.
- A poll that goes unanswered on a link the proxy still reports as up is now
  cut short after 30 seconds instead of running into the 4-minute backstop.

### Changed

- Requires easee-ble 0.1.1. A poll interrupted by a link drop now fails
  immediately instead of waiting out the reply timeout and blaming the CCCD
  subscription, which pointed at the wrong cause.
