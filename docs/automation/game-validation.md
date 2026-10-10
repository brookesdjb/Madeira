# A3 physical validation, 2026-10-10

Branch: `codex/a3-local-game-lifecycle`, based on A2 `780a5bf`.
Merge `d109d3b` includes the existing validated storage branch so an integration
build retains the normal app's storage implementation. No FEX/Wine/DXMT
submodule implementation was changed for A3.

Initial command acceptance source: `8317f394e7c48b4e68b3f46bed7f55c9cb742096`.
Current app source: `b5af176ce4e14200968d9990dbdbccf2ead4cb5c`.
Host menu checkpoint introduced at `9470c132c5dde6ed9b12be590756fa224209bb02`.
Host: Apple Silicon, macOS 27, Xcode 27.0. Controller: Appium 3.8.0,
XCUITest 12.16.0, Python 3.14.7. Device: wired physical 11-inch M5 iPad Pro,
iPadOS 26.7. All physical operations held the host-wide device reservation.
Device/account identifiers, logs and screenshots remain private.

## Command API acceptance

79 host tests pass, including execution of the actual Foundation-only Swift
parser and replay ledger; two physical wrappers are skipped in that host run.
Separate physical tests are recorded below.

Clean signed automation Debug, normal Debug and Release builds all pass strict
signature and actual executable checks. The new command identifier, status probe
and native exit-42 symbol occur only in opted-in Debug. The installed separate
automation Debug executable SHA-256 is
`a1d72085c1311e052c087cecc7c737e798c5862d59dc9693beb2c2c2e6909eb0`;
its debug dylib SHA-256 is
`411b2990a18d70ea5bb84747b7b6e1e46cc0ce9e43f7971665ae2f5dcb8f2005`.

Physical run `20261010T075436.661636Z-d6a740b5/command-acceptance.json`
passed 13 checks:

- All six read operations complete with schema 2 and matching request IDs.
- A repeated ID is rejected as `duplicate_request`.
- Launch/stop of a missing game are rejected without starting Wine.
- Malformed JSON, an unsupported purchase operation and an arbitrary path field
  are rejected as `invalid_request`.
- Wine/wineserver remain stopped and the FEX probe remains NOT_RUN.

Native cleanup confirmed the fresh test PID stopped. An earlier attempt
correctly refused a preexisting test process; its idle normal library was
verified before stopping it. No game or account was installed in this separate
test app.

Physical run `20261010T075813.410499Z-9dd279a3/runtime-guard.json` passed:
the same opted-in binary launched without `--madeira-automation` exposes the
normal library and no command control. Native cleanup confirmed it stopped.

## Internal-storage game observations

The owner replaced Borderlands on the unplugged SSD with a local-storage game.
Portal (Steam App ID 400) was already owned and installed through the existing
normal app's Download to iPad path. Free space changed from 30.51 GB to 26.14 GB.
No purchase, external library attachment or account transfer was performed.

The first normal Play request enabled JIT but stopped at Steam Cloud. The cloud
download reported URL error -999. Standard Sync now successfully retried it:
the normal UI reported In sync, 14 saves downloaded and the same on both sides.
No conflict choice or Launch anyway bypass was used.

The second normal Play request reached a rendered 3D main menu, whose title
reads "Portal: The First Slice". This proves this installed package reached
its menu, not full-game licensing, gameplay or a scripted readiness checkpoint.
Touch mode allowed the host to open Options, cancel it, and reach the game's
Quit confirmation. The prior Absolute pointer mode was restored through the
normal menu and verified selected. No gameplay was started or game options changed.

Madeira's existing Quit game action sent its normal graceful-close request but
the menu remained active. The owner explicitly authorized agent handling of
quit, save and overwrite prompts, superseding the earlier confirmation pause.
The game's own Quit path and confirmation subsequently ended the game. Dock's
numeric report recorded launch-game-ended=1, shutdown-complete=1 and result 0;
the Wine desktop remained. Absolute pointer mode was restored, then the normal
Upload saves and close Madeira flow completed and stopped the main app. This
normal UI result is separate from API stop completion; no game was force-killed
to manufacture an API success. No conflict or overwrite choice occurred.

Private screenshots include `madeira-portal-cloud-result.private.png`,
`madeira-portal-startup-latest.private.png`,
`madeira-portal-options-result.private.png` and
`madeira-portal-quit-dialog.private.png` in `/tmp`. They are not uploaded.

## Installed-game API integration

