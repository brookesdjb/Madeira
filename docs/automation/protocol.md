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
