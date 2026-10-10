# Combined local iPad source

Use the `integration/ipad` branch in `Madeira-integrated` for the combined app.
The sibling `Madeira-integrated-control` worktree holds `integration/ipad-control`:
the same app source with X1 and W1 reverted. `integration/ipad-baseline` is the
older automation/SSD reference before the later local OpenGL/SSD merge; it is
not a matched control for the current integration.

[Input manifest](ipad-inputs.json) records exact source commits and validation.
All topic branches and draft PRs remain intact. Neither fork nor upstream main
was changed. Merge commits retain each input's history. Make fixes on the relevant
topic branch, then merge its new tip into integration; never merge integration
back into a topic. Keep native outputs, DerivedData and captures inside their
own worktree. Do not reuse a stale archive as evidence that a native change ran.

## Included work

PR19 includes PR16–18's reservation/controller/JIT work and the validated SSD
branch (upstream PR235). The original local OpenGL/SSD branch supplies newer
storage recovery/downloader fixes and optional OpenGL support. Its SSD code was
reconciled using the validated SSD source as the common content base, retaining
both automation and local additions in the Xcode project. Automation commands
and the debug native presentation anchor remain present. No input topic was
rewritten to resolve this integration.

PR20–24 provide diagnostic gating, shader-cache validation, optional wineserver
wake coalescing, staged compiler-cap/shutdown patches and per-game JIT plans.
PR25 adds the shared native submission-trace consumer. G2's patches remain
unapplied and its worker cap is not enabled by this merge. W1 is disabled unless
`MADEIRA_SRV_COALESCE=1`; invalid/unset values retain the old path. X1 now disables
its three task-wide profilers by default; its documented flags opt them in.
No cache, JIT block size, QoS or worker-count default was changed.

## Validation and remaining work

The final integration passed 104 automation host tests (2 physical wrappers
skipped), affected frontend/SSD/Dock checks, X1/W1 ASan/UBSan concurrency checks,
G1 host Foundation/SQLite checks and G2 host scheduler checks. Both normal and
opted-in automation Swift source lists type-check for iOS. The actual changed
ntdll/wineserver sources compile into iOS arm64 objects using the existing Wine
configured headers read-only. These are source/object checks, not a complete
linked app or physical acceptance. Patch-file context whitespace is inherited
from the OpenGL patch assets and was preserved so patches still apply.

This fresh worktree does not yet contain a complete rebuilt native dependency
and Wine payload set. Assemble it per docs/BUILDING.md before using the harness
build command; keep outputs isolated. Verify actual archive provenance, Dock and
i386/WoW64 payload closure, signatures and automation exclusion from normal
Debug/Release before installation. Preserve the installed app's data and do not
install over a running game. No app was installed or terminated during integration.

Next performance milestone is the single #2-owned, opt-in native raw sampler
at the real Present boundary, consumed by #14's new versioned importer. Aggregate
FPS or sampled Present logs cannot supply individual frame times. Submission
cadence is distinct from visible frames and GPU execution. Add CPU/GPU attribution
only at measured boundaries and keep missing data explicit. Validate clocks,
bounds and disabled/enabled overhead on iPad, then implement deterministic input
replay (#12) and repeated paired trials (#15). Portal menu recognition does not
establish a stable gameplay benchmark.

Use the existing kernel device reservation across install, JIT, game control,
capture, cleanup and thermal recovery. Do not change its shared namespace.
For G1/W1/F2 comparisons keep X1 sampler policy identical in both arms. The
control branch restores old always-on profilers and is useful for X1 validation;
it is not automatically a fair control for other experiments. Prefer toggling
one variable in the same tested binary when the experiment permits it.

## Upstream PR preparation

Keep each fork topic review separate. Once a change is physically accepted,
create a fresh upstream topic from current origin/main and cherry-pick only its
implementation/test commits, excluding the investigation umbrella and integration
history. G2 native/PE submodule changes will need their own upstream dependency
and gitlink handling. Keep PR235 separate from local-only OpenGL and automation.
Do not close draft acceptance gaps merely because the combined source passes.
