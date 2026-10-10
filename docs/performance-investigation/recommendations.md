# Prioritized Madeira performance backlog

Audited source: `48f976429c189f8396e23d251d8a82f43c705922`, 2026-10-10. This commit adds investigation documentation and offline tools only. **No runtime optimization or measured FPS improvement is claimed.**

Read [architecture](architecture.md), [FEX](fex.md), [Wine](wine.md), [DXMT/Metal](dxmt.md), [cross-subsystem](cross-subsystem.md), and [benchmark plan](benchmark-plan.md) for the traces behind this backlog.

## Engineering conclusion

Madeira is one iOS task containing many independently schedulable pthreads. x64 game code is translated by FEX, while ARM64EC Wine and much of the x64 graphics stack execute natively. x86 uses a distinct WoW64/window path, including translated PE components and a native D3D9 frontend. D3D12 has a separate Madeira runtime. **It already supports multicore guest execution.** Its limits are serial services and dependencies—wineserver dispatch, shared JIT publication/invalidation, some initialization and PSO work—plus game dependencies, memory pressure and scheduling/thermal competition. There is no code-backed basis for a claim that all games run on one core.

C means confirmed source work/cost, S a strongly supported opportunity, H a hypothesis needing profiling. Even C does not mean a measured end-to-end bottleneck. Potential ranks benefit on the affected workload, not a universal FPS promise. Effort includes correctness validation. Priorities favor localized changes over uncertain large rewrites.

## Five first recommendations

### 1. X1 — gate task-wide diagnostic sampling

| Field | Recommendation |
|---|---|
| Subsystem | Cross-subsystem / Wine |
| Finding and evidence | C: three background diagnostic jobs launch outside the quiet check, despite the app setting quiet. They can suspend game threads, walk stacks and periodically enumerate task usage |
| Code location | `server_init_process_done`, [build/ntdll-unix/server_ios.c:4571–4587](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L4571-L4587); `ios_thread_sampler_main:1780`, `ios_xprobe_main:1488`, `ios_wprof_main:1697`; app quiet default at `WineProcessBridge.m:961` |
| Proposed code change | Add parsed-once `MADEIRA_PROFILE_THREADS`, `MADEIRA_PROFILE_XP`, `MADEIRA_PROFILE_STACKS` gates (proposed names), false by default; start only requested jobs. Retain one-time task ownership, error recovery, crash handling and existing user-selected overlay. Build-time disable optional for normal packages |
| Why it helps | Removes observer work, suspensions and log churn from normal gameplay, and makes subsequent measurements trustworthy |
| Performance potential | Medium: directly removes recurring work; magnitude depends on active profiler roles/scene |
| Implementation effort / compatibility risk | Low / low; distinguish diagnostic sampling from safety/recovery logic |
| Validation | Off means no diagnostic suspend calls/tasks; on still produces useful traces. Paired p99/frame/CPU/thermal runs plus launch/exit/crash tests |
| Upstream dependency | None; Madeira native source overlay |

### 2. G1 — make the iOS shader-cache directory policy work for x64

