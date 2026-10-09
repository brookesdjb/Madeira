# External SSD implementation record

Status on 2026-10-09: **data access and a controlled external EXE/DLL/asset/save fixture verified
on an iPad; the integrated external game library remains unimplemented.**
This is a first increment for [issue 131](https://github.com/willfaust/Madeira/issues/131),
not a claim that games can yet install or run from an SSD.

## Source and build baseline

Work started from clean `local/opengl-225` at
`88624c92b0b18692cb272ca5a7a733d22cbf250c`, on
`feature/external-ssd-library`. The OpenGL merge and Wine pipe fallback are
ancestors of this branch and remain unchanged. No JIT or graphics changes.
No credentials, saves, game files or working Madeira installation were changed.
The user-confirmed working Brotato build remains the regression baseline;
it is a published test binary with a native compatibility patch, not a build
of this checkout.

Environment: Apple Silicon macOS, Xcode 27.0 (27A266a), iOS 27 SDK, initially
14 GiB available. The connected target is an iPad Pro 11-inch (M5). The probe
uses the existing Xcode signing team in `../native-signing/project.yml`, with
its own bundle ID `com.brookes.madeira.ssdprobe`. It does not share an app
container or Keychain entitlement with Madeira.

All four submodules initially were uninitialized. The exact Dock revision
`72558e416a390f3669457930f09a389e54f49556` was fetched successfully. GitHub's
commit API also confirmed public availability of the pinned Wine, FEX and
DXMT commits. The old BUILDING.md publication warning is therefore not a
current blocker for those four top-level revisions; nested submodules have
not been audited.

The full Debug app build was attempted, without signing:

```sh
xcodebuild -project app/Madeira.xcodeproj -scheme Madeira \
  -configuration Debug -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/madeira-ssd-build CODE_SIGNING_ALLOWED=NO build
```

It fails at the missing `app/Madeira/x86_64-vcruntime` resource. Independently,
the native link inputs are absent: FEX's seven archives; Wine's
`libntdll_unix.a`, `libwineserver.a`, `libwin32u_unix.a`; `libdxmt_combined.a`;
the four FFmpeg archives; and `libmadeira_rppairing.a`. The `toolchains/`
directory is absent, including the iOS LLVM build needed by DXMT. Only the
four tracked GMP/Nettle/GnuTLS archives are present in `app/Madeira`.
Resolving the first resource failure alone will not produce a linked app.
A native rebuild needs the chains in BUILDING.md, or compatible archives
with recorded source/build provenance.

The old signing scripts re-sign the published application. They do not
compile the app source and cannot integrate these changes. The successful
probe below is fully built from its checked-in Swift sources and Apple's
SDK. **No prebuilt Madeira runtime was reused in the probe.**

For comparison only, the preserved working runtime's SHA-256 is
`d942617b44d57bb23b3e97dce87cf5272265e239dc5d6434dac11030341d6446`
(`../patched-native/Payload/Madeira.app/Madeira.debug.dylib`). Its pre-pipe-fix
backup is `ec84cfbf6b0754efc5fb56692f1223458e1c140717b201edbc1f20c3930d0f39`.
These are binary provenance fingerprints, not evidence of source equivalence.

## Implemented increment

- `SteamStorageLibrary`: internal identity `internal`, one external UUID,
  display name and bookmark. C: is internal; E: is a proposed external path
  representation only, **not yet registered with Wine**.
- A `.madeira-library-id` marker binds bookmark resolution to library identity.
  Reauthorisation requires the existing identity. Missing markers are never
  recreated on reconnect; a different folder at the old location fails closed.
- Relative path validation rejects traversal, absolute/drive paths, controls,
  and symlink components (including dangling links). Each component is checked:
  Darwin's whole-path resolver can leave a symlink ancestor unresolved when
  the final leaf does not exist. This is conservative filesystem validation,
  not a defence against another process concurrently replacing directory entries.
- Security scope starts before coordination and ends after the synchronous
  accessor returns. The accessor covers every POSIX handle and mmap lifetime.
  Stale bookmarks refresh only after identity validation. The prototype rejects
  non-local/ubiquitous folders and reports permission, read-only, disconnected
  and identity mismatch states. This does not certify every File Provider.
- The data probe creates a unique scratch folder and exercises create, pwrite,
  read, seek, shared mmap, msync, fsync, rename and close/reopen. It removes its
  own scratch folder. Registration leaves the identity marker. The optional
  >4 GiB test writes past the boundary and may allocate that much disk space;
  it is not a throughput or physical allocation test.
- Uninstall and partial-download cancellation wait for the active downloader
  before deleting. Deletion reports filesystem failures and refuses missing
  library roots and symlink targets. An install's primary record and library
  settings remain until deletion succeeds; reinstall is blocked during removal.
  Multi-file deletion is not transactional: a failed attempt can leave some
  payloads already removed, and should be retried or repaired.
- The existing download integration harness now uses Apple's native
  CommonCrypto/Compression/zlib on macOS, retaining Linux shims there. This
  exposed acceptance of incomplete AES payloads; the production decryptor now
  rejects non-block-aligned ciphertext before calling the platform library.
  Existing malformed-input expectations were preserved.

## Reproduce the device probe

Requires Xcode and XcodeGen. From the repository root:

```sh
bash tests/device/ssd-probe/build.sh             # unsigned compile
TEAM_ID=your_team BUNDLE_ID=your.distinct.ssdprobe \
  DERIVED_DATA=/tmp/madeira-ssd-probe \
  bash tests/device/ssd-probe/build.sh            # signed build
xcrun devicectl device install app --device YOUR_DEVICE \
  /tmp/madeira-ssd-probe/Build/Products/Debug-iphoneos/MadeiraSSDProbe.app
xcrun devicectl device process launch --device YOUR_DEVICE your.distinct.ssdprobe
```

Use a distinct bundle ID to preserve working Madeira. Select a dedicated SSD
folder, then **Reopen bookmark and test**, initially with the large-file switch
off. The same view is included in Madeira's source behind the default-off
`env.MADEIRA_EXTERNAL_STORAGE_PROBE = 1` setting, under Storage diagnostics.
That path has been type-checked but not installed in a full Madeira build.

Apple's [directory-access requirements](https://developer.apple.com/documentation/uikit/providing-access-to-directories)
require security-scoped access and file coordination. The picker uses
`UIDocumentPickerViewController(... asCopy: false)`. The standalone probe
holds both access and coordination for its actual operation, not merely
folder selection. It imports no copy of the folder.

## Validation evidence

| Check | Result |
|---|---|
| `check-steam-library.py` | PASS, production download/decode/record code under AddressSanitizer; interrupt/resume, valid-chunk reuse, update, uninstall, malformed inputs; new identity/path/deletion checks |
| `check-steam-games.py` | PASS, production rules/discovery and AddressSanitizer checks |
| `check-steam-cloud.py` | PASS, existing production cloud integration checks |
| `check-dock-path.py` | PASS with `WINE_FILE_C=/tmp/madeira-pinned-wine-file.c`, fetched from the exact pinned Wine commit |
| `check-dock-contract.py` | PASS against initialized pinned Dock source |
| `check-launch-routing.py` | PASS |
| `tests/host/typecheck-ios.py` | PASS, all 64 production Swift sources and real bridging header against iOS SDK; no native linking |
| Standalone probe | Debug unsigned and signed build PASS; installation and foreground launch PASS |
| First SSD test | User reported PASS on physical iPad: bookmark resolve plus data operations |
| Restart/unplug/reconnect | User explicitly confirmed FAIL unplugged, PASS reconnected without selecting the folder again |
| Full Madeira app | Build blocked by missing resources/native inputs; no new app installed |
| External Windows EXE/DLL + relative asset/save | PASS in the isolated prebuilt-runtime harness, confirmed by the user |
| Dock and Brotato from SSD | NOT TESTED |

The Wine resolver input can be reproduced without initializing all of Wine:

```sh
curl -fLsS https://raw.githubusercontent.com/willfaust/wine/257f271cfffed9f22f7987cac53bc00095d092fe/dlls/ntdll/unix/file.c \
  -o /tmp/madeira-pinned-wine-file.c
WINE_FILE_C=/tmp/madeira-pinned-wine-file.c python3 tests/host/check-dock-path.py
```

This checks the existing Unix namespace handoff; it is **not** proof of E: or
external executable loading. No physical read-only, permission-revocation,
>4 GiB, APFS/exFAT comparison, background expiration, game-session unplug, or
internal-storage growth tests have been performed.

## Gate before integrating external games

The native Dock source's `src/launch.c` normalizes Steam's actual install path
with `GetFullPathNameW` and compares it case-insensitively with
`MADEIRA_STEAM_HOST_EXPECTED_INSTALL`. That comparison is not limited to C:.
This permits investigating E:, but does not prove Valve's client or Wine
accepts a security-scoped external library. The Swift discovery and native
working-directory bridge still assume C:.

The next step needs a Wine-capable build with the shared folder-access code:
run a controlled Windows EXE that imports a DLL and reads/writes relative
assets on the SSD, retaining scope and coordination until the entire Wine
session stops. Investigate file-presenter relinquishment, cancellation,
backgrounding and disconnect while Wine is using raw descriptors. A symlink
alone or a retained security scope without coordination is not sufficient.
Then test both Dock and direct Brotato launches before selecting E: versus a
registered C: alias based on evidence.

After that gate, the following requested work is still required: library-ID
migration of existing entries; selected-library download queues and persisted
partial-install identity; external discovery, updates, repair and uninstall;
Steam libraryfolders registration and one-time installers; per-library metadata
and free-space UI; native working-directory mapping; GameInstall save and Cloud
resolution that cannot interpret missing storage as deleted saves; disconnect
recovery and the complete physical-device matrix. Existing games and queues
remain internal. The prototype never silently redirects an SSD operation into
internal storage.

## Follow-up: isolated reuse of the published runtime

The owner confirmed that only the checkout and published IPA are available.
A narrower route was then built: [the SSD runtime harness](../tests/device/ssd-runtime/README.md)
loads the hash-pinned published app runtime through its exported original entry
point and adds a source-built folder-access overlay. It uses a distinct app
container and signing profile; no runtime/JIT/graphics code is patched. This
removes the full-source-build dependency for the execution experiment only.
The preserved working runtime's hash was rechecked and remains unchanged.

The pinned llvm-mingw archive was downloaded and verified successfully, so that
toolchain is now present locally. The controlled EXE imports a companion DLL,
reads a relative asset and writes/renames/reopens a save beside its executable.
Its only other dependency is KERNEL32. Two builds in different output directories
produced identical fixture bytes. All 64 production Swift sources still
pass the iOS type-check after making the probe's pure file-path property
explicitly nonisolated.

The initial shell-based runtime test failed internally because the supplied
IPA's `cmd.exe` is ARM64-native but the harness selected ARM64EC libraries;
`kernel32.dll` failed with `c000007b`. The corrected fixture launches directly
from E:. The corrected signed app is installed and launched. The user confirmed its
PASS result: the external EXE and DLL loaded, the relative asset matched, and
the beside-executable save was written, renamed, reopened and verified. This is a prebuilt-runtime
experiment, not a successful full source app build or completed SSD support.

## Persistent catalog and async access increment

`SteamStorageLocation` stores a library ID and a validated relative path. Missing
IDs decode as internal; resolving an address against another library is refused.
`SteamStorageCatalog` keeps the registered external bookmark and per-App-ID
assignments internally, including partial installs. An existing assignment cannot
change destination. Transactions validate and atomically write the new catalog
before publishing it in memory; corrupt catalogs fail closed rather than resetting
to an empty internal library. These primitives are not yet wired to the install UI.

`SteamExternalAccess.perform` spans an entire async operation with a coordinated
accessor. Its cancellation bridge cancels the operation and waits for its cleanup
before returning and releasing the scope. The production-code host integration
suite passed migration, destination persistence, retarget refusal, failed-write
rollback, corrupt-record refusal, moved-root resolution, cancellation before
starting, and cancellation cleanup checks. All 64 app Swift sources type-check
for iOS with these additions. Live async downloader integration is still pending.

The runtime harness now also has a `FRONTEND=source` mode: the complete checkout
Swift interface links to the preserved native binary. Three hidden native symbols
are forwarded to verified existing implementations, with a hash-pinned input and
per-source/output provenance. It compiled, signed, installed in the disposable
probe container and launched a running `MadeiraSSDSource` process. This provides
a device-test route for the upcoming Swift integration; native changes remain
separate. Visual acceptance and Steam sign-in are pending. The owner confirmed
Brotato is only in the working app; no game or credentials were copied from it.

### Downloader I/O follow-up

The existing host integration suite also passes two new production-downloader
cases: an interrupted tree with a corrupted but journaled chunk is repaired while
other valid completed chunks are reused; and a preexisting `common` symlink cannot
redirect an install outside its library. Payload, journal, cache and install-record
paths now reject symlink components. Payload opens use `O_NOFOLLOW`; journal opens
do likewise and use throwing FileHandle APIs. A journal flush failure stops the
install before the final record is written, instead of raising an Objective-C
exception or silently publishing completion. These are host checks, not a live
SSD unplug-during-download result.
