# Physical iPad smoke test

## Current validation boundary

The controller's HTTP protocol and failure handling are tested with a fake
Appium server. Mac compilation/signing and binary guard checks are now verified;
see [Mac validation](mac-validation.md). Physical smoke and JIT coexistence
remain unverified. Run the following on your Mac. First provisioning,
onboarding and any OS trust prompts require a person. The controller does not
accept those prompts, change accounts, erase data or install certificates.

## One-time preparation

1. Install Xcode compatible with the actual iPadOS version; accept its license,
   install platform support and select it with xcode-select. Verify
   `xcodebuild -version`, `xcrun devicectl help`, and
   `xcodebuild -list -project app/Madeira.xcodeproj`.
2. Connect an unlocked M-series iPad over USB. Trust/pair it with this Mac,
   enable Developer Mode, provision a development signing certificate with
   get-task-allow and the memory entitlements Madeira needs. Use your own team
   and bundle prefix for both Madeira and its helper. Complete normal Madeira
   onboarding. Do not alter Steam accounts to run a smoke test.
3. Provision WebDriverAgent for this same iPad/team using Appium's real-device
   setup documentation. Set a unique WDA runner bundle ID associated with your
   profile. Trust/enable its developer app if the device asks. WDA first launch
   may require additional Xcode/manual setup; stop and resolve it rather than
   retrying indefinitely.
   On the iPad enable **Settings → Developer → Enable UI Automation** and keep
   the device unlocked. The actual first run here compiled/installed WDA but
   failed during XCTest initialization with “Timed out while enabling automation
   mode.” This one-time device setting is required by Appium's
   [device preparation guide](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/device-setup/).
4. Install Python 3.10+ and Node 24 (or a compatible engine listed in
   automation/package.json). From repository root run `make automation-setup`.
   Appium 3.8.0 / XCUITest 12.16.0 are pinned with npm's lockfile; the driver
   requires Appium 3. pymobiledevice3 is deliberately optional: no capability in
   the first proof requires another device-management stack.

```sh
export MADEIRA_TEAM_ID=YOUR_TEAM_ID
export MADEIRA_BUNDLE_ID=your.development.madeira
export MADEIRA_WDA_BUNDLE_ID=your.development.WebDriverAgentRunner
# Device list reports hardware UDID separately from CoreDevice identifier.
automation/.venv/bin/python -m automation.controller.cli doctor
automation/.venv/bin/python -m automation.controller.cli devices
export MADEIRA_DEVICE_UDID=YOUR_IPAD_UDID
make device-check
```

Unknown pairing/Developer Mode/schema information fails closed. Discovery
includes wired/network transport rather than pretending every paired device is
connected. Physical CLI commands default to `--transport wired` and reject a
device reached over Wi-Fi. Explicit `--transport localNetwork` enables later
network work; investigate that transport before drawing conclusions about USB.

## Build and install

Assemble Madeira's dependencies per `docs/BUILDING.md` first. This harness does
not download missing proprietary redistributables or change the component build
order. A clean checkout does not include every necessary build input.

```sh
make device-build
make device-install APP="$PWD/automation/derived-data/debug/Build/Products/Debug-iphoneos/Madeira.app"

# Debug-only JIT probe, in a separate output directory:
make device-build BUILD_FLAGS="--automation"
# Compile/check Release without enabling the probe:
make device-build BUILD_FLAGS="--configuration Release"
# Compile and inspect without signing (cannot be installed):
make device-build BUILD_FLAGS="--unsigned"
```

Build selects the existing Madeira scheme, overrides team and bundle ID, and
uses separate `debug`, `automation-debug`, and `release` derived data by default.
`--derived-data` selects another dedicated directory. On this Mac the existing
native components require `--setting MTL_LANGUAGE_REVISION=Metal31`; pass that
through BUILD_FLAGS. `--automation --configuration Release` is rejected.
Successful builds verify the actual compiled app's probe inclusion/exclusion,
record binary SHA-256 values, and verify signed bundles with codesign.
Signed builds clean only that variant's isolated products first: the existing
bundle scripts rewrite nested resources on incremental builds, and Xcode can
skip the outer CodeSign, producing an invalid resource seal despite reporting
BUILD SUCCEEDED. Unsigned compilation can remain incremental.
Build reports and owner-only compiler logs are retained under
`automation/runs/builds/`, including failures. Compiler output stays local.
Signing must already be provisioned; automatic account/provisioning changes are
not enabled. If signing fails, inspect the private build log locally. A separate
automation bundle ID requires its own provisioning profile with Increased Memory
Limit; a wildcard profile alone lacks this entitlement. Complete that one-time
Xcode provisioning with your developer account before a signed harness build.
Native install accepts a signed .app directory and verifies its bundle ID before
installation. It inspects the installed target's bundle URL and processes and
refuses to install over a running target. IPA unpacking/install is not implemented; use the .app from your
build (do not uninstall an existing app, which would erase its data).

