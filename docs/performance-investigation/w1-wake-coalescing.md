# W1 opt-in wineserver request-wake coalescing

Tracks [issue #5](https://github.com/brookesdjb/Madeira/issues/5). The existing
one-signal-per-request behavior remains the default. An experimental alternative
is enabled only by this existing configuration flow:

```ini
env.MADEIRA_SRV_COALESCE = 1
```

Only the exact value `1` enables it. Unset, `0` and unknown values retain the
old signal policy. The mode is read when the server loop creates its semaphore;
fully restart Madeira after changing it. No automation source, telemetry
sampler, app setting UI or shared build artifact is changed.

## Protocol

The client already publishes its request before calling `ios_wineserver_wake`.
With coalescing enabled, an atomic pending transition from 0 to 1 signals the
kernel semaphore. Other producers sharing the pending epoch do not signal.
After its existing wait, the server clears pending **before** scanning all
descriptors. A request coalesced before the clear is covered by the upcoming
scan; a request arriving after its descriptor was scanned leaves a signal for
the next pass. Clearing after a scan would lose that wake and is prohibited.

The semaphore retains an early signal. A producer delayed between pending-mark
and kernel signal can leave an extra token, so this is not a strict one-token
bound. Completed bursts avoid the old one-token-per-request backlog. Semaphore
creation publishes mode/state before publishing the usable port. Creation
failure preserves the existing fixed-tick fallback.

Timer deadline calculation, the 1 ms INET polling cap, descriptor dispatch,
MADEIRA_SRV_NOSEM A/B behavior and the stop flag path are unchanged. There was no
explicit stop signal in WineServerBridge at this base; this patch does not add
one or claim to change shutdown latency. Semaphore errors still rely on the
existing bounded fallback behavior, not a newly proved error-recovery protocol.

## Host and compiler validation

```sh
python3 tests/host/check-request-wake.py
git diff --check
```

The production pending helper and wake wrapper run against real macOS Mach
semaphores under ASan/UBSan. Tests check 10,000-request burst signal counts,
publication around clear/scan, delayed signal delivery, and a negative control
that demonstrates the lost wake from a clear-after-scan protocol. Four concurrent
producers complete 800,000 requests across enabled/disabled trials. The consumer
uses an indefinite semaphore wait: no periodic scan or timer can rescue a missed
signal; an outer process timeout fails a hung run. Host atomic queues substitute
Wine descriptor readiness.

These checks passed. Full `fd_ios.c` also compiled successfully to an arm64 iOS
object using the build recipe and read-only configured Wine headers at
`257f271cfffed9f22f7987cac53bc00095d092fe`. Commands/log/object hash are private
under `diagnostics/performance-w1-2026-10-10/` beside the worktrees. No archive or
app was linked, installed or run.

## Remaining acceptance and rollback

Physical guest correctness, INET progress, deadlines, stop under load and
request/scan/latency measurements remain pending. The source guards establish
placement and retained deadline/stop code, not their device behavior. Use the
same X1 sampler policy in both arms, one shared reservation, matched manifests
and #2's paired/sustained protocol. No device speedup is claimed.

Remove the switch or set it to `0`, then restart, to restore the unchanged
default. Revert the W1 commit to remove the experimental path entirely.

`ios_wineserver_wake_mode()` exposes the initialized backend policy read-only.
It acquires the published semaphore before reading the atomic startup policy;
-1 means no usable semaphore. The opt-in capture sidecar can record this at its
boundaries without transferring a growing live log or adding hot-path queries.
