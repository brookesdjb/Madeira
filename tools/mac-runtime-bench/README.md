# Mac runtime bench proof of concept

Runs FEX's **unchanged production buffer-pool implementation** on Apple Silicon
macOS. This is a component test bench, not a Mac port of Madeira or a game
benchmark. It does not use the iPad, Steam, game saves or the app's Wine prefix.

## Run

From the repository root:

```sh
python3 tools/mac-runtime-bench/run.py
```

Only Xcode command-line tools and Python 3.10+ are needed; fmt headers come from
the existing FEX submodule. No package download is performed. The runner compiles
an ASan/UBSan build, checks it once, then compiles an optimized build and checks
it three times. Binaries, build logs and JSON reports go under ignored `runs/`.

To test a different local FEX checkout and compare it with a saved baseline:

```sh
python3 tools/mac-runtime-bench/run.py \
  --fex-root /absolute/path/to/candidate/FEX \
  --compare /absolute/path/to/baseline/report.json \
  --repeats 5
```

The candidate needs its normal FEXCore and fmt headers. The report records the
FEX revision, dirty status, compiler, host, app revision and input header hashes.
The comparison requires the same harness, machine model and compiler. It reports
raw claim-latency measurements, not a statistically established improvement.
Use alternating baseline/candidate runs for a real performance investigation.

## Using a new worktree

Create the worktree from a commit containing this directory. For isolated FEX
headers, initialize only the dependencies this bench needs, then run it:

```sh
git submodule update --init FEX
git -C FEX submodule update --init External/fmt
python3 tools/mac-runtime-bench/run.py
```

The initialization commands may download dependencies. Alternatively, use
`--fex-root /absolute/path/to/an/initialized/FEX` to share an existing checkout
for read-only baseline tests. Do not edit that shared checkout from multiple
worktrees; use isolated submodules for candidate header changes. Each worktree
keeps its own ignored reports and binaries under this directory's `runs/`.

## What executes

`bench.cpp` includes `FEXCore/Utils/ThreadPoolAllocator.h` directly. The production
`PooledAllocatorVirtual` and its ownership, reuse, reclamation and locking code
execute without edits. FEX's metadata allocation and logging functions use small
host adapters. Its mmap/munmap hooks target an explicitly bounded 8 GiB arena.

The arena backend is a **test model**, not Wine's virtual-address allocator or
rpmalloc. It uses one real `PROT_NONE` reservation, first-fit suballocation,
read/write protection for allocated extents, and adjacent-free-range coalescing.
Allocation exhaustion returns NULL to model the Windows VirtualAlloc contract
in the observed iPad path. No executable mappings are made. Only sentinel words
are touched; reserving 8 GiB does not fill 8 GiB of physical RAM.

The original seven checks run:

1. 512 live 16 MiB buffers fill the arena; the 513th fails. The production pool
   currently records this NULL as an owned buffer. The harness detects it without
   dereferencing it. **Passing this test reproduces a known unsafe behavior; it
   does not certify production OOM handling as safe.**
2. 1,000 release/reclaim operations reuse a single backing allocation.
3. Alternating 8 MiB holes leave 4 GiB free but cannot satisfy a contiguous
   16 MiB request; releasing all remaining blocks restores the whole arena.
4. A disowned buffer is aged by changing its exposed timestamp in the fixture.
   Production reclamation invalidates its old owner and reuses it; the previous
   owner must obtain a different live buffer. No artificial sleep is needed.
5–7. 4, 9 and 84 native host threads each execute 100 synchronized claim/release
   rounds, checking distinct live buffers with boundary sentinels and measuring
   claim latency. These are worker counts, not simulated CPU-count settings.

Four additional pressure fixtures run, as described below. Expected null cases are marked in JSON. Every case also checks cleanup. Sanitizer
results are correctness checks; only optimized runs appear in timing summaries.

## First validation: 2026-10-10

On this Apple Silicon Mac, seven checks passed under AddressSanitizer and
UndefinedBehaviorSanitizer, then passed in three optimized runs. Build times were
about 3.1 seconds sanitized and 1.7 seconds optimized; individual optimized suites
took 0.09–0.24 seconds. These are observations from one run, not portable targets.

The tests reproduce the unchecked-NULL pool behavior implicated by Tomb Raider's
crash. They do not reproduce the full game's allocation history: 84 simultaneous
16 MiB buffers reserve only 1,344 MiB. The actual iPad arena also contains other
FEX allocations. We need an allocation trace to model that workload faithfully.

