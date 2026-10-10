# Implementation status

Base: 48f976429c189f8396e23d251d8a82f43c705922. Host: Linux x86_64.
No physical iPad, macOS SDK, Xcode, or simulator is available to this session.

| Milestone | Implemented | Tests / actual results | Remaining / limitations | Physical validation |
|---|---|---|---|---|
| 0 investigation | Source map, build/signing/runtime/JIT/input/log inspection | Repository cloned and inspected, Python/Node found, Xcode absent | Submodule internals not fetched; actual Mac/device inventory unknown | BLOCKED |
| 1 controller | devicectl discovery/.app install; W3C Appium UI/lifecycle/screenshots; JSON CLI; per-step smoke reports; safe diagnostic events; bounded cleanup | 25 pytest host tests pass; 2 physical tests skipped, including real HTTP against a fake Appium server, install mismatch rejection and failure cleanup | Build/sign/WDA provision on Mac; verify real devicectl schema and SwiftUI tab identifiers; IPA install omitted | BLOCKED |
| 2 JIT coexistence | Investigation, opt-in XCTest status pane, bounded compatibility experiment | Mock tests cover success, failed x86 result, timeout, termination and fresh-process reactivation; no physical experiment performed | Must demonstrate JIT + responsive WDA + x86 execution; no claim of compatibility | BLOCKED |
| 3 internal API | Minimal debug-only status/JIT/FEX probe via XCTest | Compile guards checked by host source test; Swift not compiled | Full game lifecycle API deferred until smoke/JIT gate; Release binary exclusion unverified | NOT TESTED |
| 4 game input | Existing integration points mapped | None | Virtual source, bounded release, recorder/replay; no direct bridge writes added | NOT TESTED |
| 5 visual checks | External screenshots, run association, crop/threshold comparison and suspected blank detection | Mock capture and 5 synthetic-image tests pass | Actual Metal screenshot fidelity and per-game threshold calibration | NOT TESTED |
| 6 performance | Existing telemetry mapped, no new counters | None | Real per-frame instrumentation and explicit CPU/GPU distinction | NOT TESTED |
| 7 benchmarks | Deferred | None | Requires trustworthy launch readiness/input/measurements; do not benchmark sleeps or fake FPS | NOT TESTED |
| 8 agent integration | make setup/check/build/install/smoke/jit, JSON actions, exit codes | Host smoke workflow tested | JIT/game/benchmark milestones still gated; no infinite retries | BLOCKED |

Physical milestone 1 is NOT complete just because host-side code is committed.
First developer action: use setup.md on the USB-connected provisioned Mac and
run device-smoke-test. Retain its report before proceeding to JIT experiments.

Appium 3.8.0 and XCUITest 12.16.0 installed from npm lockfile on Linux;
`appium driver list --installed` successfully recognizes xcuitest. A real loopback Appium server starts and its
/status reports ready. This is not a
successful XCUITest session. Direct Git push lacked credentials; commits are
published to the user-authorized `brookesdjb/Madeira` branch
`codex/physical-ipad-automation` through the GitHub connector, with identical Git
trees and different commit metadata. No default branch or upstream change.