| Field | Recommendation |
|---|---|
| Subsystem | DXMT / integration |
| Finding and evidence | S: default relative cache path plus `use_ios_cache_dir()` default off for x64; source says the fallback confstr location is unavailable in the iOS sandbox. Existing absolute overrides are exceptions |
| Code location | `GetDXMTShaderCacheDirectory`, [dxmt/src/dxmt/dxmt_shader_cache.cpp:10–18](https://github.com/willfaust/dxmt/blob/db546ee466ad50ec6463edb5fa183de11db43761/src/dxmt/dxmt_shader_cache.cpp#L10-L18); `use_ios_cache_dir` / `resolve_cache_dir`, [dxmt/src/winemetal/unix/cache.c:25–92](https://github.com/willfaust/dxmt/blob/db546ee466ad50ec6463edb5fa183de11db43761/src/winemetal/unix/cache.c#L25-L92) |
| Proposed code change | First run `env.DXMT_IOS_CACHE_DIR=1` through existing app configuration. If verified, default the iOS resolver on for every bitness, keeping explicit 0/absolute-path/failure behavior; alternatively set an absent-only app default before cache initialization. Preserve versioned identities and enforce a safe storage budget |
| Why it helps | Reuses converted shader blobs/Metal cache location on later launches instead of repeating conversion; native PSO construction may still remain |
| Performance potential | High for repeat-launch/loading stutter if cache currently fails; low for a fully warmed unchanged scene |
| Implementation effort / compatibility risk | Low / low–medium: stale identity/concurrent access must be reviewed |
| Validation | Cold/second/third launch directory and hit counts, conversion vs PSO time, p99, cache corruption/full-disk fallback, simultaneous pseudo-process users |
| Upstream dependency | Existing switch usable in Madeira; permanent resolver patch belongs in the DXMT iOS fork, no general upstream redesign needed |

### 3. W1 — coalesce wineserver request wakeups

| Field | Recommendation |
|---|---|
| Subsystem | Wine |
| Finding and evidence | S: signal once per request and consume once per loop pass; multiple requests can be drained in one scan, leaving wake-token backlog and extra scans |
| Code location | `ios_wineserver_wake`, [build/wineserver/fd_ios.c:34–47](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/wineserver/fd_ios.c#L34-L47); iOS `main_loop` wake wait [build/wineserver/fd_ios.c:1390–1468](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/wineserver/fd_ios.c#L1390-L1468); client [build/ntdll-unix/server_ios.c:1841–1861](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L1841-L1861) |
| Proposed code change | Atomic pending/sequence protocol: publish request then signal only on transition to pending; server clears before draining, handles races and leaves a wake for post-scan work. Preserve timer/INET deadline and explicit stop wake. Keep existing path behind a rollback switch |
| Why it helps | Fewer Mach semaphore signals and unproductive full descriptor scans without delaying actual work |
| Performance potential | Medium, potentially high in server-heavy bursts; no expected help for pure GPU-bound frames |
| Implementation effort / compatibility risk | Medium / medium; lost wakeups and timeout regressions are central risks |
| Validation | Adversarial clear/scan/sleep interleavings, request/scan ratios, p99 round trip, network progress and quit under load; don't accept the timer rescuing missed signals |
| Upstream dependency | None outside Madeira native Wine overlay; do not parallelize server handlers |

### 4. G2 — budget shader compiler workers

| Field | Recommendation |
|---|---|
| Subsystem | DXMT / scheduling |
| Finding and evidence | H: task scheduler can grow to 2×hardware concurrency, competing with game/FEX/encode/audio work; first-use callers still wait for pipelines |
| Code location | `task_scheduler` constructor/worker/submit, [dxmt/src/dxmt/dxmt_tasks.hpp:48–79](https://github.com/willfaust/dxmt/blob/db546ee466ad50ec6463edb5fa183de11db43761/src/dxmt/dxmt_tasks.hpp#L48-L79), [dxmt/src/dxmt/dxmt_tasks.hpp:131–146](https://github.com/willfaust/dxmt/blob/db546ee466ad50ec6463edb5fa183de11db43761/src/dxmt/dxmt_tasks.hpp#L131-L146); `GetPipeline`, [dxmt/src/d3d11/d3d11_pipeline.cpp:49–56](https://github.com/willfaust/dxmt/blob/db546ee466ad50ec6463edb5fa183de11db43761/src/d3d11/d3d11_pipeline.cpp#L49-L56) |
| Proposed code change | Add a validated optional compiler-worker cap and active/queued/completion telemetry. Start A/B at caps 2 and 4 versus existing policy; retain existing default until measured. Preserve continuation scheduling and avoid forcing compiler/finish workers to highest QoS as a general policy |
| Why it helps | Can reduce oversubscription, priority competition and heat while allowing the render/encode critical path to run |
| Performance potential | Medium, conditional; fewer workers can also increase loading time |
| Implementation effort / compatibility risk | Medium / medium; starvation/dependency liveness and resource ownership must stay correct |
| Validation | Cold and warm p99 plus load time, compiler queue length, per-role CPU, input/audio and 15-minute thermals across two iPads |
| Upstream dependency | DXMT iOS fork; generic scheduler option could be offered upstream |

### 5. F2 — make JIT block-size tuning a bounded per-game experiment

| Field | Recommendation |
|---|---|
| Subsystem | FEX / Madeira configuration |
| Finding and evidence | H: default multiblock maximum 5,000 instructions can trade warm dispatch efficiency for cold compile latency; no optimal iPad value has been measured here |
| Code location | FEX defaults [FEX/FEXCore/Source/Interface/Config/Config.json.in:1–18](https://github.com/willfaust/FEX/blob/3bec2ac498bf78156ab47c0c194b0e8cb2849756/FEXCore/Source/Interface/Config/Config.json.in#L1-L18); generation/pass call [FEX/FEXCore/Source/Interface/Core/Core.cpp:1174–1243](https://github.com/willfaust/FEX/blob/3bec2ac498bf78156ab47c0c194b0e8cb2849756/FEXCore/Source/Interface/Core/Core.cpp#L1174-L1243); app config export in `WineProcessBridge.m` around 1140 |
| Proposed code change | Add a diagnostic per-game choice to Madeira's existing config/profile flow, validating {500,1000,5000} and exporting `FEX_MAXINST` before translator initialization. Log the effective value; require fresh app launch. Reuse raw `env.FEX_MAXINST` first; no FEX implementation change is needed for the experiment |
| Why it helps | If cold compilation causes frame spikes, smaller regions may reduce pause size; a warmed region may instead lose efficiency, so promote only demonstrated per-game settings |
| Performance potential | Medium for compilation stutter, unknown or negative for warm throughput |
| Implementation effort / compatibility risk | Low for controlled config / medium because Mono/invalidation behaviors depend on translation shape |
| Validation | Exact instruction/FP/exception tests and representative Mono games; compile-duration distribution, emitted bytes, dispatch misses, cold/warm frame tails |
| Upstream dependency | Madeira-only experiment; adaptive block formation would require FEX development and its contribution policy |

These are five **investigation-backed next actions**, not five proven speedups. X1/G1 are the most immediately actionable; W1 needs a synchronization protocol test; G2/F2 are explicit experiments.

## Remaining prioritized candidates

Every row specifies location/evidence, implementation, benefit, effort/risk, validation and owner. Relative order within this table is provisional until the first device capture.

| Rank / ID / subsystem | Finding and code evidence | Proposed change / expected mechanism | Potential | Effort | Risk | Validation | Owner / upstream dependency |
|---|---|---|---|---|---|---|---|
| 6 W3 Wine | H: fastsync spin/park/fallback and narrower coverage, `wine/dlls/ntdll/unix/sync.c:1715–1835,3406–3465` | Count local successes/spins/fallbacks by wait type, then tune per-game bounded policy; fewer wasted spins/RPCs | Medium in job systems | Low–medium | Medium | Sync matrix, timer/APC/close races, CPU/latency | Madeira config; Wine fork for policy |
| 7 X2 Cross | H: app Debug C -O0 / Swift -Onone, `app/Madeira.xcodeproj/project.pbxproj:826–848`; BUILDING warns Release crashes | Symbolized selective optimization configuration; bisect app-source groups rather than changing runtime flags | Medium for UI/bridge-heavy scenes | Medium | Medium | Full guest matrix, symbols, crash comparison | Madeira |
| 8 F1 FEX | C diagnostic global updates on C++ miss path, `Core.cpp:1920–1965` | Opt-in diagnostic counters, per-thread aggregation; retain all correctness guards | Medium if fallback-heavy | Medium | Medium | Equal guest code/config, fewer atomics/CPU, SEH tests | FEX fork; respect no-AI-code rule |
| 9 W2 Wine | H recurring scans, `build/wineserver/fd_ios.c:1476–1585` | Active/type-specific FD lists after W1; keep generation/FD identity checks | Medium for many idle descriptors | Medium | Medium | >64 INET FDs, close/reuse, Steam/network and idle power | Madeira |
| 10 G7 Graphics | H cache pruning in write path, `madeira_ir_unix.mm:1293–1309` | Idle bounded eviction with crash-safe budget accounting | Low–medium | Medium | Low–medium | Disk-full/restart/cap and frame IO | Madeira D3D12 |
| 11 G4 DXMT | C waits/full-preservation copies, avoidability H, `d3d11_context_imm.cpp:240–307` | Early legal submission / skip copies only on proven complete overwrite; retire by GPU sequence | Medium in streaming/readback | Medium | Medium–high | Bytes/frame, query/Map correctness, peak spares | DXMT fork/upstream |
| 12 X3 Cross | H repeated fault/alias round trips, `build/ntdll-unix/signal_arm64_ios.c:308–460,2187` onward | Cause census then fix stable loader/import target at owner with module-generation checks | High if fault-bound | High | High | Faults by cause, handler CPU, SEH/reload/SMC | Madeira + Wine/FEX |
| 13 G3 DXMT | H residual PSO stalls; `d3d11_pipeline.cpp:49–56`, bridge archive calls `winemetal_unix.c:5416–5447` | Wire versioned durable pipeline archive if PSO cost remains after G1 | Medium | High | Medium | Separate shader/library/PSO cache levels, stale fallback | DXMT |
| 14 G5 D3D12 | C global prebuild barrier, `madeira_d3d12.c:2634–2709`; async submit off at 5372–5384 | Per-PSO job completion replacing cross-queue batch barrier; separately validate existing async-submit | High for first-use stalls | High | High | PSO/list/allocator lifetimes, multiple queues, first-use tails | Madeira D3D12; no external upstream required |
| 15 F3 FEX | H duplicate frontend/publication contention, `Core.cpp:1210–1243`, `JIT.cpp:1240–1385` | Measure then sharded in-flight compile ownership with recursive-delivery bypass | Medium | High | High | Cold multiworker, SMC, SEH, invalidation/cancellation | FEX development |
| 16 F4 FEX | H rollover/cache footprint, `CPUBackend.cpp:508–552,625–672`, `LookupCache.cpp:33–158` | Device-budgeted buffers/L2 policy only after measuring dirty footprint and churn | Medium | Medium | High | Long sessions, alias lifetime, memory pressure | FEX + Madeira allocator |
| 17 W6 Cross | H priority competition, `WineServerBridge.m:160–173`, `thread_ios.c:2970–3036`, `dxmt_tasks.hpp:48–79` | Role QoS/worker experiments, no presumed P-core affinity | Medium | Medium | Medium | Runnable delay, audio/UI latency, thermals | Madeira + DXMT |
| 18 X4 Cross | H shared memory-budget pressure, `virtual_ios.c:2307–2697`, `d3d11_context_imm.cpp:248–259` | Coordinate JIT/staging/swap budgets from measurements, not maximum capacities | Medium | High | High | Footprint/page-ins, jetsam and correctness under churn | Madeira + FEX/DXMT |
| 19 W4 Wine | H madsync global contention, `build/madsync/madsync.c:66–125` | Per-object locks only with atomic wait-all and teardown protocol | High for proven contention | High | High | Linearizability, wait-all, abandonment/termination | Madeira sync engine / Wine collaboration |
| 20 W5 Wine | C child boot serialization, `loader_ios.c:3420–3506` | Move mutable startup state into pseudo-process context before narrowing lock | Medium at multi-process launch | High | High | Concurrent mixed-bitness children, cwd/env and exits | Madeira + Wine |
| 21 G6 Graphics | H allocation/conversion cost, `winemetal_unix.c:691–810,6590–6646`, `dxmt_bcn.cpp` | Targeted reusable heaps or format strategies after bandwidth/lifetime profiling | Medium | High | High | Alignment, x86 reachability, alias barriers, formats | DXMT / D3D12 |
| 22 F5 FEX/Cross | H transition cost, `BranchOps.cpp:46–104`, `CPUFeatures.cpp:117–164` | Target measured hot boundary with native ABI-safe batching/thunk; use X3 if cost is faults | High if transition-bound | High | High | Call/FP/SEH/GC and module lifetime tests | FEX + Wine/Madeira |
| 23 F6 FEX | H launch compile cost, `CodeCache.cpp:558–640,640–892` | Relocatable validated data cache or block hot-set prewarm using authorized JIT pool | Medium at startup | High | High | ASLR, helper relocation, settings/code changes, cross-core flush | FEX + Madeira |

FEX paths abbreviated above are under `FEX/FEXCore/Source/Interface/Core/`, except `CPUFeatures.cpp` in `FEX/Source/Windows/Common/`. DXMT paths are under `dxmt/src/d3d11/`, `dxmt/src/dxmt/`, or `dxmt/src/winemetal/unix/` as named in [dxmt.md](dxmt.md). `madeira_d3d12.c` is `madeira-d3d12/src/pe/madeira_d3d12.c`; `madeira_ir_unix.mm` is in its `src/unix/` directory. File/function traces in subsystem reports disambiguate each location.

## Quick wins within Madeira itself

1. X1 diagnostic launch gates, then baseline captures with no hidden samplers.
2. G1 existing cache-directory switch through the app before changing the fork default; keep a rollback and prove persistence.
3. Correlated low-overhead counters and raw frame export at native Wine/Metal boundaries; fix diagnostic counter races rather than building conclusions from them.
4. W1 wake coalescing in the native overlay with focused adversarial tests.
5. F2 and W3 bounded configuration experiments, restarting the app for each setting.
6. X2 selective app optimization only after isolating the documented Release failure.

G2 needs a DXMT fork rebuild. F1/F3/F6 need FEX work rather than only app configuration. Large process-context isolation, madsync sharding, persistent JIT caches and PSO graph redesign are later projects.

## Existing improvements to retain, not reimplement

- ARM64EC native Wine, concurrent guest pthreads, native D3D9 frontend.
- FEX L1-first dispatch, shared compiled code, per-thread frontend emission, LRCPC2 probing and default AFP-off.
- Fast synchronization engines, server request wake semaphore and fixed timer-overflow behavior.
- Async DXMT encoding/completion retirement; D3D9 batching/upload settle points; iOS cached CPU mappings and present ordering fixes.
- D3D12 persistent shader conversion cache, lazy PSOs and a persistent parallel first-use pool.

Do not land blanket TSO disablement, missing cache flushes, lock removal without lifetime proof, frame-generation-as-FPS claims, universal highest-priority workers, `fence-chain=0`, or reuse of GPU-live memory.

## Recommended next-phase sequence

**Phase 0 — reproducible baseline.** Build the pinned source on a Mac, verify the installed binary manifest and JIT, attach a physical M-series iPad, run the benchmark protocol. Resolve missing toolchains before attributing binary behavior to source.

**Phase 1 — remove contamination / recover caches.** Separate commits for X1 and G1, one toggle at a time. Capture quiet versus sampled and cold versus disk-warm runs. The exit criterion is verified removal of work/cache misses with no compatibility regression.

**Phase 2 — server and scheduling.** Land W1 only after lost-wakeup/timer/network tests and request-latency improvement. Experiment with G2 caps and W3 engines, including sustained thermal runs. Do not combine them into one unexplained FPS result.

**Phase 3 — translator experiments.** Run F2 against fixed correctness tests and cold/warm games. If compile/publication data implicates FEX, prepare a maintainer-compatible F1/F3 proposal; do not generate prohibited FEX code contributions.

**Phase 4 — measured architectural work.** Pick exactly the demonstrated bottleneck: G3 PSO archive, G5 PSO graph/async submit, X3 alias faults, or W4/W5 process/sync redesign. Each has independent correctness and rollback gates. Persistent JIT caching follows a proven relocation/publication design, not a cache-file toggle.

The handoff acceptance criterion is a mechanism-backed, repeated improvement on physical iPadOS—not a successful Linux host model or a plausible static optimization.
