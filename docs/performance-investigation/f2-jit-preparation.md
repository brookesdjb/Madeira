# F2 bounded per-game MaxInst experiment

Tracks [issue #7](https://github.com/brookesdjb/Madeira/issues/7). No FEX code,
runtime default, automation source or app configuration is changed.

The existing WineProcessBridge exports global `env.NAME` lines before runtime
startup, then applies per-game configuration last. The existing per-game route
can already supply `env.FEX_MAXINST`; a new app UI is not required to begin this
experiment. FEX contributions remain subject to its no-AI-code policy.

## Prepared plan and correctness inputs

```sh
python3 docs/performance-investigation/tools/prepare-f2.py \
  --game-id EXISTING_IDENTIFIER --scene FIXED_CHECKPOINT
```

The tool prints JSON and never edits any files or controls a device. It emits
only the allowed MaxInst values 500, 1000 and 5000, config fragments, seeded
balanced AB/BA order, five pairs per candidate/phase, fresh-process requirements
and 15-minute sustained trials. Cold and disk-warm phases remain separate.
Pair count is bounded to 5–50. The output is explicitly a plan, with device/
binary identity, readiness, correctness and measurements marked missing.
It is not an implemented harness benchmark definition or a telemetry schema.

Host checks confirmed reproducible ordering, balanced pairs, bounded candidate
fragments and invalid-parameter rejection. A fixture plan is private under
`diagnostics/performance-f2-2026-10-10/` alongside the worktrees.

Using the existing LLVM-MinGW toolchain read-only, the existing
`tests/x64/fpconf-x64.c` and `setjmp-x64.c` were compiled with `-O2 -g` into that
isolated diagnostics directory. Commands, hashes and compiler output are
recorded there. The existing tracked asmconf binary was hashed; it was not
regenerated or run. None of these binaries was staged into an app or executed
through FEX. Compilation is not guest correctness acceptance.

The generic existing `tests/x64/build.sh` contains historical absolute paths and
copies into an app bundle. Do not use it blindly for this experiment. Compile
and stage through the accepted harness's isolated build route. The asmconf suite
also has its own scratch-space and resumable-output requirements; review them
and use a dedicated test prefix rather than treating a short run as a pass.

## Physical acceptance and rollback

For every value, first run instruction, float and exception/setjmp checks with
the installed translator and include representative Mono behavior. Some probes
require VC runtime components; record missing prerequisites explicitly. Keep
multiblock, TSO, FP/AVX settings, binary/game/scene/graphics, sampler/capture and
thermal policy identical. Record effective MaxInst, not just intended config.

Use the accepted harness and shared reservation for fresh app launch/JIT,
observed readiness, replay, raw compilation/frame measurements and graceful
exit. Pair 500 and 1000 separately against 5000 in cold and disk-warm phases,
then evaluate process-warm behavior separately. A smaller cold pause may cost
warm throughput; neither is assumed to win. Restore the original per-game
config and preserve saves/caches after each experiment.

No MaxInst setting should be promoted from these host results. Config forwarding,
effective translator settings, runtime correctness and performance remain open
until physical iPad evidence is available.
