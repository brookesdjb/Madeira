# G1 shader-cache preparation

Tracks [issue #4](https://github.com/brookesdjb/Madeira/issues/4). No runtime or
default change is made. The existing `env.DXMT_IOS_CACHE_DIR = 1` experiment must
pass on iPad before promoting an x64 default, and a safe storage budget remains
part of that acceptance.

## Host checks

```sh
python3 tests/host/check-ios-cache.py --dxmt-root ../Madeira-performance/dxmt
```

The optional source-root argument allows a read-only pinned DXMT checkout; omit
it when this worktree's submodule is initialized. Audited pin:
`db546ee466ad50ec6463edb5fa183de11db43761`.

The test compiles the actual Objective-C resolver and SQLite reader/writer
methods under ASan/UBSan with host Foundation. It substitutes the sandbox cache
directory lookup, unavailable Darwin confstr lookup, guest bitness and a
SQLITE_FULL fault boundary. All filesystem work is in a disposable directory.
It checks:

- x64 default off, WoW64 default on, explicit `0` off, and existing nonempty
  override behavior (even unknown words enable it; use `0` for rollback).
- Relative file/directory resolution, absolute override preservation, missing
  cache-directory lookup, empty path and a file obstructing directory creation.
- Second/third object-session persistence, version separation, misses and
  independent writer/reader objects sharing one database.
- Simulated insertion-full failure/recovery and corrupt-database refusal.

These checks passed. Host object sessions are not physical game launches. No
Metal API, shader conversion or iPad sandbox behavior was tested. SQLITE_FULL is
injected, not an actual filled disk. Independent writers use sequential writes;
concurrent SQLITE_BUSY/retry behavior remains unvalidated. The source's existing
error-path resource management was not changed by this test.

## Ready-to-run device experiment

Use a fixed installed game/scene and the accepted harness's shared reservation.
Preserve the existing per-game config and caches, then vary only this override:

```ini
env.DXMT_IOS_CACHE_DIR = 1
```

Use `env.DXMT_IOS_CACHE_DIR = 0` as the explicit disabled comparison where
appropriate. Also retain the current-default arm: on x86, unset is already on,
so unset-versus-1 is not an off/on experiment. Restart the native app per arm.
Per-game configuration wins over global configuration; capture the effective
settings from the actual launch, not just the proposed fragment.

Validate cold, second and third launches, actual directory/database identity,
hit/miss evidence and visible correctness. `DXMT_CACHE_STATS=1` already exists,
but keep its logging policy identical across arms and quantify its overhead.
Separate shader conversion reuse from native PSO creation. Match binary/game/
scene/settings/thermal state and sampler/capture policy. Follow #2's repeated
paired and sustained protocol. Do not wipe saves or unrelated caches.

Before a default change, verify concurrent pseudo-process access, corruption,
full-disk behavior, version identity and a bounded storage/eviction policy with
real native/PE integration. A cached blob surviving these host checks is not a
measured loading or frame-pacing improvement.
