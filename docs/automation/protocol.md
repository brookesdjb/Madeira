# Experimental XCTest probe protocol v1

This is the minimum internal observation/control surface for the JIT milestone,
not the complete game lifecycle API. Its code is in ContentView.swift to reuse
private existing launch/test closures without changing the Xcode source manifest.

Activation requires `DEBUG && MADEIRA_AUTOMATION` at compile time AND the process
argument `--madeira-automation`. The default build command does not add the test
flag. The Release configuration does not define DEBUG. No network transport,
URL command handler, token, pairing export or Steam account operation is added.
WDA requires the normal trusted/pairing/signed development-device provisioning.
USB forwarding reliability has not been measured here; no forwarder is assumed.

| Accessibility identifier | Operation |
|---|---|
| madeira.automation.refresh | Refresh status on main thread; monotonically increases sequence |
| madeira.automation.status | Read JSON from accessibility `value` |
| madeira.automation.enable-jit | Invoke ContentView.enableJIT, preserving its existing flow and safety checks |
| madeira.automation.test-fex | Invoke existing runFEXTest once in an idle process with JIT ready |

JSON contains schema_version, sequence, timestamp, pid, state, jit_ready,
jit_debugged, debugger_attached, launch_pool_allocated, jit_busy, jit_error (boolean,
not potentially private text), jit_method, wine_running, wineserver_running,
wineserver_ready, present_count, thermal_state, fex_test and fex_result.

States deliberately stop at APP_IDLE / INITIALIZING_JIT / SESSION_ACTIVE:
SESSION_ACTIVE is NOT GAME_RUNNING or benchmark-ready. Runtime booleans and
present count are observations, not a lifecycle state machine. fex_test is
NOT_RUN / RUNNING / PASSED / FAILED; success requires result 42. UI snapshots
have no periodic timer when the probe is unused; refresh happens on command.
The native standalone fixture explicitly executes Linux sys_exit(42) through
the existing loader; the normal developer Hello World test expects exit 0.
The test pane changes layout and adds UI work, so it is unsuitable for final
unperturbed performance measurements without further isolation.

`get_status`, `get_runtime_status`, and `get_jit_status` are currently represented
by this single snapshot. list_installed_games/launch_game/stop_game/get_game_status,
virtual input and log streaming are NOT implemented in this protocol. Existing
host log collection exports a fixed event vocabulary only. Extending commands
must retain normal launch/cloud-save checks and one-session-per-process behavior.

Security verification on this Mac: normal Debug, opted-in Debug and Release
compile/sign and pass binary checks. Both the probe identifier and native
exit-42 fixture symbol are absent from non-opted-in binaries. A launch argument
cannot enable a compiled-out probe. See jit-compatibility.md for actual device
results and remaining limits.

launch_pool_allocated is StikJITHelper's **normal game-launch pool** flag. FEX's
standalone test has a separate private pool in FEXBridge.mm; it does not set that
Swift flag. FEX success is determined from the completed test result, not this
flag. The FEX probe additionally requires an attached debugger before invoking
that existing pool-allocation path, even if the attach-check option was disabled.

## Local game commands v2 (A3 in progress)

The opted-in pane now accepts a JSON request through
`madeira.automation.command` and its `madeira.automation.send-command` button.
`madeira.automation.reply` returns the correlated JSON reply. Status snapshots
remain schema 1 with added `game_status`; command requests/replies are schema 2.
No network listener, launch path, credentials or arbitrary launch arguments are
accepted. Appium's existing paired XCTest session remains the transport.

```json
{"schema_version":2,"request_id":"launch-001","operation":"launch_game","steam_app_id":400}
```

Operations: get_status, list_installed_games, launch_game, stop_game,
get_game_status, get_runtime_status, get_jit_status, get_diagnostics. Mutations
require exactly one existing LibraryEntry UUID (`library_id`) or Steam App ID
(`steam_app_id`); multiple storage copies make an App ID ambiguous. Read commands
observe the current process and accept no selector. Requests are at most 4096
UTF-8 bytes, IDs are 1–64 ASCII letters/digits/hyphens/underscores, and unknown
fields/operations, malformed selectors and unsupported versions are rejected.
Every parsed request ID is consumed once; after 1000 IDs, restart is required.
IDs are never evicted, so a delayed old launch cannot replay.

Launch requires a fresh idle library process, no prior Wine or FEX test session,
attached JIT, no busy initialization and no current confirmation/error. It calls
ContentView.launchLibraryEntry, retaining the normal storage validation, launch
profile, Steam Dock and cloud-save gates. The reply `accepted/launch_requested`
only acknowledges the request; it is not readiness. Status distinguishes IDLE,
LAUNCH_REQUESTED, SESSION_OBSERVED, STOP_REQUESTED, SESSION_ENDING, EXITED, ERROR
and MANUAL_INTERVENTION_REQUIRED. Readiness remains NOT_VERIFIED until a separate
game-specific checkpoint is implemented/observed; neither elapsed time nor
present counters prove game readiness. Error output uses fixed codes, not private
messages. list_installed_games reports existing configured entries supported by
current installed Steam metadata or an internal executable check.

Stop accepts only the game this automation instance requested and which is
still the active entry, after normal startup tooling releases input. It invokes
LibraryModel.requestQuit without killing a process. The reply
`accepted/graceful_stop_requested` is not proof of exit. The host bounded exit
observer requires EXITED, no active library ID and both Wine/wineserver stopped.
A confirmation or timeout preserves the game; a saving game is never killed to
manufacture a pass. Launch requests cannot repeat in one process, including
requests held by asynchronous storage/cloud validation.

Example for an already running opted-in foreground app:

```sh
python -m automation.controller.cli game-command list_installed_games
python -m automation.controller.cli game-command launch_game --steam-app-id 400
python -m automation.controller.cli game-command get_game_status
python -m automation.controller.cli game-command stop_game --steam-app-id 400
```

These commands do not launch/restart/install the app or force-stop it at session
cleanup. Rejection exits nonzero. Full game-specific readiness/input/exit device
acceptance remains pending; Portal on the iPad's internal storage is now the
selected first game, replacing the earlier SSD-dependent Borderlands proposal.
