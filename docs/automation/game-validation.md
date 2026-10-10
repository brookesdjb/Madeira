# A3 physical validation, 2026-10-10

Branch: `codex/a3-local-game-lifecycle`, based on A2 `780a5bf`.
Merge `d109d3b` includes the existing validated storage branch so an integration
build retains the normal app's storage implementation. No FEX/Wine/DXMT
submodule implementation was changed for A3.

Tested command source: `8317f394e7c48b4e68b3f46bed7f55c9cb742096`.
Host: Apple Silicon, macOS 27, Xcode 27.0. Controller: Appium 3.8.0,
XCUITest 12.16.0, Python 3.14.7. Device: wired physical 11-inch M5 iPad Pro,
iPadOS 26.7. All physical operations held the host-wide device reservation.
Device/account identifiers, logs and screenshots remain private.

## Command API acceptance

71 host tests pass, including execution of the actual Foundation-only Swift
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
the menu remained active. The game's own Quit path reached "Do you wish to stop
playing now?". Confirmation is pending under issue #11's preserved-gate rule;
there is no claim of exit. The normal app has not been replaced or force-stopped.

Private screenshots include `madeira-portal-cloud-result.private.png`,
`madeira-portal-startup-latest.private.png`,
`madeira-portal-options-result.private.png` and
`madeira-portal-quit-dialog.private.png` in `/tmp`. They are not uploaded.

## Next integration and limits

A signed automation build for the existing game app is prepared in the isolated
`automation/derived-data/portal-integration` output, using the same tested source.
It is not installed while the existing game session remains active. It must
retain the app's data and normal cloud/storage/Steam Dock launch path.

Actual installed-game commands, one-session rejection, failed-startup recovery,
game-specific readiness and bounded graceful-exit completion remain pending.
The command status explicitly reports NOT_VERIFIED readiness. Underlying
unchecked/conflicting cloud holds are observed even if a sheet transition
dismisses their alert. A saving or held game is never killed to manufacture a
successful exit. Read diagnostics currently returns the safe snapshot; richer
fixed-event diagnostics are still a follow-up. Virtual input/replay belongs to
issue #12; the UI menu exercise above does not satisfy its acceptance criteria.
