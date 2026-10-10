# Reproducible profiling and benchmark plan

## What ran in this investigation

Environment: x86-64 Linux container, no Apple SDK/device/GPU. Tests used the exact [source pins](architecture.md); no runtime changes were applied.

| Command, from repository root | Result | What it establishes / limitation |
|---|---|---|
| `python3 tests/host/check-fastsync.py` | PASS | Extracted engine selection, cell-generation/semaphore race models and source wiring; not physical Darwin/Windows wait latency |
| `ASAN_OPTIONS=detect_leaks=0 python3 tests/host/check-scene-batching.py` | PASS | Scene pairing, 256-op bound, FIFO, clear/hazard/Present drains; ASan/UBSan enabled, leak checking unavailable |
| `ASAN_OPTIONS=detect_leaks=0 python3 tests/host/check-d3d9-splitlock.py` | PASS | 4 × 20,000 split XADD model exact under strict lock; device-lock/source guards present |
| `ASAN_OPTIONS=detect_leaks=0 python3 tests/host/check-d9-upload-commit.py` | PASS | Production ring/extracted behavior is bounded with settle points; synthetic peak 1,088 MiB without settle vs 192 MiB with settle is a model result, **not device footprint** |
| Offline manifest/CSV tools | Verified with source inventory and deterministic valid/invalid CSV fixtures | No runtime hooks; cannot produce missing device timings |

The initial scene-batching run failed because LeakSanitizer could not read `/proc/.../task` in this runner and reported a ptrace restriction. Rerun only disabled leak detection; no source changed. ThreadSanitizer was not run. No FPS, JIT speedup or macOS/simulator performance was measured. Existing test programs are largely correctness tests, not throughput benchmarks.

## Reproducible build identity

From a checkout at the audited pin, retrieve the required submodules/toolchains following `docs/BUILDING.md`. Some recipes are explicitly marked unverified; do not treat the documentation as a clean-build certification. Rebuild both the native archive and PE DLL if an ABI or shared fork changes, and confirm the app stages the rebuilt output (DXMT combined archive in particular).

```sh
python3 docs/performance-investigation/tools/source-manifest.py > source-manifest.json
python3 docs/performance-investigation/tools/source-manifest.py --binary app/Madeira/arm64ec-windows/xtajit64.dll --binary app/Madeira/arm64ec-windows/d3d11.dll > source-and-binaries.json
```

Also record app binary/IPA hash, configuration, compiler/SDK, per-game overrides, effective FEX features/MaxInst, sync engine, Metal capabilities, device model/SoC/RAM, OS build, display refresh, resolution, render scale, frame cap, power mode and thermal state. Hash the actual installed build, not just source. Redact credentials and device identifiers from shared logs. Preserve diagnostic symbols locally; shipped PE DLLs may be stripped.

The user fork’s physical-iPad automation branch has a host-tested Appium/devicectl smoke controller; its status still marks physical JIT coexistence and performance collection unvalidated. See [architecture](architecture.md) for exact branch commits. Reuse it only after proving normal launch, JIT and capture on the provisioned Mac/iPad; it does not replace raw frame instrumentation.

## Physical M-series iPad protocol

1. Use the same iPad, OS, game version, save, route/camera/input sequence and graphical settings. Include an older M-series and newer M-series device when changing feature detection. Do not mix simulator results into that table.
2. Verify app launch and JIT authorization normally; caching does not replace it. Start a fresh app process for configuration cached at process initialization. Avoid a second pseudo-session inheriting old FEX/sync state.
3. Use one CPU-heavy x64 scene, one x86/D3D9 case, one D3D11 streaming/shader case and one D3D12 shader-heavy case. If available, use a game with launch helpers and one with frequent readback/query polling.
4. Establish a correctness baseline: screenshots/camera position, audio, controls, loads, exit, no new errors. Keep resolution and cap identical for latency comparisons; run an additional uncapped throughput experiment separately.
5. For warm gameplay, settle for 60 seconds, record 180 seconds, repeat at least five paired A/B runs in randomized AB/BA order. Return to the same thermal starting state rather than using only a fixed cooldown interval. Also run 15-minute sustained sessions for thermal/memory behavior.
6. Measure cold launch, first traversal and warm traversal separately. For G1, retain the baseline caches as a backup and vary only the relevant DXMT cache directory; do not wipe unrelated game saves or every shader cache. Distinguish process-warm, disk-warm and OS-compiler-cache-warm states.
7. Compare p50/p95/p99 frame times, frames over 16.67/33.33 ms, load-to-interactive time, per-role CPU time, peak footprint, GPU duration, crashes and correctness. Report pairwise differences and between-run spread; choose a practical improvement threshold before inspecting results. Reject a short burst gain accompanied by sustained thermal regression.
8. Run both low-overhead telemetry and a separate short Instruments capture. Report the overhead of profiling itself. Uncontrolled anecdotal FPS changes are not evidence for landing a default.

