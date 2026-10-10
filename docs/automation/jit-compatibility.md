# JIT / WebDriverAgent compatibility

**Result: UNKNOWN — no physical iPad or Mac was available.** Mock tests below
exercise orchestration only. There is no claim that WDA and JIT currently coexist.

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
- FEX's existing developer test executes a bundled x86-64 ELF and reports its
  exit result through `fex_test_execute`; the Swift test expects 42. The header's
  short mov/ret description is older than the ELF loader implementation.
- LocalDevVPN's app link opens its UI. The optional Madeira JIT Shortcut can
  change network/VPN state through the existing workflow. This is not proof a
  newly installed device can do it without permission prompts. No VPN or mobile
  data setting is changed by this harness outside the normal enabled JIT flow.

## Runnable experiment (NOT yet run on hardware)

After the smoke test passes, create a development build with both compile flags:

```sh
make device-build BUILD_FLAGS=--automation
make device-install APP="$PWD/automation/derived-data/Build/Products/Debug-iphoneos/Madeira.app"
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
return value 42, captures evidence, terminates/relaunches and verifies a new PID
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
| WDA + built-in StikJIT | Responsive status sequence, JIT fields, x86 return 42 | NOT RUN |
| WDA + StikDebug | Same, including successful foreground return | NOT RUN |
| Debugger attach impact | Appium latency/responsiveness during attach | NOT RUN |
| Debugger detach survival | Normal launch's detach then successful guest execution/input | NOT RUN; standalone FEX probe does not claim this |
| App restart | New PID, readiness recheck, successful reactivation | NOT RUN |
| VPN already connected | Native JIT succeeds without network change | NOT RUN |
| Shortcut connect/restore | User-configured Shortcut completes without permission dialogs, expected network restored | NOT RUN |
| Install/reinstall | Existing data preserved; any trust dialogs recorded | NOT RUN |

Initial trust/pairing, Developer Mode, developer signing, WDA provisioning,
Madeira onboarding, JIT pairing/DDI setup, and optional Shortcut installation may
need a person. Their exact recurrence depends on the device and signatures and
has not been measured here. Credentials and pairing files are never exported.

If coexistence fails: capture diagnostics before recovery; separate activation
and UI-control stages, reconnect WDA without restarting Madeira, or retain the
XCTest-accessible internal control surface. Do not add platform bypasses or an
unauthenticated listener. Do not implement a large game benchmark framework on
an assumed successful JIT milestone.
