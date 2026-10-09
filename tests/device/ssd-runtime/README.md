# Isolated prebuilt-runtime SSD experiment

This harness reuses the published OpenGL runtime with the existing pipe fallback
patch. It does not constitute a full Madeira source build, and does not replace
the working app. Native archives are unnecessary for this experiment. The real
external-library integration still belongs in the production source.

`main.m` loads the exact hash-pinned `Madeira.debug.dylib` and calls its exported
original `main`. The wrapper adds one separately compiled Swift overlay. It does
not patch Wine, JIT, graphics or any instructions in the supplied runtime.
The original app's UI, JIT helper and runtime initialization remain in use.
Only the disposable app's preferences/configuration/prefix are prepared.

The build requires the verified llvm-mingw toolchain under `toolchains/`, Xcode,
XcodeGen, and a signing team. `MINGW_BIN` can name the pinned toolchain's `bin`.
The known input archive is:

- [llvm-mingw 20260421](https://github.com/mstorsjo/llvm-mingw/releases/tag/20260421),
  `llvm-mingw-20260421-ucrt-macos-universal.tar.xz`;
- SHA-256 `bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7`;
- downloaded and hash-verified on 2026-10-09.

From the repository root:

```sh
SOURCE_APP=/path/to/the/preserved/patched/Madeira.app \
  TEAM_ID=your_team BUNDLE_ID=your.distinct.ssdprobe \
  python3 tests/device/ssd-runtime/build.py
```

The script creates a fresh temporary output directory, builds signing stubs
using the existing native-signing workflow, copies the supplied app, compiles
the wrapper/overlay and controlled fixture, rewrites the copied bundle IDs,
signs the copied frameworks, helper and app, and verifies the signatures.
It emits the output `.app` path and a `provenance.json` with input, source and
output fingerprints. An existing output app is refused; the source app is
never modified. No pairing file or Steam credentials are handled by the script.
Keep the working app's bundle ID out of `BUNDLE_ID`.

Installing over the disposable SSD data-probe app preserves its folder bookmark.
The runtime needs its own normal Built-in StikJIT setup because its app/Keychain
container is separate from working Madeira. In this local test, the existing
iPad pairing credential was privately transferred to the isolated app's legacy
import location and migrated by the unmodified app into its own Keychain. It is
not a repository resource or a reusable build artifact. No Steam sign-in was
copied.

## Device steps

1. Tap **SSD** near the top right. Register the dedicated external folder if
   necessary. Tap **Arm E: and prepare external EXE**.
2. Wait for the armed status, close the sheet, and enable JIT using the original
   app controls with LocalDevVPN connected.
3. Tap **Wine Virtual Desktop**. The isolated `madeira.cfg` selects the test
   executable directly instead of the desktop. The existing native runtime
   applies that config after the button's environment setup.
4. Tap **SSD** again to see the result. If the app exits, relaunch it and tap
   **Read last execution result**. A missing result is not a pass.
5. Quit this test app before unplugging. The overlay refuses to release its
   security scope while Wine or wineserver reports active.

The coordinator's accessor remains active on a worker thread for the complete
armed interval, with security-scoped access balanced around it. E: maps only
the selected registered root. The prefix, registry and system libraries stay
inside the isolated app. A small, unique `.madeira-execution-<UUID>` directory
on the SSD holds the fixture and diagnostic result; it is intentionally kept
for inspection. This is not a downloaded game or an internal staging copy of
one. Reauthorisation and all root/path checks use the production storage code.

## What a pass proves

The source-built x64 EXE statically imports `ssd_probe.dll`; that DLL must load
from beside the EXE before its entry point runs. The EXE explicitly selects its
own directory using `GetModuleFileNameW` / `SetCurrentDirectoryW`, reads
`assets/input.txt`, creates `beside-exe.save`, flushes it, renames it to
`reopened.save`, reopens it and checks its bytes. Only then does it write
`SSD-EXE-DLL-ASSET-SAVE-PASS` to `result.txt` on SSD.

There is no CRT dependency: the EXE imports only KERNEL32 and the companion
DLL. The fixture build uses timestamp-free PE linking and was reproduced with
identical EXE/DLL bytes in two different output directories.

This does not verify the production host's native E: working-directory
conversion: the fixture deliberately sets its own directory. It also does not
prove Dock, Steam library registration, Brotato, disconnect recovery during a
session, file-presenter relinquishment, background processing, or external
install/update/repair/cloud integration. The lifetime semaphore is an
experimental harness, not the final session/access manager.

## Results so far

- Wrapper and fixture compilation/linking, signing, installation, foreground
  launch: verified.
- First shell-based attempt: failed before SSD execution. The IPA contains an
  ARM64-native `cmd.exe`, whereas the supplied full C: command path selected
  ARM64EC system libraries. Its log reports `kernel32.dll` status `c000007b`.
  No external-execution conclusion can be drawn from that failure.
- Corrected direct EXE/DLL fixture: PASS on the physical iPad, explicitly
  confirmed by the user. That marker is written only after all EXE/DLL, relative
  asset and beside-executable save checks succeed. E: is therefore a viable
  candidate for the production integration, not just a symlink assumption.

See [the implementation record](../../../docs/EXTERNAL_STORAGE.md) for the
source-build baseline and earlier data-access/reconnect results.
