# Changelog

Notable changes per release. Versions follow [SemVer](https://semver.org).

## Unreleased

### Fixed

- The connection is no longer retired once an hour. Dropping a working link
  handed the charger's only connection slot away, and getting it back took
  minutes of failed connects when something else claimed it first.
- A reconnect now waits for the previous teardown to finish. Connecting into
  that window failed with GATT error 133 after 20 seconds per attempt.
- A poll that goes unanswered on a link the proxy still reports as up is now
  cut short after 30 seconds instead of running into the 4-minute backstop.