If Xcode's UI shows a signed-in developer account but xcodebuild still reports
“No Accounts,” create the dedicated test bundle's development profile through a
Build in Xcode's UI, using your team and the Increased Memory Limit capability.
The CLI can then sign with that existing profile without automatic account
changes. This was the successful provisioning route on this Mac.

## First end-to-end proof

All physical CLI commands use the [shared device reservation](device-reservation.md)
before installation or Appium connection. Competing worktrees fail immediately
instead of taking the device from a live run. Performance tools must use the same
reservation; see issue #2. Do not delete its persistent lock files.

In one terminal:

```sh
make automation-server
```

In another, from the repository root with the same environment:

```sh
make device-smoke-test
# For Madeira's alternate developer interface:
automation/.venv/bin/python -m automation.controller.cli smoke --frontend developer
```

Madeira must be stopped before smoke begins, so an active game is never killed
by a smoke-test preflight. The library smoke selects Library, takes a screenshot, opens Settings, finds the
existing JIT setup button without activating it, returns to Library, verifies
its selected state, takes another screenshot, collects diagnostics and
terminates Madeira. The developer variant opens/closes All settings. Explicit
accessibility identifiers have been added to these existing controls; their
propagation through SwiftUI's iPad tab bar still needs physical verification.
Do not substitute guessed coordinates and call that a validated identifier test.

Reports are timestamped under automation/runs with owner-only permissions and
ignored by Git. JSON stdout gives pass/fail and report path; exit 0 = passed,
1 = attempted workflow failed, 2 = blocked/prerequisite error. Screenshot names
are tied to the run timestamp. Failure diagnostics run before termination; a
failed evidence collector is recorded independently. App state 1 means not
running; unexpected termination does not prove a crash. Historical device crash
report counts are explicitly unattributed. App/system logs export only a fixed
vocabulary of known Madeira diagnostic events, not complete log text. Screenshots
can show private UI; keep them local and do not capture sign-in screens.
If session creation fails, the controller also inspects this run's local XCTest
result bundle and retains fixed failure codes, such as
`ui_automation_mode_timeout`, without exporting arbitrary diagnostic text.

## Agent UI commands

An actions file runs in one persistent Appium session. It never implicitly
restarts the application (which could lose JIT). Session deletion leaves the
app's lifecycle as the actions specified.

```json
[
  {"action":"launch"},
  {"action":"tap_id","id":"madeira.tab.settings"},
  {"action":"inspect"},
  {"action":"screenshot"},
  {"action":"tap_id","id":"madeira.tab.library"},
  {"action":"terminate"}
]
```

```sh
automation/.venv/bin/python -m automation.controller.cli actions /path/to/actions.json
```

Other supported actions: tap(x,y), swipe(start,end,duration), scroll(direction),
text(id,text), state. Coordinates use XCTest screen points, not PNG pixels.
Inspection exports types, bounds, and Madeira identifiers, never arbitrary UI
text. Use actions only for the intended test; do not place credentials in fixtures
or automate purchases/account changes. UI control is powerful and cannot infer
whether an arbitrary screen coordinate is a purchase button.

Recovery is bounded: capture diagnostics, attempt lifecycle cleanup, stop. No
automatic app retries, reinstalls, JIT retries, VPN switching or destructive
cleanup. Resolve hardware/provisioning failures, then start a fresh test run.

## References

- https://appium.github.io/appium-xcuitest-driver/latest/getting-started/installation/
- https://appium.github.io/appium-xcuitest-driver/latest/getting-started/real-device-config/
- https://appium.github.io/appium-xcuitest-driver/latest/reference/capabilities/
- https://appium.github.io/appium-xcuitest-driver/latest/reference/execute-methods/
- Native command/schema reference on the actual Mac: `xcrun devicectl help`.

Appium is bound to loopback without relaxed-security. The client rejects remote
hosts and redirects. A local OS user with access to Appium has device control;
this is a trusted development Mac, not a public service. No on-device network
endpoint is introduced.

## Offline screenshot comparison

```sh
automation/.venv/bin/python -m automation.controller.cli compare-images baseline.png candidate.png --pixel-threshold 20 --changed-fraction 0.1
# Optionally isolate the game rectangle in image pixels, excluding OS chrome:
# --crop LEFT TOP RIGHT BOTTOM
```

Uses a small blur plus changed-pixel fraction to tolerate antialiasing changes.
Different resolutions are inconclusive. Suspected black/uniform captures are
flagged for review, even against an equally blank baseline. Dark scenes and
loading screens are not automatically rendering failures; inspect the image.
Coordinates for crop are image pixels, unlike XCTest's UI screen points.

Physical pytest wrappers are skipped by default. After successful setup:

```sh
MADEIRA_RUN_PHYSICAL=1 make automation-test
# Separately, only with the opted-in Debug build and JIT configured:
MADEIRA_RUN_JIT_PHYSICAL=1 make automation-test
```

These run the same CLI workflows and require a running Appium server. Ordinary
`make automation-test` performs host-only validation and does not touch a device.