Simulator can help test UI/configuration and some harness paths, but its executable-memory rules, scheduler, host CPU and graphics driver are not those of an iPad. macOS can validate algorithm/Metal semantics where supported, but macOS timings do not prove iPad JIT, thermal or memory behavior.

## Existing facilities and their limits

| Quantity | Existing source/facility | Gap / proposed minimal addition |
|---|---|---|
| Per-thread CPU | App `CPUMeter`, `DeviceLoadDiagnostics`; server `ios_xprobe_main` | Use Mach user/system-time deltas by stable native TID; attach Wine PID/TID and role; don't equate % of all cores with one-core saturation |
| Guest vs native work | `ios_thread_sampler_main`, `ios_guest_rip_profile`, FEX host-PC→guest-RIP metadata | Gates required (X1). Sample categories with unresolved fraction; don't count every address in executable pool as translated guest code because native PE copies share it |
| JIT compiles/cache | FEX `CB_SUMMARY`, code-buffer generation and lookup-cache logs; `ThreadStats` lock-time fields | Count real compiles, C++ hits, discarded duplicate IR, emitted bytes and invalidation causes per thread; current global diagnostic counters can race/contend and are not a rigorous cache hit-rate measurement |
| Wineserver requests | Client `server_call_unlocked`, server `request_ios.c` request census | Timestamp send/reply and handler entry/exit by opcode; separate queue delay from service time; bounded histograms rather than per-request log IO |
| Wait/lock latency | madsync contention/wake histograms; fastsync counters; thread-alert counters | Add wait reason, spin hit, local success/server fallback and timeout counts; keep arbitrary wait-all correctness tests |
| Metal CPU work | DXMT frame statistics, command-queue commit/sync intervals; D3D12 performance counters | Signpost encoding start/end and submission per queue/sequence; do not confuse queue-capacity waits with encoding CPU |
| GPU frame work | `AccountGpuTime`, `madeira_gpu_meter_*`; Metal capture controls | Correlate command buffers to rendered frames; union GPU intervals across queues; Metal counters only when exposed on that device/capture setup |
| Shader/PSO time | DXMT cache stats, task scheduler; D3D12 caches/prebuild counters | Distinct decode/convert/library/PSO/load/save durations and cache hit level; critical-path first-use wait |
| Allocations/memory | `dxmt_mem_census`, staging spare budget, Wine pool ledger, app memory overlay | Counters by allocator/category plus physical footprint, compressed/file-backed pressure, page-ins; virtual reservation is not residency |
| Frame distributions | Present paths and overlay aggregates | Export raw monotonic per-frame intervals to CSV; aggregate FPS logs cannot reconstruct p99 |

Proposed runtime instrumentation is **not implemented in this patch**. Add a compile-time profiling option and runtime bitmask, off by default. Per-thread fixed-size rings/histograms avoid hot-path allocations, global atomics and synchronous IO. For lock experiments sample a fraction of acquisitions rather than calling a clock on every uncontended lock. Flush on a background thread with drop counters. In exception/signal handlers, use only preallocated safe counters and no formatting/locks. Preserve all recovery behavior.

Reference points: `server_ios.c:1841–1877,4571–4587`; `FEX/Core/Core.cpp` is actually `FEX/FEXCore/Source/Interface/Core/Core.cpp:1920–1965,2118–2168`; `dxmt_command_queue.cpp:76–213,215–259`; `winemetal_unix.c:533–612`. FEX's profiling macros/Tracy hooks exist, but this checkout's build flags and missing nested dependencies do not establish a ready iPad trace export. Additions inside FEX must respect its contribution instructions.

## CPU translation microbenchmarks

Use existing `tests/x64/build.sh` and `tests/x86/build.sh` as the toolchain/launch templates. Existing `fib2`, `fib3`, `asmconf`, `fpconf`, `setjmp` and `clocktest` provide correctness seeds. They do not implement the timing sweeps below; the next implementation should add a guest-only benchmark executable under `tests/performance/` (outside FEX).

