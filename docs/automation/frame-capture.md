# Native submission capture

Issue #2 producer; #14's existing importer consumes the version 1 trace.
The fixed C ring records individual CLOCK_MONOTONIC nanosecond timestamps at
DXMT's existing Present counter boundary, before the quiet logging gate. It
measures submission cadence, not visible frames, CPU encode or GPU time. RAW
mailbox and multiple surfaces retain their original meanings.

Recorder storage (250,000 events) exists only in opted-in Debug. Disabled capture
reads an atomic flag; enabled capture uses a nonblocking writer lock and records
contention/overflow loss. Stop drains writers; JSON allocation/file writing occurs
only after measurement. Loss or clock failures make the trace unsuitable for
percentiles and are rejected by the importer. Backgrounding stops capture.

Build a separate native archive inside the measurement worktree with
`MADEIRA_FRAME_CAPTURE=1 bash build/dxmt-ios/build.sh`. This stages a copy of the
pinned DXMT source with a weak app callback; it does not modify DXMT's gitlink or
submodule implementation. Normal archives use the original source. Never mix
measurement and production archives/DerivedData. Build the app using the existing
`build --automation` harness command. Normal Debug/Release exclude the recorder;
binary checks enforce its marker. Starting capture rejects an archive missing the
native hook rather than exporting empty data as success.

After API launch and an independently established scene:
`start_frame_capture`, then `stop_frame_capture`. Stop exports only to the fixed
app-owned `Documents/automation-submission-trace.json`; no arbitrary request path
is accepted. Retrieve it under the shared reservation with devicectl and use
`summarize-telemetry`. Export is atomic and owner-only. One process/capture only;
a new start resets prior samples. Copy each completed export before starting
another capture. Keep binary/source/settings/thermal manifests alongside it.

Host ASan/UBSan verifies actual ring concurrency, bounds, restart, disabled state
and timestamp order; source staging fails closed if its anchor changes. Physical
clock accuracy, native callback delivery, overhead, background interruption and
paired benchmark acceptance must be measured separately.

Capture also exports `automation-capture-metadata.json` with the same capture ID.
Only the start/end boundaries query `getrusage(RUSAGE_SELF)` for process user and
system CPU time and `TASK_VM_INFO` for footprint. The monotonic wall window
brackets recorder activation/drain; these are whole app CPU totals, including
UI heartbeat work, not Wine role attribution, frame encoding or GPU timing.
Unavailable counters export null. No extra query is added to Present.

Physical delivery on 2026-10-10: the isolated integrated signed Debug app ran
Portal via the harness/JIT workflow on the wired M5 iPad. A ten-second menu
capture exported 600 events; a fifteen-second existing-save gameplay capture
exported 899. Both passed contiguous-sequence, monotonic-clock and loss checks.
A later thirty-second capture exported 1,799 events with matching whole-app CPU,
footprint and initialized W1 mode 0. These prove callback/export delivery, not
visible-frame timing, clock calibration, observer overhead or an optimization.
Normal signed Debug/Release builds using the original native Present source
passed actual marker exclusion checks before the later wake-policy accessor
addition. No app data was reset; existing saves were backed up privately.
