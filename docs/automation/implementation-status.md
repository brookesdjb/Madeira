# Implementation status

Base: 48f976429c189f8396e23d251d8a82f43c705922. Host: Linux x86_64.
No physical iPad, macOS SDK, Xcode, or simulator is available to this session.

| Milestone | Implemented | Tests / actual results | Remaining / limitations | Physical validation |
|---|---|---|---|---|
| 0 investigation | Source map, build/signing/runtime/JIT/input/log inspection | Repository cloned and inspected, Python/Node found, Xcode absent | Submodule internals not fetched; actual Mac/device inventory unknown | BLOCKED |
| 1 controller | devicectl discovery/.app install; W3C Appium UI/lifecycle/screenshots; JSON CLI; per-step smoke reports; safe diagnostic events; bounded cleanup | 13 pytest host tests pass, including real HTTP against a fake Appium server, install mismatch rejection and failure cleanup | Build/sign/WDA provision on Mac; verify real devicectl schema and SwiftUI tab identifiers; IPA install omitted | BLOCKED |
| 2 JIT coexistence | Investigation and experimental probe pending | No physical experiment performed | Must demonstrate JIT + responsive WDA + x86 execution; no claim of compatibility | BLOCKED |
| 3 internal API | Not implemented yet | None | Gate on first smoke/JIT result; choose smallest transport supported by evidence | NOT TESTED |
| 4 game input | Existing integration points mapped | None | Virtual source, bounded release, recorder/replay; no direct bridge writes added | NOT TESTED |
| 5 visual checks | External screenshots and run association | Mock capture tested | Actual Metal screenshot fidelity, blank detection and baseline thresholds | NOT TESTED |
| 6 performance | Existing telemetry mapped, no new counters | None | Real per-frame instrumentation and explicit CPU/GPU distinction | NOT TESTED |
| 7 benchmarks | Deferred | None | Requires trustworthy launch readiness/input/measurements; do not benchmark sleeps or fake FPS | NOT TESTED |
| 8 agent integration | make setup/check/build/install/smoke, JSON actions, exit codes | Host smoke workflow tested | JIT/game/benchmark milestones still gated; no infinite retries | BLOCKED |

Physical milestone 1 is NOT complete just because host-side code is committed.
First developer action: use setup.md on the USB-connected provisioned Mac and
run device-smoke-test. Retain its report before proceeding to JIT experiments.
