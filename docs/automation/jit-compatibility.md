# JIT / WebDriverAgent compatibility

**Result: built-in JIT + responsive WDA + x86 exit 42 observed on the M5 iPad.**
The standalone probe also observed a new PID and successful JIT reactivation after
restart. Two consecutive runs of the final native-launch/cleanup variant pass,
followed by a normal UI smoke pass. This is not normal-game or post-detach
compatibility; those matrix rows remain untested.

## Established by source inspection

- JITCoordinator uses StikDebug or the built-in MadeiraJITHelper extension. Both
  use the existing Madeira script. No new debugger attach strategy was added.
- StikJITHelper.ready checks CS_DEBUGGED and, with the current attach-check option,
  either an attached debugger or an allocated pool. A sticky flag alone can be
  insufficient. Disabling the existing attach check weakens this observation;
  keep Madeira's normal default for compatibility experiments.
- Pool/PE setup uses the debugger; `allocateAndDetach`'s name is misleading: its
  implementation explicitly postpones detach. ContentView detaches at selected
  later points in normal launch. Automation must not detach it arbitrarily.
- Process restart loses process-local pool/runtime state. Recheck after every
  restart rather than caching success on the Mac.
- The current normal `fex_test_execute` loads Hello World ELF and expects exit 0.
  The initial Swift/probe expectation of 42 was stale and caused a real false
  failure. The opted-in Debug probe now selects a freestanding sys_exit(42) ELF
  through the same loader, context, allocator and syscall path. No FEX submodule
  implementation changed. The fixture and native entry point are compiled out
  of normal Debug and Release, and the normal developer UI recognizes exit 0.
- LocalDevVPN's app link opens its UI. The optional Madeira JIT Shortcut can
  change network/VPN state through the existing workflow. This is not proof a
  newly installed device can do it without permission prompts. No VPN or mobile
  data setting is changed by this harness outside the normal enabled JIT flow.

## Runnable experiment

After the smoke test passes, create a development build with both compile flags:

```sh
make device-build BUILD_FLAGS=--automation
make device-install APP="$PWD/automation/derived-data/automation-debug/Build/Products/Debug-iphoneos/Madeira.app"
# Madeira must be stopped first; the probe refuses to kill an existing game.
make jit-test
```

The probe launches with `--madeira-automation`; ordinary Debug builds lack the
MADEIRA_AUTOMATION flag and cannot expose the interface. Production Release
builds lack DEBUG and the test symbols are conditionally excluded. The interface
has no HTTP/socket listener; it is accessible through the already-provisioned
XCTest/WDA channel. See protocol.md.

The test creates an Appium session without auto-launching/resetting Madeira,
launches Madeira explicitly, reads a fresh structured status, presses its
existing enableJIT operation, repeatedly verifies foreground status refresh and
JIT readiness, invokes the existing FEX developer test, requires the observed
return value 42, captures evidence, stops its owned probe through devicectl, clears XCTest launch registration,
relaunches and verifies a new PID
and clean FEX-test state. It records whether JIT needed reactivation, then tests
reactivation if required. Any failed operation or timeout fails the run.

StikDebug/Shortcuts may take foreground. The probe observes this and attempts
`activateApp` after 10 seconds in background; this is NOT a process relaunch or
readiness heuristic. Whether foreground changes disrupt the helper is itself an
unverified part of this experiment. No readiness success depends on elapsed time.
A stalled setup dialog, untrusted developer app or lost session stops the test
with diagnostics. A second fresh run is a manual developer decision, not an
unbounded retry.

## Hardware experiment matrix

Repeat each row on the actual M-series iPad. Record Xcode/Appium/WDA versions,
iPad model/OS, transport, signing method and Madeira commit alongside report.json.

| Experiment | Evidence needed | Current result |
|---|---|---|
| WDA + built-in StikJIT | Responsive status sequence, JIT fields, x86 return 42 | OBSERVED: builtIn, attached debugger, fresh status, FEX PASSED/42 |
| WDA + StikDebug | Same, including successful foreground return | NOT DETECTED by app; no attempt |
| Debugger attach impact | Appium latency/responsiveness during attach | Fresh status/screenshot control observed with debugger attached; host round trips recorded |
| Debugger detach survival | Normal launch's detach then successful guest execution/input | NOT RUN; standalone FEX probe does not claim this |
| App restart | New PID, readiness recheck, successful reactivation | OBSERVED: new PID, initially not ready, built-in reactivation; two consecutive native launch/cleanup passes |
| VPN already connected | Native JIT succeeds without network change | OBSERVED: existing connected LocalDevVPN path; no Shortcut configured in separate app |
| Shortcut connect/restore | User-configured Shortcut completes without permission dialogs, expected network restored | NOT RUN |
| Install/reinstall | Existing data preserved; any trust dialogs recorded | Owned fixture preserved in A1; pairing migrated into separate app Keychain and survived reinstall |

Initial trust/pairing, Developer Mode, developer signing, WDA provisioning,
Madeira onboarding, JIT pairing/DDI setup, and optional Shortcut installation may
need a person. Their exact recurrence depends on the device and signatures and
has not been measured here. Credentials and pairing files are never exported.

If coexistence fails: capture diagnostics before recovery; separate activation
and UI-control stages, reconnect WDA without restarting Madeira, or retain the
XCTest-accessible internal control surface. Do not add platform bypasses or an
unauthenticated listener. Do not implement a large game benchmark framework on
an assumed successful JIT milestone.

## Physical evidence and integration fixes: 2026-10-10

