# Mac validation: 2026-10-10

Related issues: #9 (Mac/physical smoke), #2 (shared reservation), #10 (JIT).
Automation base: `2d152014038bd64e363b459acdaec0551aaac5f6`.
Reservation prerequisite: `6dbeafe9a92816e01f97016102b05d40a7365082` / PR #16.

## Verified host preparation

- macOS 27.0, Apple Silicon; Xcode 27.0 build 27A266a.
- Harness venv Python 3.14.7; Node 26.5.0; npm 11.17.0.
- Locked npm dependencies: Appium 3.8.0, XCUITest 12.16.0.
- Xcode reports Madeira and MadeiraJITHelper schemes. Appium's XCUITest doctor
  reports zero required fixes. Optional applesimutils is absent; simulator
  permission changes are outside this physical test.
- Local native component archives, generated FEX headers and ignored runtime
  resources were reused from the earlier native build in an independent
  checkout using APFS clones. No FEX/Wine/DXMT implementation edits or component
  rebuilds were made. Archive hashes and source checkout provenance are retained
  privately in `automation/runs/preparation/native-inputs.json`. This is an app
  rebuild against local component inputs, not a clean toolchain rebuild.

## App compilation, signing and packaging checks

Normal Debug, automation Debug and Release successfully compile and sign using
an existing development profile. The signed bundles pass
`codesign --verify --deep --strict`. Inspection of the app executable and Debug
dylib confirms the automation status identifier is included in automation Debug
and absent from normal Debug and Release. Release gameplay is still untested.
The existing component build uses `MTL_LANGUAGE_REVISION=Metal31`.

The build CLI now records source commit/dirty status, binary hashes and private
compiler logs, including failures. It isolates each build variant and rejects
enabling the automation probe in Release. New compiled-artifact tests detect an
unexpected probe in a normal artifact and a missing probe in a test artifact.
An additional incremental signed rebuild reported BUILD SUCCEEDED but failed
strict signature verification with an invalid sealed resource. The existing
bundle scripts re-sign/rewrite nested resources while Xcode can omit the outer
CodeSign on incremental runs. Signed harness builds now clean only their isolated
variant products before rebuilding and verifying; shared component inputs remain
intact. This failure was detected before any installation of that artifact.

Representative commands (team and bundle names are local provisioning choices):

```sh
make automation-setup
automation/.venv/bin/python -m automation.controller.cli doctor
make automation-test
make device-build BUILD_FLAGS="--setting MTL_LANGUAGE_REVISION=Metal31"
make device-build BUILD_FLAGS="--automation --setting MTL_LANGUAGE_REVISION=Metal31"
make device-build BUILD_FLAGS="--configuration Release --setting MTL_LANGUAGE_REVISION=Metal31"
```

WebDriverAgentRunner also successfully builds for generic iOS, signs with the
existing wildcard development profile, and passes deep/strict signature
verification. Its isolated output is `automation/derived-data/wda`. This does
not establish a successful XCUITest session on the iPad.

## Device inventory and remaining gates

Read-only devicectl discovery sees an iPad Pro 11-inch (M5), iPadOS 26.7, paired,
Developer Mode enabled, connected over localNetwork. Installed-app/process JSON
schemas were inspected under the shared reservation. An existing SSD test app is
running; it was neither replaced nor terminated. Install preflight now matches
the requested bundle's installed URL against running executables and rejects
replacement while that target is running.

USB/wired transport is now confirmed. The CLI defaults to wired transport and
refuses a Wi-Fi-only connection unless explicitly selected. The separate
automation app successfully installed. No UI smoke or JIT success is claimed.

A separate automation app needs an Increased Memory Limit provisioning profile.
The initial signed build failed because the wildcard profile lacked this
capability. Even after account sign-in was visible in Xcode Settings, xcodebuild
reported “No Accounts.” A Build through Xcode's UI in an isolated local signing
project created the dedicated Increased Memory Limit profile. The full
automation app then built and verified successfully through the CLI using that
existing profile. The owner's SSD test app was neither replaced nor terminated.

First physical attempt: app install succeeded; Appium session creation failed.
The local XCTest result records “The test runner failed to initialize for UI
testing. (Underlying Error: Timed out while enabling automation mode.)” The
iPad's Settings → Developer → Enable UI Automation setting has been requested
from the owner before another bounded attempt. Failed-run report and original
xcresult remain local. Startup reports now classify this failure as
`ui_automation_mode_timeout` without exporting raw diagnostic text.

Second physical attempt at source commit `d3ac8d154a5079d9bb38a582fc355f2074ec28ea`:
the owner confirmed UI Automation enabled, but XCTest failed with the same
`ui_automation_mode_timeout`. The private run is
`automation/runs/20261010T062443.608495Z-88a45f71/report.json` with its current-run
xcresult and exported diagnostics retained locally. Device inventory confirms
wired transport; a subsequent lock-state query reports `passcodeRequired=false`
and `unlockedSinceBoot=true`. Native testmanagerd connected and authorized the
runner successfully; the runner then timed out waiting for automation mode.
No Madeira launch, UI action or JIT attempt occurred. No WDA runner process
remained after failure. These observations do not prove whether an additional
on-device XCTest permission/passcode prompt was present. The owner has been asked
to check for that prompt before another attempt. The timeout alone must not be
reported as proof that the UI Automation switch is disabled.

The installed XCUITest/Xcode/device versions fall within Appium's published
[support ranges](https://appium.github.io/appium-xcuitest-driver/12.15/getting-started/system-requirements/).
This does not rule out a device or toolchain fault. No dependency downgrade,
security bypass, device restart or existing-app termination was performed.

Host validation: 47 tests passed, 2 physical pytest wrappers skipped. Additional
HTTP fixture cases exercise failed launch, a launch that leaves the app stopped,
lost session, failed termination and missing-device selection. They confirm bounded
failure reports, session cleanup and private-error filtering; they are host
coverage, not physical failure-injection evidence. Both actual physical CLI
attempts above failed independently of the host pass count.
Next: resolve the XCTest initialization gate, repeat smoke, verify identifiers
and data protection, then continue to JIT coexistence. Onboarding/trust prompts
remain manual.

Keep #9 open until physical smoke, active-game/data preservation and failure
acceptance are evidenced. #10 JIT coexistence and subsequent lifecycle/input/
benchmark acceptance remain unverified.