## Execution-runner feasibility

The existing `FEX/build-ios/CMakeCache.txt` targets `iOS` and `iphoneos`; its core
archives are not a validated native macOS runtime. FEX's top-level CMake accepts
Darwin, but gates the `Source/` executables behind `if (NOT APPLE)`. There is no
ready-to-run Mac Wine/FEX guest launcher in this proof of concept.

The next separate milestone is a Darwin FEXCore build with an explicit host/JIT
adapter and a tiny x86 execution fixture, followed by a Wine-integrated probe.
An ordinary native ARM program or a Rosetta run would not verify that path.

## Interpretation limits

This bench can detect pool regressions, exercise failure behavior and compare
host-side contention. It cannot measure Tomb Raider FPS, GPU time, iPad JIT alias
behavior, iOS memory limits, thermal throttling or real Wine allocation placement.
A faster Mac result needs iPad confirmation. Existing FEX contribution policy is
respected: the harness is outside that submodule and its source is unchanged.

## Local pressure-reclamation experiment: 2026-10-10

```sh
python3 tools/mac-runtime-bench/run.py --pressure-experiment --repeats 10
```

This builds the unchanged production pool and an experimental `PressurePool`
subclass in `pressure_pool.h`, outside FEX. Both inherit the production claim,
reown, disown, ownership flags, lists and mutex. Only the subclass's backing
allocation hook changes: if allocation returns NULL, atomically revoke disowned
buffers regardless of age, release them and cached unclaimed buffers, then retry
once. Active buffers are never eligible. Normal successful allocations and
cached-buffer reuse do not enter this pressure path.

The existing implementation already reclaims disowned buffers after five seconds
and frees up to one expired unused buffer per claim. It does **not** do this in
response to allocation failure. The candidate tests bypassing that age threshold
only at failure. It is deliberately broad (release all idle buffers), so could
create churn when those clients resume. A refined implementation could first
reuse a suitably sized disowned buffer and release only as much as needed.

The additional fixtures fill the same 8 GiB arena and check:

- A recently disowned 16 MiB buffer can be recovered while another buffer stays
  active and its boundary sentinels remain intact.
- Two adjacent disowned 8 MiB buffers can be released to satisfy a 16 MiB claim.
- Two adjacent unclaimed 8 MiB buffers can likewise be released before expiry.
- 100 races between lock-free reownership and pressure reclamation have exactly
  one winner. A successful reowner's contents survive; a revoked owner cannot
  dereference its obsolete iterator via `TryToReownBuffer`.

The original all-active exhaustion and interleaved-fragmentation fixtures still
return NULL. This candidate **does not fix unsafe production NULL ownership**:
that behavior is retained and asserted so recovery is not mistaken for complete
OOM handling. Its retry adds another failed backing call when nothing helps.

Observed result: both variants passed all 11 cases under ASan/UBSan, then all
11 cases in each of 10 optimized trials (242 case executions total). Each of the
three recoverable pressure fixtures failed in production and succeeded in the
candidate. The harness checked 1,100 reown races per variant including sanitized
runs. These checks do not prove all possible interleavings; TSan was not run.

Optimized variants alternate AB/BA order. Median per-run p95 claim latency:

| Native workers | Production | Pressure candidate | Production range | Candidate range |
| --- | ---: | ---: | ---: | ---: |
| 4 | 6.687 us | 6.917 us | 4.125–12.083 us | 3.083–9.166 us |
| 9 | 21.875 us | 21.917 us | 18.750–30.584 us | 15.708–26.583 us |
| 84 | 118.438 us | 105.855 us | 103.292–125.750 us | 51.333–123.250 us |

Ranges overlap substantially. These short synthetic contention runs neither
establish a speedup nor rule out small overhead. They measure normal claim/reuse,
not compilation throughput or stall recovery latency. The whole experiment took
14.0 seconds, including four compilations. Source fingerprints, raw release
samples and correctness evidence are in `pressure-results.json`; the full report
and binaries are in ignored `runs/20261010T134100.658065Z/`.

This is a successful feasibility experiment for pressure recovery, **not a
Tomb Raider performance improvement**. No production FEX files or iPad state
were changed. There is still no evidence linking the game's 4 FPS minimum to
this allocator. The next useful evidence is a real allocation/ownership trace
around a repeatable stall, followed by replay in this bench. Before integrating
any fix, handle unrecoverable allocation failure explicitly and evaluate churn
when revoked clients resume.
