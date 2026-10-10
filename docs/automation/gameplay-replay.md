# Debug gameplay replay

Issue #12. Only the opted-in Debug command panel accepts these operations:
`reserve_input` in a fresh idle process (stable player-one identity before
Wine enumeration), `start_replay` in the API-owned active focused game,
`get_replay_status`, and `stop_replay`.

A replay object has `duration_ms` (1–900,000) and 1–64 `events`, within the
existing 4096-byte command bound. Every event has strictly increasing `at_ms`
(0 <= value < duration) and a complete `keys` snapshot (at most 16 distinct VK
codes: Enter, Escape, Shift, Ctrl, Space, arrows, digits and letters). Optional
`dx`/`dy` are relative mouse deltas bounded to ±1000. Optional `buttons` and
`lx`/`ly`/`rx`/`ry` supply the virtual XInput snapshot, with actual native ranges.
No paths, account actions or arbitrary runtime arguments are accepted.

Keyboard samples are unioned with physical keys in HardwareInput's existing
edge publisher, so clearing virtual input does not release a held physical key.
Mouse deltas use its existing relative pointer bridge. Virtual pad snapshots
merge on GamepadInput's existing serial queue; no competing driver writer exists.
The optional early slot remains reserved at rest for this process.

Replay schedules locally against Dispatch uptime, samples every 4 ms, records
per-event lateness in microseconds, and stops on an event more than 100 ms late.
This is timed input, not frame-aligned replay. Completion, stop, focus loss,
backgrounding and heartbeat timeout release all virtual keys/pad controls.
The host must tap the existing Refresh button at least every 10 seconds to
maintain its lease heartbeat. Automatic snapshot refresh must not count as a
host heartbeat. An inactive/menu/cloud-held session never receives replay input.

Host validation covers the actual Swift command/plan parser and Python's
preflight validator. Physical keyboard/mouse/pad response, focus interruption,
heartbeat release and a reproducible gameplay checkpoint remain separate gates.

## On-device measurement window

`start_benchmark` combines replay with `warmup_ms` and `capture_ms`. Their sum
must equal the plan duration. The native replay timer starts capture after warmup
and freezes/exports it at the end, then releases input. This avoids opening the
command editor during measurement (which correctly interrupts gameplay focus).
`benchmark-capture PLAN --warmup 60 --seconds 180` maintains the existing Refresh
heartbeat, requires an API-owned session and the same foreground PID throughout,
retrieves the frozen trace under the same reservation and exports summaries.
It never launches, quits or force-kills an unknown game. Interrupted/lost captures
fail; they cannot reuse a prior export as a successful benchmark.

Capture establishes telemetry, not gameplay readiness or an optimization result.
A paired experiment still needs matched scenes/cache/thermal conditions, source
and installed-binary manifests, multiple independent trials and sustained tests.
