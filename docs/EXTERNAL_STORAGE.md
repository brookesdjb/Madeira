# External SSD implementation record

Status on 2026-10-09: **Brotato and Borderlands GOTY downloaded to the SSD and
are user-confirmed playable through Madeira Dock using the scoped C: alias in
the mixed-source build.** Borderlands also passed the reported unplug/reconnect
download-resume sequence. Its successful launch followed the isolated runtime
configuration change described below; DirectX returned a nonzero prerequisite
status despite successful gameplay.
The user reported that the first splash initially appeared windowed, then became
fullscreen after tapping the game, and gameplay appeared normal. This records the
observed focus behaviour without changing graphics or JIT settings. The live
numeric Dock report independently confirmed `session-requested-app-listed=1`,
`launch-install-directory-verified=1`, `launch-client-error=0` and
`launch-game-running=1`. Reconnect/relaunch also passed on source-v6. Save continuity and the remaining
physical matrix for [issue 131](https://github.com/willfaust/Madeira/issues/131)
are still outstanding. The working original app remains separate.

The first physical reconnect test exposed recovery failures: the library showed
Connect SSD but still offered Play; a missing-provider error remained after
reconnecting until app restart and folder reconnection. A failed cloud check
then retained the same provider error, and Launch Anyway allowed gameplay.
This is not a passed reconnect/save-continuity test. The user also reported the
menu Exit action does not work in stock Madeira, requiring app close/reopen;
that pre-existing issue is recorded separately and was not changed here.

Source-v6 preserves the original picker bookmark unless resolution marks it
stale, rather than rewriting it from every coordinated access URL. Invalid
cached access is dropped; folder reauthorization resets the weak access cache.
External launch paths validate storage before JIT/cloud prompts, Play is disabled
when storage is known unavailable, and Game details offers Check SSD connection
and folder reconnection. Restored access invalidates only failed cloud checks,
requiring a fresh audit while preserving save conflicts and active transfers.
Provider failures become an actionable storage message. Host library, Dock
contract and cloud checks passed; on-device recovery remains to be retested.
The 65-source mixed build compiled, linked and signed successfully at
`/tmp/madeira-ssd-source-v6` (with provenance) and installed after the user
confirmed the test app was closed. It was left closed for the requested
unplug/open/reconnect/check-connection test.

The user confirmed source-v6 recovered successfully in that sequence, without
reporting another restart, folder selection or cloud bypass. The first connection
check appeared to pause or ignore the tap; a second tap confirmed immediately.
Gameplay resumed after an approximately 30-second windowed splash pause. Save
continuity was checked separately: the user reported that it appears to have
loaded the existing save. This is user-observed continuity, not a byte-level save
comparison or cloud upload verification. The launch log
shows Play at 18:53:11, online authentication at 18:53:19, entitlement at 18:53:24
and client launch error 0 at 18:53:26; this explains roughly 15 seconds of startup,
not the entire user-observed splash pause. It does not establish an SSD-specific
graphics or performance regression.

Source-v7 adds observable connection-check progress and suppresses duplicate
checks. Marker/read-only validation after acquiring access and the final marker
verification now run on a utility task, retaining the lease, instead of doing
removable-filesystem I/O on the UI actor. The check logs only availability and
elapsed milliseconds. No graphics/JIT settings were changed. All 65 Swift sources
compiled and linked successfully; source-v7 was signed, installed after the user
confirmed the test app was closed, and launched. Build/provenance output is
`/tmp/madeira-ssd-source-v7`. On-device responsiveness of the check remains to be
confirmed; the reconnect and save observations above were on source-v6.

On source-v7, the user reported that the SSD was detected as connected as soon
as it was plugged in, and the game worked. The unavailable Play control still
looked enabled and tapping its area opened storage options. Source-v8 addresses
both presentation issues: the custom Play style now respects `isEnabled`, the
disabled control reads `SSD unavailable` with a drive-warning icon, and storage
options is a separate borderless button/sheet instead of a NavigationLink that
can capture the surrounding Form row. Check connection is also borderless.
No storage routing, graphics or JIT behaviour changed in this UI increment.
All 65 Swift sources compiled/linked and the source-v8 app signed successfully;
build/provenance output is `/tmp/madeira-ssd-source-v8`. After the user confirmed
the test app was closed, installation succeeded. It was left closed for a focused
disconnected-button, separate-storage-options and reconnect UI check.
The user confirmed that this check worked as expected: the disconnected control
and separate storage-options action behaved correctly. After reconnecting,
one tap on Check SSD connection immediately restored Play. This validates manual
connection refresh on source-v8; automatic detection is not required or claimed
for that run.

## Download recovery polish prepared while device testing is paused

The owner selected Borderlands GOTY (8980) for the next interrupted-download
test, then deferred it while away from the iPad. The later device results are
recorded below. The device baseline captured before that test contains 1,312 regular
files, 1,368,320,927 bytes, and zero internal Steam game-payload bytes, excluding
external aliases and symlinks (`/tmp/madeira-borderlands-ssd-baseline.json`).

Source-v9 keeps the installed source-v8 app untouched while preparing:

- Partial/discovered records and pending updates retain Pause/Resume/Retry
  controls; they do not incorrectly replace those controls with Open.
- The download sheet offers Check SSD connection and explains that partial
  files remain on the original SSD. Resume, retry and repair are disabled while
  that storage is known unavailable. Installed updates no longer show the
  first-install cancellation prompt that says downloaded files will be deleted.
- Game details names the selected library; free-space displays clear stale
  values and refresh after storage availability changes.
- An operation error is distinguished from loss of the volume. A healthy
  destination preserves network, depot and low-space errors. Cancellation does
  not re-query the provider or mark it disconnected. Failed validation of a
  missing/replaced library still overrides completion and requires recovery.

Production host library and games suites passed under AddressSanitizer, with
new cases for partial-install controls, pending updates, network errors,
cancellation and destination revalidation. These are host results for source-v9;
the subsequent physical Borderlands interruption test used source-v8.
All 65 production Swift sources compiled and linked against the preserved
runtime, and the source-v9 app was signed successfully. Ready build and provenance:
`/tmp/madeira-ssd-source-v9`. It has not been installed; source-v8 remains on the
iPad during the ongoing gameplay test.

The owner subsequently reported that the installed build stopped gracefully at
248 MB during the Borderlands GOTY download, requested SSD reconnection and
resumed from the stopped position after reconnect/Try again. Completion was not
confirmed at that point. Later the prerequisite phase stalled at PhysX. The live
installer report shows MSVC returning 0 followed by PhysX starting without an
exit record. The storage catalog identifies the registered external library and
13,148,046,648 bytes, with installed=true but pending=true; this does not establish
that all download/update work is complete or that the game is playable.

The owner identified a prior-chat workaround, `MADEIRA_WOW_SMALL_VA_SLOTS=4`.
The disposable app had no override (source default 2). At the owner's request,
only its `env.MADEIRA_WOW_SMALL_VA_SLOTS` config key was set to 4 and read back to
verify, preserving other settings and leaving the original app untouched.

After reopening, the owner saw a paused transfer and resumed it. The reported
local-file verification completed quickly, followed by one-time installation,
Steam sign-in/license confirmation and successful fullscreen Borderlands
GOTY gameplay. A fresh catalog inspection confirms installed=true, pending=false,
13,148,046,648 bytes and the registered external library identity. Dock reports
session-requested-app-listed=1, launch-install-directory-verified=1,
launch-client-error=0 and launch-game-running=1.

The latest prerequisite report records PhysX exit 0, AMD CPU exit 0 and DirectX
exit -1073741800 (0xC0000018), followed by end. This confirms PhysX completed
after the configuration change and restart, but does not prove the setting was
the sole cause or that all prerequisites succeeded. Successful gameplay does
not erase the DirectX installer failure; its impact remains unverified.

The owner again saw the Windows desktop before the game reached fullscreen,
as with Brotato, and reports not seeing this in stock Madeira. Record this as
an unresolved startup-presentation difference, not a demonstrated SSD graphics
regression. The source-v9 control fix covers the confusing Open/Play action while
a transfer is pending, but has not yet been installed or device-tested. No app
replacement or restart was performed during this gameplay check.

The first Brotato SSD install attempt in source-v2 stopped at the capacity gate:
the user reported 0.2 GB required and 0.0 GB available. A read-only inspection of
the disposable app's catalog confirmed the registered external destination;
the attempt had not silently selected internal storage. Source-v3 replaces the
single important-usage capacity query with `SteamStorageCapacity`, shared by the
downloader and free-space UI. When important-usage capacity is zero or absent,
it queries ordinary volume capacity and filesystem free bytes at the same scoped
destination. True zero still blocks installation; unavailable capacity throws
instead of becoming unlimited space. Regression checks cover these cases and a
real host-volume query. Device retry remains required to confirm this fixes the
reported SSD result. Apple's capacity properties are documented at
https://developer.apple.com/documentation/foundation/urlresourcevalues/volumeavailablecapacityforimportantusage.
Source-v3 compiled and linked all 65 Swift sources against the preserved runtime,
was signed, installed over the disposable test app, and launched successfully.
Its build/provenance output is `/tmp/madeira-ssd-source-v3`; host library and games
suites passed under AddressSanitizer, and the iOS source type-check passed.
The user confirmed the retry installed successfully. The catalog records app
1942280 installed on its registered external identity, with 245,990,176 payload
bytes. The subsequent launch showed the generic identity-mismatch alert.
The old prototype registration and current library IDs match, but no launch
mapping owner record exists. Source-v4 adds ownership handover from the isolated
prototype's persisted registration for E: only, normalizes mapping comparisons
to canonical paths, and distinguishes a mapping conflict from a folder identity
failure. It still refuses to replace real directories or unowned unrelated links.
Host checks cover stale owned mappings, matching unowned targets, unrelated
unowned mappings, real directories and mismatched destination markers. The
physical launch retry is required to establish whether this resolves the alert.
Source-v4 compiled/linked 65 Swift sources, signed, installed over the disposable
app and launched successfully. Output/provenance: `/tmp/madeira-ssd-source-v4`.
The host library suite and iOS type-check passed; the user was asked to retry Play.
The retry passed storage setup but exited without a final Dock result. Inspection
found that the prototype's `env.MADEIRA_EXE` still forced `ssd_probe.exe`; its
empty `env.MADEIRA_ARGS` override also remained in Documents/madeira.cfg. The
runtime log showed the fixture executing and exiting with code 4, so this was
not evidence that Brotato or Valve's client had started. The narrowly matched
`clear-probe-overrides.py` cleanup removed only those two fixture settings in the
disposable app, verified the written file and restarted the app. Its self-test
passed. No game data or sign-in was changed. The next user Play check returned
Dock code 41. The numeric report confirmed `launch-install-directory-mismatch=1`,
and Valve's content log stated `Install folder E: not mounted`. Both Steam library
files listed E:, so registration alone did not establish client mount support.
Source-v5 registers the existing owned `C:\MadeiraExternalLibrary` alias with
Valve and sets Dock's expected path to that identical alias for this diagnostic
runtime. The exact install-folder check, authentication and licence gates remain
unchanged. Host tests cover matching registration/expectation and keeping aliased
SSD games out of internal discovery. A physical retry is required.
Source-v5 compiled/linked all 65 Swift sources, signed, installed and launched
successfully (`/tmp/madeira-ssd-source-v5`, including provenance). The host
library and Dock contract suites passed under AddressSanitizer. The user has
been asked to retry Play with the new client registration.

After installation, the disposable app container contains 951 regular files
totalling 1,302,539,848 bytes, versus 863 files and 1,288,441,301 bytes before the
download: growth of 14,098,547 bytes. Internal `steamapps/common` payload bytes
remain zero. Both measurements exclude symlinks and the E:/C: external aliases;
the container therefore does not contain a second copy of the 245,990,176-byte
game payload. These are device file-service observations, not gameplay evidence.

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
  display name and bookmark. C: is internal; E: is the registered external
  mapping. The source native bridge resolves E: only with the matching marker;
  the mixed-source diagnostic build needs the compatibility alias below.
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
| `tests/host/typecheck-ios.py` | PASS, all 65 production Swift sources and real bridging header against iOS SDK; no native linking |
| Standalone probe | Debug unsigned and signed build PASS; installation and foreground launch PASS |
| First SSD test | User reported PASS on physical iPad: bookmark resolve plus data operations |
| Restart/unplug/reconnect | User explicitly confirmed FAIL unplugged, PASS reconnected without selecting the folder again |
| Full native source app | Still blocked by missing resources/native archives |
| Source Swift interface + prebuilt native runtime | 65-source compile/link, signing, isolated installation and launch PASS; user confirmed the interface opens |
| External Windows EXE/DLL + relative asset/save | PASS in the isolated prebuilt-runtime harness, confirmed by the user |
| Brotato SSD install | PASS, user confirmed; 245,990,176 payload bytes recorded externally; no internal game payload copy |
| Dock and Brotato launch from SSD | PASS on source-v5 using scoped C: alias; user-confirmed gameplay and numeric Dock evidence; initial focus/fullscreen quirk noted above |

The Wine resolver input can be reproduced without initializing all of Wine:

```sh
curl -fLsS https://raw.githubusercontent.com/willfaust/wine/257f271cfffed9f22f7987cac53bc00095d092fe/dlls/ntdll/unix/file.c \
  -o /tmp/madeira-pinned-wine-file.c
WINE_FILE_C=/tmp/madeira-pinned-wine-file.c python3 tests/host/check-dock-path.py
```

This checks the existing Unix namespace handoff; it is **not** proof of E: or
external executable loading. No physical read-only, permission-revocation,
>4 GiB, APFS/exFAT comparison, background expiration, game-session unplug, or
tests have been performed. Internal-storage growth was measured above.

## Integrated library behavior and remaining device gate

The native Dock source's `src/launch.c` normalizes Steam's actual install path
with `GetFullPathNameW` and compares it case-insensitively with
`MADEIRA_STEAM_HOST_EXPECTED_INSTALL`. That comparison is not limited to C:.
The controlled fixture proved E: EXE/DLL/asset/save access. The production source
now carries library identity through queues, downloads, retries, resume, update,
repair, deletion, discovery, metadata, launch paths and GameInstall cloud saves.
Legacy entries without a library ID remain internal. Existing installations are
not moved. A saved partial destination cannot be retargeted by a later choice.

Settings → Game storage registers or reauthorizes the one external folder. The
uninstalled game's page has an explicit Download to picker. Its capacity is
read from that library's volume. Download payloads, journals, caches and install
records use its `steamapps`; prefix, client and normal user folders stay internal.
Discovery keeps internal snapshots when the SSD is absent. A failed save audit
cannot acknowledge missing external files as deleted saves.

A reference-counted access lease retains one coordinated accessor and security
scope across async operations and the entire Wine session. Save operations during
a session share that accessor rather than deadlocking on a nested coordinator.
The last client releases it only after its handles are closed; the session owner
waits for both Wine and wineserver to stop. Hardware disconnection can still end
an operation/session and cannot preserve unsaved game state.

Before launch, the app validates the marker, updates its owned E: symlink, and
writes a bounded `libraryfolders.vdf` update preserving unrelated entries. The
prefix's owner record prevents stealing another mapping. Native source resolves
E: working directories and PE types without a Z: fallback. One-time installer
lookup receives the external game root while scripts and registry remain internal.

**Mixed-source build limitation:** the preserved native binary has a C:-only
working-directory and direct Steam-identity bridge. Only this diagnostic build
creates a second owned `C:\MadeiraExternalLibrary` alias to the same scoped root
and passes that alias as the direct launch's working folder/SteamAppPath. Valve's
library registration and Dock expected-install path also use this alias after
the client rejected the E: volume. Canonical executable paths and external
discovery retain the registered external identity and E: path.
This does not patch the native binary. Direct external 32-bit starts are refused
in this build because its old PE probe cannot inspect E:. The native source fix
is host-tested and syntax-checked, not linked into the published runtime.

Still required: direct Brotato gameplay, save continuity after reconnect, download unplug/resume,
background/foreground/cancel, low-space/read-only, >4 GiB, APFS/exFAT where
available. Before/after internal growth is recorded above. File-presenter relinquishment under
other coordinated clients remains unverified. The test app's pre-download
baseline was 1,288,441,301 regular-file bytes (863 files), excluding symlinks and
external aliases, with **zero bytes in the internal Steam game payload folder**.
That is a baseline, not a completed no-duplication measurement.

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
to an empty internal library. These primitives now back the install destination UI.

`SteamExternalAccess.perform` spans an entire async operation with a coordinated
accessor. Its cancellation bridge cancels the operation and waits for its cleanup
before returning and releasing the scope. The production-code host integration
suite passed migration, destination persistence, retarget refusal, failed-write
rollback, corrupt-record refusal, moved-root resolution, cancellation before
starting, and cancellation cleanup checks. All 64 app Swift sources type-check
for iOS with these additions. These operations are now wired to the storage model; live disconnect/cancellation checks remain pending.

The runtime harness now also has a `FRONTEND=source` mode: the complete checkout
Swift interface links to the preserved native binary. Three hidden native symbols
are forwarded to verified existing implementations, with a hash-pinned input and
per-source/output provenance. It compiled, signed, installed in the disposable
probe container and launched a running `MadeiraSSDSource` process. This provides
a device-test route for the upcoming Swift integration; native changes remain
separate. The user confirmed the source interface opens, completed the SSD download and confirmed gameplay on source-v5. The owner confirmed
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

## Source-v9 installation for the next device check

After confirming Borderlands ran well, the owner requested installation of the
next test build. The prepared source-v9 app passed strict/deep code-signature
verification, installed successfully over the isolated SSD test app and launched
on 2026-10-09. Post-install readback confirms
`env.MADEIRA_WOW_SMALL_VA_SLOTS = 4` remains set and Borderlands retains
installed=true, pending=false and 13,148,046,648 catalog bytes. The original
Madeira bundle was not targeted. This establishes deployment and preserved
configuration/catalog state, not device acceptance of the new controls.

Next owner check: start a fresh SSD download for another game, pause it, reopen
the app and verify Resume remains available instead of a misleading Play/Open
action. With that transfer paused, unplug the SSD and verify the download sheet
provides connection recovery and blocks resume until the library is available;
reconnect, check connection and resume the existing transfer.

## Source-v10: game-details transfer controls and retained byte counts

The source-v9 owner check exposed a separate route: the home card said Paused,
but the installed game's details header still offered Play and its Steam section
said Resume update. After reopening, no transferred byte counts were displayed.
The earlier sheet fix did not cover the LibraryDetail header.

LibraryDetail now observes download changes and replaces Play with shared
Pause download / Resume download / Retry download controls while a transfer
exists. The header also displays progress; its Steam section uses the same
controls. Both respect unavailable storage for resume/retry. Paused progress
includes completed and total bytes. A catalog display snapshot is saved at most
every five seconds during progress and again when a transfer stops, restored
on app startup, preserved during install rediscovery and cleared on completion.
SSD journals and chunk verification remain authoritative for actual resume.
Older paused records have no snapshot: they explicitly ask to resume to check
downloaded files; they do not show a fabricated amount.

Production host games and library checks passed under AddressSanitizer,
including snapshot persistence through restart/rediscovery and cleanup on
completion. The owner confirmed the app is closed with its download paused for
replacement. Device build and acceptance are tracked below.

Source-v10 compiled and linked all 65 Swift sources, passed strict/deep signature
verification, installed successfully in the isolated app and launched. Build and
provenance: `/tmp/madeira-ssd-source-v10`. Device acceptance of the header and
pause/reopen progress display remains pending; the next check resumes the
existing paused download long enough to calculate totals, pauses it and reopens
the app to compare the saved counts and Resume control.

## Source-v11: removal detection while a card stays open

The owner confirmed source-v10 shows Resume download and resumes successfully.
Unplugging while paused did not disable Resume until the game card was closed
and reopened. Reconnecting and using Check SSD connection then restored it.
This isolates missing live refresh in the visible card; persisted byte counts
across reopening have not yet been explicitly confirmed.

The game-details and download-sheet views now run a foreground-only availability
monitor. Every two seconds, while the library is considered connected, it uses
the existing off-main-thread identity validation and publishes a failed check.
The monitor holds its scoped lease between checks, releases it on failure or
view-task cancellation, and stops with dismissal/backgrounding. It does not
scan game payloads, start downloads or repeatedly reopen a disconnected provider;
Check SSD connection remains the reconnect action. This changes detection while
a card stays open, not the downloader's operation-time validation.

The games host suite passed under AddressSanitizer. All 65 Swift sources compiled
and linked, and the source-v11 app passed strict/deep signature verification.
After the owner confirmed the download was paused and app closed, installation
and launch succeeded in the isolated test bundle. Build and provenance:
`/tmp/madeira-ssd-source-v11`. On-device removal detection without closing the
card remains to be confirmed; allow several seconds for the periodic check and
provider response, then reconnect/check/resume in the same card.

## Host follow-up: pause during file verification

The detached preparation pass did not inherit cancellation from the download,
and checked cancellation only between depots. For large resumed games, Pause or
background expiration could leave verification touching the SSD for a long time.
`prepareForInstall` now forwards cancellation into its worker and awaits its
completion; preparation checks between files/chunks, and final install-record
publication checks cancellation too. Production host coverage uses an actual
5,000-file preparation plan, cancels after the first file appears, and verifies
that work stopped before completion and no further files appeared after return.
A pre-cancelled request makes no payload files. The full library suite passed
under AddressSanitizer. This is host evidence, not a new physical background test.

## Host follow-up: sparse resume space and large offsets

A new production preparation fixture reproduced a capacity-estimate bug: after
`ftruncate` set a partial file to its final length, resume treated that logical
length as already allocated and estimated zero new bytes for a missing chunk.
The estimator now uses POSIX allocated blocks, bounded by pending chunk bytes,
so it counts unallocated payload without charging for untouched sparse holes.
Unsupported file lengths above signed 64-bit offsets are refused before creating
the file instead of trapping on conversion.

The host fixture creates a sparse file slightly larger than 5 GiB, verifies and
reuses its first journaled chunk, checks space for the missing tail, then writes
and verifies the tail beyond 4 GiB. A complete resume estimates no new space.
The regression failed before the estimator fix and passed afterwards; the full
library suite passed under AddressSanitizer. This verifies host sparse-file
behaviour and offsets, not an iPad/exFAT/APFS physical large-file test or actual
low-space exhaustion on the iPad.

## Host follow-up: external GameInstall save containment

A synthetic cloud comparison reproduced following a nested symlink from an SSD
GameInstall save directory to a file outside the selected library. The external
cloud context now supplies its library root; case-insensitive save resolution
validates each existing path component using the storage path validator before
following it. Local-only enumeration validates candidate saves too. Unsafe paths
throw and fail the audit before a sync plan or baseline is recorded. Upload and
download use the same checked resolver. Internal Wine user-folder behaviour is
unchanged when no external root is supplied.

The cloud host suite now compiles the production storage validator alongside
its production comparison/planning code. It reproduced the outside-read bug
before the fix, then passed normal SSD/case-insensitive saves, linked ancestors,
local-only linked folders/files and dangling destination links after the fix.
This is synthetic save-path evidence; it does not establish a live Steam Cloud
upload or conflict-resolution result on iPad.

The large-file fixture additionally rejects a chunk extending past its declared
file length and an overflowing offset before any chunk read/write conversion.
Storage error classification now retains POSIX permission/read-only failures,
including errors wrapped by a provider, instead of calling them disconnected.
The full production library suite passed with these boundary cases.

## Startup presentation investigation

The current starting-screen suite passes new cases for both canonical E: game
paths and the scoped C: alias: drawn game windows end the hold, while windows
first seen during prerequisites remain installer windows. Existing census tests
also pass AddressSanitizer and ThreadSanitizer. Read-only inspection of the
hash-pinned runtime's `winios_window_census` shows a 304-byte copy stride, matching
the current C structure size; this rules out that simple stride mismatch, not
every possible native/frontend behavioural difference. Available device logs
from the current app run contain no historical launch-view transitions. There
is insufficient evidence to change reveal/focus policy, so no graphics, JIT or
starting-screen settings were changed. The user-observed startup desktop remains
an open physical observation.