The benchmark contract is reproducible:

- Fixed xorshift seed `0x12345678`, no IO in the timed region, QPC timestamps only at region boundaries, checksum returned to prevent dead-code elimination. Build x64 and i386 variants with the same optimization policy; save disassembly/compiler version. Use fixed work per worker and report total operations divided by elapsed time.
- Cases: dependent integer arithmetic; indirect calls through 64 deterministic targets; sequential and randomized reads over 32 KiB/4 MiB/64 MiB; aligned contended/uncontended atomics; independently verified split-atomic correctness; x87/SSE helpers; repeated calls into one native Wine API.
- Workers: 1, 2, 4, then available logical CPU count, each with independent data/cache-line-padded counters. Start using one barrier outside the timed loop; do not hold a global mutex around the workload. Record per-thread CPU and total process CPU to prove overlap.
- Run 1 million iterations as calibration, then pick a fixed iteration count yielding roughly 2 seconds at baseline. Use that identical count for all variants. Keep cold first pass separate from ten repeated warm passes.
- F2 matrix: MaxInst 500/1,000/5,000, multiblock on, identical TSO/FP/AVX settings. Include Mono games because invalidation/Mono rules depend on block configuration. Run `asmconf`, `fpconf` and exception tests at every candidate setting.

## Synchronization microbenchmarks

Implement a small Win32 guest program with two auto-reset events for ping-pong: 10,000 warmup and 100,000 timed round trips, timestamp batches of 100 to bound measurement overhead. Compare standard Wine, fastsync auto/on and madsync in separate app launches. Distinguish auto's initial unarmed window from steady armed behavior.

Add semaphore producer/consumer (exact token conservation), N-worker fanout/join, multi-object wait-any and wait-all, alertable wait/APC, recursive/abandoned mutex, 0/1/10 ms deadlines and close/reuse stress. 1/2/4/N workers, fixed job sizes of roughly 10/100/1,000 microseconds at baseline. Report operations/s, p50/p99 round trip, context switches, spin CPU and server requests per operation. For W1, drive request bursts while interleaving stop and INET activity; inject a request in every pending-clear/scan/sleep race window and require bounded completion without the periodic tick rescuing a lost wake.

## Graphics microbenchmarks

Use `tests/dxmt/build-x64.sh`, `tests/x86/build-d3d9-cube.sh`, and the native D3D12 canary/tests as build/compatibility seeds. New benchmark variants should hold pixel work constant while varying draw count (100/1,000/10,000), then hold draw count constant while varying resolution. This separates CPU translation from GPU fill cost.

Test 1 versus 100 versus 1,000 unique PSOs, dynamic buffer upload sizes (4 KiB/1 MiB/16 MiB), Map discard/no-overwrite/readback, one versus many render passes, BC format support/decode, and command-buffer batching. Add resource release/reuse while GPU work is in flight; query/readback must match a CPU reference. Run Metal API validation/capture in correctness trials, then disable validation for performance trials. For G2 compare compiler caps 2/4/current policy, recording loading time as well as frame p99. For G5 compare existing async-submit off/on before changing the queue architecture.

## Offline analysis included here

Export one row per rendered frame, with required `frame_ms` and optional correlated `cpu_ms,gpu_ms`. These scripts do not parse aggregate logs into invented frame samples and do not collect a device trace.

```sh
python3 docs/performance-investigation/tools/frame-summary.py frames.csv --budget-ms 16.666667 > summary.json
```

The tool reports sample counts (optional fields can be missing), nearest-rank p50/p95/p99, mean/max, throughput `frames / total duration`, and over-budget count. It rejects empty/nonfinite/negative data. Do not combine generated/interpolated frames with guest-rendered frames. Keep separate files per run/scene/cache/thermal phase; analyze paired runs externally rather than pooling away run variance.

## Landing gate

A performance patch needs: exact source/binary/config manifest; before/after raw captures; a demonstrated mechanism (fewer scans, cache misses, copies, waits or CPU time); repeatable device improvement beyond baseline variability; unchanged visual/sync/exception correctness; no resource lifetime, memory-pressure, audio or sustained thermal regression; and one reliable rollback switch where behavior changes. A host model pass is necessary for some changes but never sufficient for an M-series iPad performance claim.