A signed automation build updated the existing game app's same bundle after
normal cloud close. Before/after SHA-256 comparisons verified unchanged library
settings, pointer settings, cloud-sync baseline, all 13 Portal save files and
the game config. Private backups remain in the ignored run directories. No
credential transfer, uninstall or data reset was used.

Run `20261010T081633.540864Z-16c630e4/integration-install.json` records the initial
update. Its first launch reached Portal, but the host missed the correlated
reply during the screen transition. A later read recovered accepted/launch_requested;
the launch was not retried. The host now polls only the reply across transitions.

Run `20261010T083201.381772Z-009f7301/overlay-game-commands.json` proves API launch,
reads during startup, duplicate-ID rejection and a fresh second-launch rejection.
Typing into the overlay made its window key, allowing Winios to attach guest
rendering above its UI. Restoring key focus alone cannot eliminate a race when
a read occurs during later runtime initialization. The opted-in native anchor
now binds the compositor to MetalBackedView's actual window. That symbol and
branch are compiled out of normal Debug and Release, with a binary guard.

Run `20261010T083411.407149Z-ead3d2ba/portal-stop.json` records the accepted API
graceful stop. Portal stayed at the menu. Run
`20261010T083532.241226Z-149ae72d/exit-timeout.json` records a bounded
graceful_exit_timeout_game_preserved result, subsequent active status and
duplicate/second-stop rejection. An accepted Alt+F4 is not successful exit.

Run `20261010T084459.403631Z-b73d522f/portal-normal-quit.json` records the authorized
in-game Quit, successful Dock result, restored pointer mode and normal cloud
close, with app state 1 and no native main process. A background main process
was later observed again; the cause is not established. Install attempts correctly
refused it until it was activated and verified to be an idle library, then stopped.
Run `20261010T084829.216601Z-eefa4b3b/overlay-game-validation.json` records a further
preserved-data update and API launch/replay/second-session checks.

Run `20261010T085024.778952Z-d796e344/report.json` records a live host Vision
checkpoint: two fresh same-PID screenshots recognize the English Portal: The
First Slice title plus New Game, Options and Quit. Result is MENU_OBSERVED,
with observation time and screenshot hash; it is not gameplay or benchmark
readiness. The actual Source splash screenshot fails recognition. Arbitrary
OCR text is discarded. See protocol.md for confidence, title OCR tolerance,
deadline and preservation semantics.

The current integration executable SHA-256 is
`b9de8b6ab4d67d5d13a15bb6eff7fb1536c3ac6ab182d60e626fd06d0d09f0e3`;
debug dylib SHA-256 is
`b6d2647d91f01014e3b1ee5104aae7d8e4c11c12fbc10c986047dabae86b8547`.
Build `20261010T085440.454267Z-13a42e1d` is clean and strictly signed.

Run `20261010T085538.001269Z-3b5a5c78/overlay-game-validation.json` installs that
exact build with the same data hashes, repeats the JIT/API launch/startup reads,
and rejects replay and a second launch. Screenshot inspection confirms both
the command panel and game HUD remain drawn above the guest surface during
startup. Run `20261010T085736.032737Z-9b0491ac/report.json` passes the live menu
checkpoint again on that process. Clean strictly signed normal Debug and Release
from the same source exclude the panel, native exit-42 fixture, command marker
and presentation-anchor symbol.

On that same final binary, normal touch input opened Options; Cancel returned
to the menu without changing a game option. Run
`20261010T090015.368567Z-31631201/final-input-stop.json` repeats accepted API stop
and bounded preservation on timeout. Run
`20261010T090343.681460Z-55a27dd8/final-normal-quit.json` then confirms the
authorized game Quit, Dock game-ended/shutdown/result-0 fields, restored Absolute
pointer mode and successful normal cloud close with no native main process.
These are menu-only observations, not virtual-input/replay or gameplay acceptance.

## Remaining limits

Failed-startup recovery, broader game checkpoints, and API graceful-exit
completion remain pending. Portal's menu checkpoint and installed-game
launch/replay/one-session checks are observed; the game-specific Quit and
cloud-close flow currently needs normal UI orchestration after API stop timeout.
The command status explicitly reports NOT_VERIFIED readiness. Underlying
unchecked/conflicting cloud holds are observed even if a sheet transition
dismisses their alert. A saving or held game is never killed to manufacture a
successful exit. Read diagnostics currently returns the safe snapshot; richer
fixed-event diagnostics are still a follow-up. Virtual input/replay belongs to
issue #12; the UI menu exercise above does not satisfy its acceptance criteria.
