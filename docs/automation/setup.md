# Physical iPad smoke test

## Current validation boundary

The controller's HTTP protocol and failure handling are tested on Linux with a
fake Appium server. No physical iPad run or Xcode compile has occurred in this
implementation session. Run the following on your Mac. First provisioning,
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
connected. The initial proof should use `transport: wired`; investigate any
network transport before drawing conclusions about USB behavior.

## Build and install

Assemble Madeira's dependencies per `docs/BUILDING.md` first. This harness does
not download missing proprietary redistributables or change the component build
order. A clean checkout does not include every necessary build input.

```sh
make device-build
make device-install APP="$PWD/automation/derived-data/Build/Products/Debug-iphoneos/Madeira.app"
```

Build selects the existing Madeira scheme and Debug configuration, overrides
team and bundle ID, and uses dedicated derived data. Signing must already be
provisioned; automatic account/provisioning changes are not enabled. If signing
fails, run the documented xcodebuild command locally to inspect private errors.
The CLI suppresses arbitrary compiler/tool output to avoid exporting credentials.
Native install accepts a signed .app directory and verifies its bundle ID before
installation. IPA unpacking/install is not implemented; use the .app from your
build (do not uninstall an existing app, which would erase its data).

## First end-to-end proof

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

The library smoke selects Library, takes a screenshot, opens Settings, finds the
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
