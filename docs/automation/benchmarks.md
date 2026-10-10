# Benchmark milestone gate

There is no implemented game benchmark runner yet. Do not interpret the UI smoke
or standalone FEX test as a performance benchmark. Physical UI control plus JIT
must pass before implementing the dependent game lifecycle and input milestones.

## Existing measurable sources

- `FPSOverlay.swift` samples native present count over a window. A difference
  in count / elapsed monotonic time can give a sampled present rate, not
  individual frame times, GPU time or a meaningful 1% low.
- Existing task_info footprint sampling is app memory, not isolated guest/GPU
  memory. DeviceLoadDiagnostics exposes public thermal state and low power mode.
- `LibraryModel.poll` and `DockStartScreen` supply existing startup observations.
  A game-specific ready checkpoint is still required; desktop frames and a
  launch spinner disappearing are insufficient for many Steam games.
- FEXBridge's standalone test reports completion but does not separate translation
  from execution. No new FEX counters were invented.
- Wine request/wait latency and DXMT shader/pipeline/command-buffer/GPU timings
  require further source and on-device measurement. No upstream code was changed
  and no CPU timer is presented as a GPU measurement.

## Next implementation after device proof

1. Bind a debug-only command queue to `launchLibraryEntry` / normal Steam Dock
   launch and `LibraryModel.requestQuit`; preserve cloud-save/user confirmation
   gates. Implement truthful lifecycle events and per-game ready checkpoints.
2. Merge virtual samples inside GamepadInput's serial publisher. Reserve a stable
   controller identity before game enumeration; release held input on timeout,
   disconnect, focus loss and replay completion. Avoid competing direct writes
   to winios_gamepad_set_state. Reuse keyboard/mouse translation paths too.
3. Record monotonic event timestamps and observed replay lateness. Frame alignment
   needs a rendering-clock integration; don't claim frame-perfect host timing.
4. Add opt-in bounded frame-time collection at actual present/submit/completion
   points. Distinguish each clock and CPU/GPU/end-to-end scope. Keep counters
   disabled by default and measure collection overhead.
5. Implement repeated warmup/measurement iterations with versioned run metadata:
   source commit/dirty flag, signed app identity, device/OS, game, resolution,
   graphics/runtime settings, thermal state, duration and evidence filenames.
   Restart app and re-enable JIT between native sessions when required.
6. Compare independent iterations, not individual frames treated as independent
   trials. Report inconclusive results when noise/sample count is insufficient;
   report environment/thermal mismatches instead of attributing them to code.

Offline screenshot checks are available now through `compare-images`; calibrate
crop and tolerances with actual captures before using them as a rendering gate.

## Shared telemetry contract (issues #2 and #14)

`automation.controller.telemetry` owns the version 1 **consumer** for #14.
Issue #2 owns the native producer; there is no second sampler. Run:

```sh
python -m automation.controller.cli summarize-telemetry /private/submission-trace.json
```

This is an offline import; it neither discovers nor mutates a device. Reports
and validated raw data go into owner-only `automation/runs` directories.
It cannot create timing samples from the overlay or the existing Present logs.
The native producer, replay runner and paired physical trials remain pending.

The exact input keys are `schema_version` (integer 1), `clock`
(`clock_monotonic_ns`), `scope` (`present_submission`), `capture_id`
(1–64 ASCII letters/digits/underscore/hyphen), `complete` (boolean),
`dropped_samples` (nonnegative integer), and `samples` (array). Each sample
contains exactly `sequence` (positive integer) and `timestamp_ns` (nonnegative
integer); both must fit signed 64 bits. Sequence numbers are contiguous within
one capture and timestamps strictly increase. All samples belong to the same
process and clock; a restart requires a new capture. Two timestamps yield one
interval. The first event must not be assigned an invented preceding interval.

