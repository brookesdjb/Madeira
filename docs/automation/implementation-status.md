# Implementation status

Base: 48f976429c189f8396e23d251d8a82f43c705922.
Initial implementation ran on Linux x86_64 without Xcode or a physical iPad.
Continuation on 2026-10-10 uses macOS 27 / Apple Silicon and Xcode 27.0.
See [Mac validation](mac-validation.md) for current verified results and gates.

| Milestone | Implemented | Tests / actual results | Remaining / limitations | Physical validation |
|---|---|---|---|---|
| 0 investigation | Source map, build/signing/runtime/JIT/input/log inspection | Mac toolchain and existing component inputs inventoried; M5 iPad/iPadOS 26.7 paired/Developer Mode/wired USB verified | Initial owner trust, UI Automation and signing setup completed; unlock recurs after Auto-Lock | PREPARATION VERIFIED |
| 1 controller | devicectl discovery/.app install; W3C Appium UI/lifecycle/screenshots; JSON CLI; safe diagnostics; shared reservation; running-target install protection; private build/startup reports | Normal Debug, automation Debug, Release and WDA compile/sign on Mac; 79 host tests pass, 2 physical wrappers skipped; separate app installed via wired USB | Three physical UI runs pass across library/developer routes after initial XCTest prompt approval; running-target refusal and owned fixture persistence verified; forced disconnect/live-game saves untested; IPA install omitted | UI SMOKE PASSED |
| 2 JIT coexistence | Investigation, opt-in XCTest status pane, bounded compatibility experiment | Mock tests cover success, failed x86 result, timeout, termination and fresh-process reactivation; physical built-in JIT, attached debugger, fresh UI, exit 42, new PID and reactivation observed | Two consecutive native launch/cleanup runs and subsequent UI smoke pass; StikDebug, normal-game detach and Shortcut restoration untested | CORE OBSERVED |
| 3 internal API | Debug-only correlated command v2, status/JIT/FEX probe via XCTest; host Portal menu checkpoint; stable presentation-window anchor | Physical read/rejection, opt-in guard, installed Portal API launch/startup reads/replay/second-session rejection and live menu checkpoint pass; all four automation markers absent from normal Debug/Release | API stop accepted but Portal ignored Alt+F4; bounded timeout preserves it. Authorized game Quit and normal cloud-close UI succeed. Failed-startup recovery, richer diagnostics and API stop completion remain open | LOCAL PORTAL LAUNCH/MENU OBSERVED |
| 4 game input | Debug-only bounded timed keyboard, relative mouse and serial-queue virtual-pad replay; stable early slot reservation | Physical Portal menu/save navigation and mouse camera response; native host-timeout observed | Pad stick response, focus/background injection, independent held-key release checks and frame alignment remain | KEYBOARD/MOUSE OBSERVED |
| 5 visual checks | External screenshots, run association, crop/threshold comparison and suspected blank detection; English Portal menu recognition | Synthetic-image tests and live Portal checkpoint pass; actual Source splash rejected; game/menu/overlay pixels inspected | Broad Metal fidelity, gameplay checkpoints and per-game threshold calibration | PORTAL MENU OBSERVED |
| 6 performance | Single bounded native submission recorder, strict trace importer and process CPU/footprint boundary sidecar | Physical loss-free menu/gameplay traces; linked signed measurement build; normal Debug/Release markers excluded | Visible-frame/GPU/per-role CPU attribution, calibrated clocks and observer-overhead acceptance remain | SUBMISSION DELIVERY OBSERVED |
| 7 benchmarks | On-device warmup/capture windows; correlated frozen trace and process sidecar export | Short physical captures and first W1 control arm | Scene checkpoints reviewed by agent; repeated paired/sustained trials and optimization acceptance remain | PRELIMINARY CAPTURES |
| 8 agent integration | make setup/check/build/install/smoke/jit, JSON actions, exit codes | Host failures/current unlock gate tested; UI and standalone built-in JIT proof observed | Standalone lifecycle repeats pass; full-game lifecycle, input and benchmarks remain; no infinite retries | PARTIAL |

Physical UI smoke now passes on the provisioned USB iPad; source, binary and
private run references are in mac-validation.md. Two consecutive standalone JIT/restart tests also pass; see jit-compatibility.md.
The owner replaced the SSD-dependent game requirement with local Portal.
Portal installed internally, synced 14 cloud saves through a standard retry and
reached a rendered main menu through normal Play and the command API. Menu input
and a two-screenshot host checkpoint are observed. The owner authorized handling
quit/save/overwrite prompts. Game Quit and normal cloud-close UI succeeded;
full API stop completion remains open. Keyboard/mouse timed replay and capture delivery are now observed; pad response and broader interruption checks remain.
See [game validation](game-validation.md).
Forced physical failure injection and live-game save/cloud checks remain untested.

Historical initial Linux environment: Appium 3.8.0 and XCUITest 12.16.0 installed from npm lockfile;
`appium driver list --installed` successfully recognizes xcuitest. A real loopback Appium server starts and its
/status reports ready. That initial check did not establish a successful XCUITest session; the Mac/iPad
continuation above now has direct session evidence. Direct Git push lacked credentials; commits are
published to the user-authorized `brookesdjb/Madeira` branch
`codex/physical-ipad-automation` through the GitHub connector, with identical Git
trees and different commit metadata. No default branch or upstream change.

## Performance consumer progress

A bounded offline native submission-trace consumer is implemented and host-tested
for issues #2/#14. It validates the shared version 1 contract and exports private
raw/summary reports. The native producer and timed input/capture runner now supply physical submission traces and whole-app CPU boundary counters. GPU and per-role CPU attribution, repeated trial acceptance and a representative iPad performance baseline remain incomplete.
