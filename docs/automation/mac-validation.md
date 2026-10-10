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

## Successful physical smoke and preservation checks

After the owner approved the additional on-device XCTest prompt, WDA connected
and Madeira launched successfully. The first UI run stopped at optional
first-run onboarding and retained a screenshot before terminating the target.
The separate test app's existing “Skip setup” control was used once, without
Steam sign-in or downloads. Initial trust/provisioning is separate from the
subsequent unattended proof.

At clean harness commit `2c79231`, the acceptance run
`automation/runs/20261010T063419.960664Z-ab9d60a0/acceptance.json` passed:

- A harness-owned Documents file survived signed reinstall with identical SHA-256.
- Install and smoke refused a preexisting running target. Its foreground state
  remained 4 after refusal; only the test's own launched process was then stopped.
- Library → Settings → Library passed twice using visible stable identifiers,
  selected-tab state, PNG screenshots, termination-state verification and cleanup.
- Developer → All settings → developer passed using visible stable identifiers,
  PNG screenshots, termination and cleanup. Landscape is the existing game surface;
  the harness uses portrait for the diagnostic tools and restores the prior orientation.
- The fixture remained byte-identical after all three smoke runs.

Individual successful reports under that acceptance directory:
`20261010T063442.385956Z-e0c1406f`, `20261010T063449.995397Z-9b5dc792`, and
`20261010T063459.393151Z-87988de1`. The installed bundle was the verified separate
automation Debug build; its executable SHA-256 is
`2b3ec8fc2ccd2589f854900d300877ba784192e69dbaf492bc0ba94ef7c04ec6`
and Debug dylib SHA-256 is
`305d9e3a59a1a51cb6164970a28003350b7f786d101ba653afae10271f1178c9`.
No Swift/native code changed during these host-controller fixes. Screenshots
and device identifiers remain private. The normal SSD installation was not replaced.

XCTest can return controls behind a full-screen onboarding sheet. The controller
now requires displayed elements rather than treating hidden-control existence as
page readiness. Smoke selects the requested frontend using Foundation's process
argument domain (`-madeiraFrontend new/old`), preserving the persistent preference.

Host validation: 49 tests passed, 2 physical pytest wrappers skipped. Direct
physical CLI/acceptance runs above passed independently of the pytest wrappers.
HTTP fixtures additionally cover missing device, failed launch, stopped-after-launch,
lost session, failed termination, hidden controls and private-error filtering.
Actual startup/onboarding failures confirmed bounded reporting and target cleanup;
forced physical disconnect and termination-failure injection remain untested.
A running test app and owned fixture are the preservation evidence; this does
not claim a live game's saves or normal game/cloud-save behavior were exercised.

The physical UI smoke gate for #10 is now met. JIT coexistence, x86 execution,
detach survival and game automation remain separate, unverified milestones.
