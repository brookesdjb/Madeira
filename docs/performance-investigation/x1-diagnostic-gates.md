# X1 task-wide diagnostic gates

Tracks [fork issue #3](https://github.com/brookesdjb/Madeira/issues/3).

The three task-wide background diagnostic jobs in `server_ios.c` are disabled
by default. Each has an independent explicit opt-in:

| Environment switch | Existing job |
|---|---|
| `MADEIRA_PROFILE_THREADS` | Thread/guest sampling bursts, including diagnostic thread suspension |
| `MADEIRA_PROFILE_XP` | 250 ms task/thread transition and usage probe |
| `MADEIRA_PROFILE_STACKS` | Submission-worker stack sampling bursts |

Enable with `1`, `on`, `yes` or `true` (words are case-insensitive). Unset,
empty, false and unknown values disable the job. Whitespace is not trimmed by
the native parser. The existing app configuration parser trims values before
exporting them.

For example, diagnostic sessions can use existing `Documents/madeira.cfg`:

```ini
env.MADEIRA_PROFILE_THREADS = 1
env.MADEIRA_PROFILE_XP = 1
env.MADEIRA_PROFILE_STACKS = 1
```

Set only the jobs needed for an investigation. All three settings are read
before dispatching any jobs at the first Wine process-init completion, and a
`pthread_once` owner queues each selected job once per native app process.
Additional Wine pseudo-processes cannot duplicate or change them. Fully restart
Madeira after changing configuration. Enabled settings produce one
`[task-profile] enabled: threads=... xp=... stacks=...` startup line; default-off
queues no jobs and emits no new profiler startup line. Existing diagnostic
worker bodies, role registration and counters are unchanged.

The switches work independently of `MADEIRA_QUIET`: explicit opt-in can run while
the app's quiet default remains set. Quiet continues to control the separate
legacy `[PROF]` sampler. The existing initialization watchdog, crash/exception
handling, recovery, role-registration logging and user-selected overlay are
unchanged. This is a focused gate on three recurring jobs, not a claim that all
diagnostic overhead is removed. Stack sampling requires a registered submission
worker; games without that role may yield no stack samples.

## Validation performed

From `Madeira-perf-x1` on the preparation Mac:

```sh
python3 tests/host/check-task-profilers.py
git diff --check
```

The test compiles the production startup policy with stub dispatch/workers under
ASan/UBSan. It covers 48 cases: all eight job combinations, accepted/invalid
values, and quiet unset/set. Each case invokes startup from 32 concurrent clients,
100 calls each, then changes the environment and checks that no jobs are added or
duplicated. These checks establish host policy behavior; they do not run Mach
sampling or demonstrate real diagnostic output.

The full changed `server_ios.c` compiled to an arm64 iOS object with the recipe's
compiler options plus explicit `-fblocks`, using read-only configured Wine
headers from the existing SSD checkout at pinned Wine commit
`257f271cfffed9f22f7987cac53bc00095d092fe`. It produced two existing
`%{public}s` format warnings outside this change. Compilation is not app linking,
installation, game acceptance or a measured performance gain. No shared archive,
DLL farm, automation source or device state was modified.

Local compilation command, log and object hash are recorded privately under
`diagnostics/performance-x1-2026-10-10/` alongside the worktrees. Generated
artifacts are excluded from this change.

## Remaining device acceptance and rollback

After the harness's game lifecycle and telemetry gates pass, use its existing
shared reservation and establish source/config/installed-binary identities.
Verify normal launch, graceful exit and crash/recovery with jobs off and on;
confirm default-off has no launches from these three jobs and explicit opt-in
produces the expected existing diagnostic traces. Include a pseudo-process/helper
case to confirm one task-wide owner. Enabled workers retain their existing shared
diagnostic state and limitations; this change does not make their counters a new
validated telemetry contract.

Measure off/on observer cost using raw frames, per-role CPU and thermal state,
then keep the same sampler policy in both arms of other optimization experiments.
Use issue #2's paired and sustained protocol. No device measurements have been
performed for this patch, so performance acceptance remains open.

To restore the previous three always-on jobs, enable all three switches and
restart the app. To return to the new normal default, remove them or set each to
`0`, then restart. Revert the X1 commit to restore the previous startup code.
