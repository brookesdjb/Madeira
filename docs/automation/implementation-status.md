# Implementation status

Base: 48f976429c189f8396e23d251d8a82f43c705922.
Initial implementation ran on Linux x86_64 without Xcode or a physical iPad.
Continuation on 2026-10-10 uses macOS 27 / Apple Silicon and Xcode 27.0.
See [Mac validation](mac-validation.md) for current verified results and gates.

| Milestone | Implemented | Tests / actual results | Remaining / limitations | Physical validation |
|---|---|---|---|---|
| 0 investigation | Source map, build/signing/runtime/JIT/input/log inspection | Mac toolchain and existing component inputs inventoried; M5 iPad/iPadOS 26.7 paired/Developer Mode/wired USB verified | Initial owner trust, UI Automation and signing setup completed; unlock recurs after Auto-Lock | PREPARATION VERIFIED |
| 1 controller | devicectl discovery/.app install; W3C Appium UI/lifecycle/screenshots; JSON CLI; safe diagnostics; shared reservation; running-target install protection; private build/startup reports | Normal Debug, automation Debug, Release and WDA compile/sign on Mac; 61 host tests pass, 2 physical wrappers skipped; separate app installed via wired USB | Three physical UI runs pass across library/developer routes after initial XCTest prompt approval; running-target refusal and owned fixture persistence verified; forced disconnect/live-game saves untested; IPA install omitted | UI SMOKE PASSED |
| 2 JIT coexistence | Investigation, opt-in XCTest status pane, bounded compatibility experiment | Mock tests cover success, failed x86 result, timeout, termination and fresh-process reactivation; physical built-in JIT, attached debugger, fresh UI, exit 42, new PID and reactivation observed | Final native launch/cleanup repetition waits for owner unlock; StikDebug, normal-game detach and Shortcut restoration untested | CORE OBSERVED |
| 3 internal API | Minimal debug-only status/JIT/FEX probe via XCTest | Swift compiled; actual app binary contains probe only in opted-in Debug and excludes it in normal Debug/Release | Status/JIT/FEX probe observed on iPad; full game lifecycle API and truthful game readiness remain deferred | NARROW PROBE OBSERVED |
| 4 game input | Existing integration points mapped | None | Virtual source, bounded release, recorder/replay; no direct bridge writes added | NOT TESTED |
| 5 visual checks | External screenshots, run association, crop/threshold comparison and suspected blank detection | Mock capture and 5 synthetic-image tests pass | Actual Metal screenshot fidelity and per-game threshold calibration | NOT TESTED |
| 6 performance | Existing telemetry mapped, no new counters | None | Real per-frame instrumentation and explicit CPU/GPU distinction | NOT TESTED |
| 7 benchmarks | Deferred | None | Requires trustworthy launch readiness/input/measurements; do not benchmark sleeps or fake FPS | NOT TESTED |
| 8 agent integration | make setup/check/build/install/smoke/jit, JSON actions, exit codes | Host failures/current unlock gate tested; UI and standalone built-in JIT proof observed | Full repeated lifecycle acceptance, game input and benchmarks remain; no infinite retries | PARTIAL |

Physical UI smoke now passes on the provisioned USB iPad; source, binary and
private run references are in mac-validation.md. Proceed to JIT experiments.
Forced physical failure injection and live-game save/cloud checks remain untested.

Appium 3.8.0 and XCUITest 12.16.0 installed from npm lockfile on Linux;
`appium driver list --installed` successfully recognizes xcuitest. A real loopback Appium server starts and its
/status reports ready. This is not a
successful XCUITest session. Direct Git push lacked credentials; commits are
published to the user-authorized `brookesdjb/Madeira` branch
`codex/physical-ipad-automation` through the GitHub connector, with identical Git
trees and different commit metadata. No default branch or upstream change.
