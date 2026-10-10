# Combined local iPad source

Use the `integration/ipad` branch in `Madeira-integrated` for the combined app.
The sibling `Madeira-integrated-control` worktree holds `integration/ipad-control`:
an earlier app source with X1 and W1 reverted. It lacks the new capture/replay work
and must be refreshed before it can serve as a matched control. `integration/ipad-baseline` is the
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
PR25 adds the shared native submission-trace consumer. PR26 adds its bounded native
producer and process CPU/footprint sidecar; PR27 adds timed input and on-device
warmup/capture windows, fresh status reads and bounded experiment settings. G2's patches remain
unapplied and its worker cap is not enabled by this merge. W1 is disabled unless
`MADEIRA_SRV_COALESCE=1`; invalid/unset values retain the old path. X1 now disables
its three task-wide profilers by default; its documented flags opt them in.
No cache, JIT block size, QoS or worker-count default was changed.

## Validation and remaining work

The updated integration passes the harness host suite and has a linked, signed,
installed Debug measurement app. Its isolated native inputs were copied from
established builds; current winemetal, ntdll server and wineserver fd objects were
replaced, and win32u was rebuilt with the existing local OpenGL patch. This is
not a clean rebuild of all native dependencies. The Wine worktree intentionally
has that local patch applied; its pinned gitlink remains unchanged. Actual
archive and binary hashes live in private build/input reports beside the worktree.
Dock and the i386/ARM64EC/WoW64 payloads are present; the installed 32-bit Portal
launches through the normal Dock/JIT path. Do not generalize this runtime proof
to other games or payload combinations.

Physical delivery on 2026-10-10: menu capture exported 600 events over ten seconds;
existing-save gameplay exported 899 over fifteen seconds. Thirty-second captures exported 1,799 events with matching CPU and footprint
sidecars. Earlier mode-0 reports were not accepted as native experiment proof
after duplicate archive entry-point owners were discovered. Keyboard/menu navigation, existing-save load, relative mouse camera
response and native host-timeout interruption were observed. All 13 original save
files match private backups; the test also created a new save and auxiliary files,
which remain preserved. Virtual-pad stick response was not observed. Focus-loss
injection, independently verified release behavior, observer overhead, calibrated
clocks and representative paired/sustained performance acceptance remain open.

Both normal signed Debug and Release builds with the original native Present
source passed actual automation-marker exclusion before the later read-only wake
policy accessor was added. Signed Debug capture builds include that accessor. Corrected single-owner native
archives also passed normal signed Debug and Release automation exclusion.
No telemetry is interpreted as visible-frame timing, GPU execution or per-role
CPU attribution. CPU boundary totals cover the whole app, including its UI work.
The initial static saved-scene W1 trial is preliminary and changes no default.
A requested-on arm that reported native mode 0 was excluded from A/B results.
PR27 now applies a bounded explicit startup argument and reports requested/current
values; private runs also verify the initialized native policy after capture.
An early mode-0 capture exported 1,799 samples, p95 16.817 ms, p99 16.974 ms
and 0.456 mean whole-app CPU cores over a 30-second window. Its archives had
duplicate ntdll/wineserver entry-point owners, so it establishes telemetry delivery
only. Corrected archives remove both legacy/current object names before insertion,
apply the wineserver symbol renames, and pass native entry-point ownership checks.
New matched controls are required before drawing any optimization conclusion.
W1 comparisons keep X1 profiler settings identical; they are W1 baselines, not an
untouched upstream baseline for evaluating X1. For X1 compare all three profiler flags on
against all off, with W1 and every other setting held identical.

Bounded neutral replay plans live in `automation/scenarios`. The sustained
900-second plan requires warmup before starting its window; the combined replay
limit is 900 seconds. Scene readiness must be established separately. A traced
menu, sleep or a single short pair cannot establish a performance improvement.

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

## Command transport follow-up

The inherited XCTest command text field is a prototype transport. JSON entry and
keyboard dismissal happen before measured replay; capture runs natively with
Refresh heartbeats. This avoids typing inside the measured window, but repeated
UI control still changes focus and adds app/UI overhead. There is no existing
app command socket; the debugger/JIT connection is not a gameplay control protocol.
Before long campaigns, replace repeated text-field control with a Debug-only
bidirectional channel forwarded over USB, retaining the current validated request
schema, correlation ledger, owned-session checks and stop/watchdog semantics.
Use a private per-process capability, bounded messages and loopback-only endpoints;
retain XCTest for visual checkpoints/JIT interaction. This transport is planned,
not implemented or physically verified by the present results.

## Verified W1 pilot after archive correction

The same signed app completed mode 1 and mode 0 captures after native archive
entry-point ownership was corrected and audited. Each used the same preserved
Portal chamber-00 test save, neutral input, 15-second warmup and 30-second capture.
The game-region image comparison passed with zero pixels exceeding its threshold;
both traces contain 1,800 events, no loss, and matching native policy metadata.
Off: p95 16.735 ms, p99 16.945 ms, mean whole-app CPU 0.4462 cores.
On: p95 16.757 ms, p99 16.958 ms, mean whole-app CPU 0.4442 cores.
This single static pair establishes the experiment pipeline; it does not show an
accepted performance improvement. Defaults and issue acceptance remain unchanged.
The source, archive hashes, metrics and limitations are frozen in
`performance-pilot-2026-10-10.json`. Earlier ambiguous-archive runs are excluded.

Next: replace repeated XCTest JSON text entry with the USB command transport
before a longer representative gameplay campaign; verify watchdog/input-release
behavior on that transport; obtain repeated paired baselines; then test X1, W1,
G1 and eligible F2 settings independently. G2 patches remain unapplied.