The producer must stop/freeze before export, retain at most 250,000 events,
report loss/overflow, and use actual individual events. The importer rejects
loss, incomplete captures, gaps/resets, duplicate keys, unknown fields,
nonmonotonic clocks and files over 32 MiB. It emits submission interval
p50/p95/p99 using nearest rank, submission rate in Hz and over-budget intervals.
These describe **Present submission cadence**, not visible FPS, GPU time or CPU
encoding. Those measurements are explicitly null. It makes no 1% low claim.
Do not feed this output into the older rendered-frame CSV summarizer.

The existing native boundary is `madeira_log_present_cadence` in
`dxmt/src/winemetal/unix/winemetal_unix.c`, called before Metal's presentation
request. Its counter can describe submitted work; RAW mailbox frames and
multiple surfaces prevent equating it with displayed gameplay. The source also
records an earlier `presentedTime == 0` failure. Any future visible-frame producer
must establish its clock/accuracy on the physical device before extending this
contract. Native collection must remain opt-in and absent from normal Release,
with disabled/enabled overhead measured before interpreting differences.

Trace import deliberately cannot certify a device measurement. A benchmark run
must separately supply source/dirty state, installed binary hashes, submodule
pins, device model/OS, game/scene, resolution/settings, capture policy,
warmup/measurement duration, cache state, thermal conditions and exit evidence.
Private IDs and credentials must stay out of shared reports.

## Comparing iterations (issue #15, offline part)

`benchmark-compare` compares independent iterations offline and never touches a
device. It does not run a benchmark. The runner that writes these records
does not exist yet.

```sh
python -m automation.controller.cli benchmark-compare \
  --baseline runs/a/iteration-*.json --candidate runs/b/iteration-*.json
```

Each file is one version 1 iteration record with exactly these keys:

- `conditions`: `device_model`, `os_version`, `game`, `scene`, `resolution`,
  `settings_digest`, `runtime_config_digest`, `capture_policy` and
  `cache_phase` (`cold`, `disk_warm` or `process_warm`). These must be
  identical within and across both sides, otherwise the result is
  `inconclusive` and the differing fields are listed.
- `source`: `commit`, `dirty` and installed `binary_sha256`. Each must be
  uniform within a side. A dirty source becomes a caveat.
- `order_index`: the iteration's position in the whole session. If all
  baseline iterations ran before all candidate ones (or the reverse), the
  order is `blocked` and an improved or regressed verdict is capped at
  `inconclusive`. Use interleaved AB/BA order.
- `outcome` (`completed`, `startup_failed`, `jit_failed`, `disconnected`,
  `crashed` or `timed_out`), `thermal_state_start` and `thermal_state_end`
  (public `ProcessInfo.ThermalState` names), and `visual_status` (from
  `compare-captures`, or null).
- `metrics`: any subset of `submission_interval_p50_ms`, `_p95_ms`, `_p99_ms`
  and `submission_rate_hz` (from `telemetry-summary.json`; this is submission
  cadence, not visible FPS), plus `loading_ms`, `footprint_peak_bytes` and
  `mean_cpu_cores`. Values are null when unavailable. Failed iterations must
  carry no metrics.

Only completed iterations whose thermal states stayed `nominal` or `fair` enter
a distribution. Excluded iterations are counted. For each metric the tool
needs at least `--min-iterations` (default 5) per side. If either side's
coefficient of variation exceeds `--max-cv` (default 0.15), the metric is too
noisy. Otherwise it computes a seeded bootstrap 95% interval of the relative
median difference. Verdicts:

- `improved` or `regressed`: the whole interval is beyond `--min-effect`
  (default 3%) in one direction.
- `no_meaningful_difference`: the whole interval is inside ±min-effect.
- `inconclusive`: anything else.

The overall status is `review` when the candidate has more failed iterations
or more visual reviews than the baseline. Otherwise it is `regressed` if any
metric regressed, `inconclusive` if any metric is, then `improved`, then
`no_meaningful_difference`. Exit codes: 0 for improved or no meaningful
difference, 1 for regressed or review, 3 for inconclusive, 2 for invalid
input. The report always states `attribution: not_established`, because
differences can come from device, thermal, cache or scene variation as well
as source changes.
