# Shared physical-device reservation

All Madeira worktrees on this Mac use one kernel-backed reservation per
hardware UDID. `install`, `smoke`, `jit-test` and `actions` acquire it before
installation or Appium session creation and retain it through evidence capture
and cleanup. Discovery, host tests and builds do not control a device.

The default location is `~/.local/state/madeira/device-reservations/`. Hardware
identifiers are hashed in filenames. Owner/run/PID/timestamps are local metadata;
do not publish these files. Leave `MADEIRA_RESERVATION_DIR` unset for ordinary
work: a different directory creates a different reservation namespace.

A competing client fails with `device_reserved_by_another_run` before touching
the device. The persistent lock file must never be deleted or replaced while
clients may be running. PID metadata is descriptive; only the kernel lock grants
ownership. Normal failure releases ownership in `finally`; abrupt process death
also releases the kernel lock. The next owner records
`recovered_exited_owner: true` if the prior process left held metadata. Following
that recovery, inspect device/app state and old run evidence before further
control. A surviving game, WDA runner or JIT service is not evidence that its
previous orchestration process still owns the lock.

The baseline/telemetry tools owned by issue #2 must import this same primitive,
using the canonical hardware UDID returned by `DeviceControl.select`, and hold it
through install, JIT, gameplay, capture, cleanup and thermal recovery:

```python
from automation.controller.reservation import reserve_device

with reserve_device(hardware_udid, "performance-baseline", run_id) as lease:
    # Keep all physical operations and their cleanup inside this context.
    # Include lease in the private run manifest.
    run_baseline_and_cleanup()
```

This is host-wide exclusion for cooperating clients, not a cross-Mac lock or an
OS-level ban on manual Xcode/device operations. Other device tooling must respect
the same reservation. Do not run manual device commands while a lease is held.

Host tests exercise an independent competing process, exception cleanup,
unchanged lock inode, and recovery after killing the owner. They establish lock
behavior on the host. Physical baseline, telemetry and iPad acceptance under #2
remain separate work.
