# Rise of the Tomb Raider benchmark adapter

This host-only adapter reads the English built-in benchmark's own FPS numbers.
It does not infer visible FPS from Present submission timing. Its tests and
saved-screen recognition pass; a complete physical repeated run is still pending.
No installed app rebuild is needed for these host changes.

Build the reader on macOS:

```sh
swiftc automation/controller/rise_checkpoint.swift -o /tmp/madeira-rise-checkpoint
```

`rise_benchmark.run_from_result(workflow, executable)` requires the caller to hold
`reserve_device` and an authenticated paired transport for the entire call. It
verifies foreground state, automation ownership and installed Steam app 391220.
By default, start on a previous benchmark's result screen. The adapter dismisses it, waits
for the main menu, presses Enter on the previously selected Start Benchmark item,
and requires departure from menus/results before accepting two identical fresh
result observations. Unknown navigation or a non-starting benchmark times out;
it does not send speculative extra input. For the first run in a fresh process,
`selected_menu=True` skips result dismissal after the caller has visually verified
that Start Benchmark is selected. Menu recognition verifies the menu labels, not
the highlighted selection. Evidence is written under the caller's
private run directory, including failed attempts. Result-screen recognition alone
does not establish visual correctness throughout gameplay.

The reader exports only fixed checkpoint labels and numeric results. CPU-only
Vision recognition avoids the prolonged accelerator initialization observed on
this Mac. Recognition is bounded by a ten-second subprocess timeout; key replays
finish before recognition starts. Socket observations run every 1.5 seconds
between result checks, which occur approximately every ten seconds. Screenshot
and result-check overhead must be identical in both arms and measured separately
before claiming a low-overhead capture method.

## Comparisons with a declared switch

Iteration schema 1 remains supported. Schema 2 additionally requires
`runtime_config`, a bounded string dictionary, and its SHA-256 in
`conditions.runtime_config_digest`. Use `benchmark_compare.runtime_digest` to
hash canonical JSON. Include the complete experiment configuration, including
unchanged CPU count and per-game settings; do not omit a setting just to match.
The digest is evidence supplied by the producer, not proof of device application.
Record actual applied startup environment and native initialized modes separately.

`benchmark-compare --experiment MADEIRA_SRV_COALESCE ...` permits exactly that
single runtime difference with otherwise identical conditions and source/binary
identity. Other runtime differences, missing flags and unequal build identities
are rejected. Each arm retains its own real digest. `game_reported_fps` is a
separate higher-is-better metric. Existing thermal, failure, ordering, repeat-count
and visual gates still apply. A statistical difference does not establish causal
attribution or visual acceptance.

For the first W1 trial, use the current matched installed binary with explicit
mode 0 and mode 1 at startup. Preserve cpuCount=4, DXMT_WSI_MONITOR_IDENTITY=1,
faultrep.dll and the game's graphics settings. Confirm `wineserver_wake_mode`
in native capture metadata. Use at least five independent iterations per arm,
interleaving AB/BA fresh-process arms; discard equivalent warmups in both arms.
Do not count repeated samples within one trace as independent iterations. Keep
cache phase, screenshot policy and thermal conditions matched. Retain failures,
and exclude a run if thermal pressure becomes serious/critical at any point.
Old control branches and the earlier 34.30/33.85 FPS screenshots are not matched
A/B baselines. X1, cache and FEX settings are separate experiments; do not change
them alongside W1.