Mac/Xcode/Appium/device preparation is recorded in mac-validation.md. Separate
A2 worktree/branch: `codex/a2-ipad-jit-coexistence`, stacked on A1 `5c1a30e`.
The initial setup failure did not establish a coexistence fault: the fresh app
had no pairing record, and StikDebug was not detected. Its normal setup sheet
hid the probe. The controller now classifies this as `jit_setup_required` rather
than a generic missing element, without dismissing prompts or exporting text.
The existing local pairing file was imported through Madeira's existing legacy
Keychain migration. A native file listing confirmed zero remaining Documents
pairing-file entries. No pairing bytes were logged, committed or uploaded.

The first provisioned run (`20261010T063953.277174Z-48a46f43`) observed built-in
JIT ready, a live debugger and responsive status, but the current Hello World
ELF returned 0, so the old expected-42 probe failed correctly. It also observed
an XCTest termination timeout. The explicit exit-42 fixture was disassembled on
the Mac (mov eax,60; mov edi,42; syscall; unreachable ud2), then compiled/signed
and installed. No change to the FEX engine or guest loader's execution strategy
was needed. The expected result is the observed guest sys_exit value, not a
host-side synthesized success.

Run `20261010T064808.370816Z-1848a010` observed exit 42 and fresh-process
reactivation but failed final cleanup because process discovery included the
helper under PlugIns. Native main-app PID matching now excludes extension paths
and checks the exact bundle and reported probe PID before stopping it. A
suspended main process still blocks startup; an extension alone does not.
Run `20261010T065023.451233Z-91477fd4` passed every probe/cleanup step, with fresh
PID and reactivation required. Its three status refresh round trips were
831.99–1823.27 ms, all with a live debugger. These are host command round trips,
not frame time, attach duration or CPU/GPU measurements. Full raw reports,
screenshots and private device identifiers remain local under automation/runs.
A subsequent attempt preserved a newly observed background main process and
refused startup. Cleanup is being checked across repeated sessions, including
clearing XCTest's process registration after the native stop. A later launch
failed with iPadOS CoreDevice `Locked`, confirmed by a black screenshot and
`passcodeRequired=true` (despite `unlockedSinceBoot=true`). This does not
establish a stale XCTest launch-cache fault. The final native launch variant
was then host-tested and awaiting owner unlock; its subsequent acceptance is
recorded below. It records
the fresh PID directly and compares it with the probe snapshot before JIT.
All physical CLI mutations now check the current unlock gate under reservation
and return `device_locked_requires_owner_unlock` before creating a session.

At compiled app commit `273df26`, signed normal Debug, opted-in Debug and Release
all passed strict signature verification. Binary inspection confirms both probe
identifier and native fixture symbol are present only in opted-in Debug. The
installed executable SHA-256 is
`9aaaab970327f3080697850b42fb48db54f5e4739ee26cd367aefdf4de1f73d1`,
and Debug dylib SHA-256 is
`143c38e6d9db27dc9f82b9b82789fc56fc718fa5c304e5a524a932c53fcdbfd3`.
Builds reuse the existing local native inputs; the new fixture runs through the
app's existing bridge. All changes are outside the FEX/Wine/DXMT submodules.

Normal-game detach survival, guest execution after that detach, configured
Shortcut connect/restore and StikDebug remain unverified. This probe does not
claim game readiness, rendering, virtual input or benchmark compatibility.

Host validation: 62 tests pass, 2 physical pytest wrappers skip. The direct
physical results above are separate from that count. No passcode is accepted,
stored or injected; owner unlock remains an explicit device prerequisite.

## Consecutive acceptance after watchdog lifetime fix

The unlocked native-launch run `20261010T070810.167659Z-3c8b1fde` reached
attached JIT and logged guest exit 42, then the main app terminated before its
next status read. Cleanup succeeded. No attributable fresh crash report was
found, so the exit cause remains unconfirmed. Source inspection found an
existing detached test-watchdog thread capturing a stack atomic and reading a
Thread that the test destroys. The app bridge now signals and joins that
watchdog before destroying its state. This corrects its lifetime independently
of whether it caused the observed exit; the FEX submodule is unchanged. A
termination racing a status refresh now reports a terminated process rather
than a generic missing UI element.

At clean source `3216acc6d1d0e3e4fb6c7d8aabdf2886b99fef5c`, both
`20261010T071110.833633Z-616a4f3c` and
`20261010T071204.974062Z-135aa9da` passed every step consecutively without human
preparation between them. Each observed built-in JIT, a live debugger, FEX
PASSED/42, a new PID, initially absent JIT readiness after restart, successful
reactivation and confirmed native cleanup. The following normal library smoke
`20261010T071245.940352Z-1255175e` also passed. The six attached-debugger UI
refresh round trips ranged from 751.59 to 1898.39 ms; these are host command
round trips, not game metrics.

All three signed variants at this clean commit pass strict signature and
compiled-surface checks. The latest installed automation executable SHA-256 is
`2fa02cdcee1bb182e274092b5e08d280360aef717fe5636c704878eb18e8f658`,
and its Debug dylib SHA-256 is
`c2a3202428b8e4188c8bdf7db4f612a0c2bdce615d68560e091c7955dbe4e303`.
The normal Debug and Release binaries exclude both the probe identifier and
native automation fixture. Existing normal SSD app/data remain untouched.
The owner subsequently selected local storage instead of the SSD. Portal is
installed in the existing app's internal Steam library as the next lifecycle/input
target; no full-game result is claimed by the standalone JIT runs.
