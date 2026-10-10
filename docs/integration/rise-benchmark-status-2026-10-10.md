# Rise benchmark preparation and current device blocker

The focused branch `automation/rise-benchmark-results` at `f4c6666` is merged
with ancestry into `integration/ipad` at `d0e2abf`. Both are pushed to the fork.
It adds English Rise menu/result recognition, a bounded result-to-result runner,
and explicit same-build single-variable comparison support with genuine distinct
configuration digests. See [the adapter guide](../automation/rise-benchmark.md).

Validation: 215 host tests passed, two physical wrappers skipped. The Swift
reader compiled and recognized the saved 33.85 FPS result (all three scene rows
matched), recognized the main menu, and rejected gameplay/loading/settings
screens as completed results. These are saved-screen checks, not a successful
new end-to-end device benchmark. Independent iteration export and a fresh-process
AB/BA orchestration wrapper remain to be connected to this adapter.

All five performance preparation branches (PR20–24) are ancestors of integration.
W1 and X1 runtime code is already combined; G2 remains staged/unapplied experiment
preparation. Their draft status and runtime acceptance gates are unchanged.
No additional performance implementation was enabled, rebuilt or installed today
in this follow-up. DX12 experiments PR35/37 remain separate from this DX11 trial.

Physical observation during this follow-up:

- Wired iPad detected, Madeira process still alive, JIT ready, owned Rise session.
- Authenticated paired socket snapshots worked. Experiment state NOT_REQUESTED,
  requested/process environment both empty. No new switch trial was started.
- The device reported serious thermal pressure. No timing measurement was taken
  under that condition and no baseline or speedup is claimed.
- XCTest repeatedly failed to enable automation mode. This prevented screenshots
  and UI bootstrap. The alternate read-only screenshotr route was unavailable.
- The owner was away from the iPad. An authorized normal stop_game request was
  accepted; the owned game remained running in STOP_REQUESTED for the bounded
  two-minute observation. It may require an in-game confirmation. No force kill,
  reinstall, settings change or save deletion was attempted.

When the owner is back, inspect the screen and any normal exit confirmation,
restore the UI automation connection, and let the device return to nominal/fair.
Do not repeat stop_game blindly: the process has already recorded STOP_REQUESTED.
Use normal Madeira save/upload-and-close flow to end the process, then launch
fresh explicit W1=0/1 arms on the same installed binary, checking actual native
mode and preserving cpuCount=4, monitor-identity setting, DLL and graphics settings.
The earlier 34.30 and 33.85 scores remain uncontrolled references, not A/B evidence.

The unrelated local Wine/build-list/DLL/toolchains work remains untouched. No
upstream submission, tracking-issue closure or branch deletion was performed.
