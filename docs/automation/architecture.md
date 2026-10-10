# Automation architecture investigation

Inspected upstream commit `48f976429c189f8396e23d251d8a82f43c705922` on 2026-10-10.
This is source inspection, not a successful device run.

## Host observed in this execution

Linux x86_64, Python 3.12.14, Node 24.19.0, Git 2.51.1. No `xcodebuild`,
`xcrun`, `appium`, or `pymobiledevice3` on PATH. No Mac or USB iPad is exposed
to this session. macOS/Xcode version, device pairing, Developer Mode, signing,
and connectivity cannot be verified. Physical testing is BLOCKED. A simulator
is also unavailable. Do not confuse host mocks with iOS validation.

## Source map

| Concern | Actual source and findings |
|---|---|
| Entry/lifecycle | `app/Madeira/MadeiraApp.swift`: SwiftUI `@main`; starts GamepadInput and HardwareInput, restores JIT network state, routes JIT-network and game shortcut URLs. `ContentView.swift` owns launch closures and main UI. |
| Build | `app/Madeira.xcodeproj`, scheme documented as `Madeira` in `docs/BUILDING.md`; no shared xcscheme checked in. Must verify scheme with Xcode on Mac. Debug is the documented game-running configuration. Clean builds need external toolchains, runtime files, generated component libraries; see BUILDING.md rather than assuming an app-only checkout builds. |
| Signing | Project sets team V8NU3FX3TL; callers must override with their own team. Default bundle identifier is **com.willfaust.madeora** (intentional spelling as checked in), via MADEIRA_BUNDLE_IDENTIFIER. Helper uses the same prefix plus `.JITHelper`. App deployment target 17.0, built-in helper 26.0. |
| Existing deployment | BUILDING.md describes xcodebuild then IPA packaging/sideloading. No physical-device Appium harness found. `tools/deploy-vm.sh` targets the VM, not the iPad. |
| JIT | `JITSetup.swift`: JITCoordinator enables StikDebug URL path or built-in extension via `JITBuiltInHost.swift`. `StikJITHelper.swift` and `madeira-jit.js` implement debugger readiness, pool allocation/PE-page preparation, detach. Pairing material lives in Keychain. `JITNetwork.swift` drives an optional user-installed Shortcut; `LocalDevVPN.open` opens its UI, not an authenticated VPN control API. |
| Execution | `ContentView.launchLibraryEntry` dispatches Steam/Dock or normal `runWineFullSequence(profile:)`; checks JIT/session constraints, applies environment, initializes JIT/FEX, wineserver and Wine through `FEXBridge.mm`, `WineServerBridge.m`, `WineProcessBridge.m`. Do not build a second startup path. |
| Games | `Library.swift` LibraryEntry UUID and optional steamAppID; `SteamGames.swift` and MadeiraDock handle Steam launch. Launch policy includes cloud-save/conflict checks that automation must preserve. |
| Lifetime | LibraryModel allows one native session per process. A later session requires an app restart. `requestQuit()` sends normal Alt+F4; it is a request, not proof of exit, and can require in-game confirmation. |
| Readiness | LibraryModel.poll uses present/surface counters; DockStartScreen distinguishes game windows from launcher/desktop frames. An elapsed timeout only sets a slow indicator. A generic first-frame flag is not proof a game is ready for benchmarking. |
| Input | `GamepadInput.swift` samples controllers and merges touch samples, publishes `winios_gamepad_set_state`, optional HID and keyboard/mouse translation. `TouchGamepad.swift`, `PadKeyboardMouse.swift`, `HardwareInput.swift`, ContentView touch handling feed existing Winios paths. PadOutput handles rumble. A virtual source should merge here and release on timeout/disconnect, not tap an overlay or race another publisher. |
| Logs | `LogStore.swift`, `LogTail.swift`: Documents/madeira-log.txt, prior log and per-session logs; native stderr/file capture continues when UI parsing is idle. Raw logs can contain private account/path data; don't export them by default. |
| Performance | FPSOverlay samples `madeira_get_present_count` for a windowed rate and task footprint, not individual frame times. Library's opt-in DeviceLoadDiagnostics reports public thermal state/low power/capture. DXMT build includes existing frame/capture diagnostics. These are not interchangeable with measured GPU time. |
| Tests | `tests/host/check-*.py` source/host checks; native x86/x64/DXMT test programs; developer UI has `runFEXTest` (expects 42). No XCTest/Appium target found. |

## Dependencies at inspected revision

Uninitialized submodules (no upstream changes made):

- FEX `3bec2ac498bf78156ab47c0c194b0e8cb2849756`, willfaust/FEX, ios-port-2607.
- Wine `257f271cfffed9f22f7987cac53bc00095d092fe`, willfaust/wine, madeira-lgpl.
- DXMT `db546ee466ad50ec6463edb5fa183de11db43761`, willfaust/dxmt, ios-port.
- madeira-dock `72558e416a390f3669457930f09a389e54f49556`, willfaust/madeira-dock, main.

Submodule internals were not fetched or audited for new counters. Component
integration/build sources live under build/. Bundled StikJIT.xcframework and
MadeiraJITHelper extension implement the built-in helper. Its binary behavior
and physical debug-service coexistence cannot be inferred from Swift alone.

## First proof design

Python controller: xcrun devicectl JSON discovery/install + loopback Appium
XCUITest session for UI, screenshots and lifecycle. Preserve app data with
noReset; never uninstall. Prefer a signed .app for native installation; IPA
installation can use Appium on the same Mac. Explicit UDID if multiple iPads.
Smoke opens existing settings and returns, records each step, captures failure
evidence before termination, then deletes its Appium session. No game launches,
Steam sign-in, purchases, account edits, VPN changes or JIT changes in smoke.

The host tests validate command construction, device selection, bounded failure
handling and protocol responses. They cannot establish WDA signing, iPad UI
identifier propagation, screenshot/Metal fidelity or JIT compatibility.
