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
