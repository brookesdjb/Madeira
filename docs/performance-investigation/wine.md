# Wine threading, synchronization and process emulation

This is the pinned Wine fork **plus** Madeira's native source replacements; see [architecture](architecture.md). C/S/H describe source certainty, not measured FPS impact.

## Process/thread architecture map

| Operation | Trace | Host representation and shared cost |
|---|---|---|
| Initial guest launch | `WineProcessBridge.m::wine_process_thread → __wine_main` | Dedicated pthread, native Unix loader, Wine PEB/TEB and translator initialization |
| CreateProcess | `process_ios.c::NtCreateUserProcess → spawn_process → ios_child_thread_entry → loader_ios.c::wine_ios_child_main` | Another pthread in the same Darwin task, socket descriptors duplicated because there is no fork |
| CreateThread | `thread_ios.c::NtCreateThreadEx → pthread_create(start_thread) → server_init_thread → signal_start_thread` | Independent kernel-scheduled pthread, owned TEB key, per-thread syscall/CPU state |
| Native/x64 boundary | ARM64EC dispatchers and FEX CPU area | Native Wine can execute between translated guest regions on the same pthread |
| x86 child | WoW64 window, native aarch64 support, FEX `xtajit.dll` | Separate guest address namespace represented by a shifted host window |
| Server | `WineServerBridge.m::wineserver_start → wineserver_thread_func → wineserver_main` | One native server pthread with serialized object/request dispatch |
| GPU submission | DXMT encoding and finish threads; optional D3D12 submit workers | Additional native execution competing with guest workers; some PE-created workers still incur Wine/FEX thread initialization |

References: [build/ntdll-unix/process_ios.c:418–646](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/process_ios.c#L418-L646), [build/ntdll-unix/thread_ios.c:1270–1305](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/thread_ios.c#L1270-L1305), [build/ntdll-unix/thread_ios.c:1549–1743](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/thread_ios.c#L1549-L1743), [app/Madeira/WineServerBridge.m:160–183](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/app/Madeira/WineServerBridge.m#L160-L183). These establish real concurrency. The child-slot list's 32 entries track session lifetime; it should not be interpreted as the hardware thread count or a universal guest-thread limit.

The upstream comparison is concrete: `wine-11.4:dlls/ntdll/unix/process.c:403–449` uses fork/exec, while Madeira uses pthread creation. Upstream per-process Unix globals cannot be assumed isolated after that substitution.

## Process isolation and serialized initialization

A process's PEB, TEBs, guest mappings, handles and PE loader identity are represented in Wine. Host native globals, file descriptors and Mach resources are shared. `ios_child_thread_entry` still calls `fchdir` and `spawn_process` can `putenv`; those operations affect host-global state. Treat any attempt to make bootstrap more parallel as a correctness project first.

`loader_ios.c` documents and implements `ios_child_boot_mutex`, with TLS ownership and destructor/unlock cleanup: [build/ntdll-unix/loader_ios.c:3420–3506](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/loader_ios.c#L3420-L3506). It serializes child bring-up because startup globals were written assuming an OS process. It is not a lock around every guest instruction. Removing it may shorten multi-process launch but risks cross-child loader/environment corruption. **W5** proposes explicit per-pseudo-process native context first, then narrowing its scope.

The owned TEB key replaced use of a foreign raw pthread TSD slot; the source specifically records failures observed on an M4 iPad: [build/ntdll-unix/thread_ios.c:1277–1305](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/thread_ios.c#L1277-L1305). This is exactly the kind of port-specific invariant an optimization must retain. The PE `RtlWaitOnAddress` queue table is deliberately shared across ntdll copies (`wine/dlls/ntdll/sync.c:1264–1319`); making it per-copy again can strand waiters.

## Standard wineserver round trip

`wine_server_call` masks server signals, `server_call_unlocked` sends the request, wakes wineserver and waits for a reply, then restores the signal mask: [build/ntdll-unix/server_ios.c:1841–1877](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L1841-L1877). Request handling is not a direct synchronous call despite sharing an address space. The protocol retains pipe/socket transfer and scheduling costs.

The iOS event loop treats AF_UNIX readiness differently from ordinary Wine. Its source documents a sandbox readiness limitation and uses synthetic nonblocking client readiness plus real zero-timeout polling for INET descriptors. This limitation was **not independently reproduced on an iPad here**. Do not replace the workaround with desktop `poll` merely because desktop Wine does so.

Every client request calls `semaphore_signal` in `ios_wineserver_wake`: [build/wineserver/fd_ios.c:34–47](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/wineserver/fd_ios.c#L34-L47). The loop consumes a semaphore token per pass and scans descriptors; its own comment documents accumulation when signals arrive faster than loop iterations: [build/wineserver/fd_ios.c:1390–1468](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/wineserver/fd_ios.c#L1390-L1468). INET descriptors are already batched without the earlier first-64 cap: [build/wineserver/fd_ios.c:1476–1535](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/wineserver/fd_ios.c#L1476-L1535). Two loop scans still scale with registered descriptor slots. `MADEIRA_SRV_NOSEM` is a diagnostic comparison, not a recommended fix: sleeping through real requests increases latency.

**W1 (S): coalesce wakes with a race-safe pending protocol.** Use an atomic pending flag/sequence published only after the request bytes are visible. Signal on transition to pending; clear pending before draining/scanning; a request arriving during/after the scan must either be observed or leave a wake for the next pass. Keep an explicit stop wake and the timer/INET tick. Test the clear/scan/sleep interleavings, EINTR and descriptor reuse. A plain “if not sleeping, skip signal” is unsafe without a proven handshake. Do not replace wineserver's serialized object operations with arbitrary concurrent handler calls.

## Three synchronization engines, different coverage

### Fastsync: current app default

`madeira_cfg_sync_engine()` chooses fastsync when no override is supplied; the app exports `MADEIRA_FASTSYNC=auto`. [build/madeira_cfg.h:213–224](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/madeira_cfg.h#L213-L224), [app/Madeira/WineProcessBridge.m:1215–1230](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/app/Madeira/WineProcessBridge.m#L1215-L1230). The Wine implementation alone defaults off when its environment is unset; that does not contradict the app default.

`wine/dlls/ntdll/unix/sync.c:1043–1924` and `wine/include/wine/madeira_fastsync.h` implement a shared cell protocol and handle-to-cell cache. Cache identity includes process ownership and generation, close invalidates it, and new pseudo-processes flush reused PID entries (`server_ios.c:4429` onward). Generation/state are checked together to avoid consuming a token from a recycled object.

Coverage is deliberately limited: eligible events and optional semaphore operations, read-only zero-timeout peeks, bounded spin/ulock park, then server fallback. Non-alertable single-handle WaitAny is the important fast-wait shape; complex multiwait, alertable/APC semantics, mutexes and unsupported cases retain server handling. [wine/dlls/ntdll/unix/sync.c:3406–3465](https://github.com/willfaust/wine/blob/257f271cfffed9f22f7987cac53bc00095d092fe/dlls/ntdll/unix/sync.c#L3406-L3465). Semaphore fast waits are experimental and require `MADEIRA_FASTSYNC_SEM`; don't enable them universally based on an event benchmark.

The local wait initially tries atomics, spins (`isb` loop), can adapt its spin budget, registers a waiter, rechecks state/generation and parks via Darwin `__ulock_wait`. [wine/dlls/ntdll/unix/sync.c:150–200](https://github.com/willfaust/wine/blob/257f271cfffed9f22f7987cac53bc00095d092fe/dlls/ntdll/unix/sync.c#L150-L200), [wine/dlls/ntdll/unix/sync.c:1715–1835](https://github.com/willfaust/wine/blob/257f271cfffed9f22f7987cac53bc00095d092fe/dlls/ntdll/unix/sync.c#L1715-L1835). Fallback relative deadlines account for prior waiting. “Remove all barriers/spins” is not a correctness-preserving patch. **W3** measures spin successes, fallback rate and kernel wake latency across engine/config choices before tuning defaults.

### Madsync: optional

`build/madsync/madsync.c` implements ntsync-like events, recursive/abandonable mutexes, semaphores, wait-any/all and alert handling in shared userspace. One global mutex protects object state and makes multi-object transitions atomic; blocked waiters use Mach semaphores. Signal masking prevents thread termination while owning the lock; destruction has explicit cleanup. [build/madsync/madsync.c:1–125](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/madsync/madsync.c#L1-L125). The header comment mentioning stack condition variables is stale relative to the implementation's semaphore and waiter lifetime handling.

Its global lock has bounded spin before kernel blocking, configurable with `madsync-lock-spin`. Under high contention this serializes otherwise independent objects. However it can also eliminate many more server round trips than fastsync for some workloads. Splitting locks requires a wait-all acquisition/rollback protocol, object lifetime and abandonment semantics; do not “shard by handle” without solving these. **W4** is a larger, profiling-gated project.

### Standard Wine and address waits

Standard Wine remains the compatibility baseline. Critical sections/SRW locks often complete without server interaction; `RtlWaitOnAddress` uses hashed queues and the thread-alert machinery for contention. Darwin ulocks are available in this port; it is inaccurate to claim that every wait is a wineserver RPC or that Linux futex/ntsync is directly available on iPadOS. DXMT PE workers use the port's address-wait wrapper, while native Darwin DXMT uses libc++ atomic wait/notify.

## Thread pools, timers, wakeups and QoS

`wine/dlls/ntdll/threadpool.c` is unchanged versus fetched upstream Wine 11.4. Its locks, minimum/maximum worker counts, timer/wait/completion machinery remain relevant, but timer behavior also depends on the replaced server loop. The timeout-overflow fix discussed in PR #184 is already present in the superproject history; do not recommend implementing it again. Inspect request mixes for repeated timer programming before changing worker counts.

The server explicitly starts at `QOS_CLASS_USER_INTERACTIVE`; the initial guest thread also requests it. Worker start paths and Eco mode affect further threads. Thread-affinity APIs can record guest masks via wineserver, but that does not prove Darwin pins a thread to a named P-core. Inspect `thread_ios.c:2970–3036` and the effective thread policy. **W6** proposes role-aware QoS experiments using actual native thread policy and per-thread CPU accounting. Raising all workers is not a free gain: it can starve UI/audio, exacerbate shader contention and increase heat.

## Confirmed diagnostic overhead: X1

The app sets `MADEIRA_QUIET=1` (`WineProcessBridge.m:961`), yet `server_init_process_done` arms three task-wide jobs **before** checking quiet: [build/ntdll-unix/server_ios.c:4571–4587](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L4571-L4587). `ios_thread_sampler_main` periodically suspends threads; `ios_xprobe_main` samples task/thread usage every 250 ms; `ios_wprof_main` performs repeated stack sampling of role-marked threads. [build/ntdll-unix/server_ios.c:1488–1508](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L1488-L1508), [build/ntdll-unix/server_ios.c:1697–1789](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/build/ntdll-unix/server_ios.c#L1697-L1789). Only the older 500 Hz profiler below the quiet check is disabled by that check.

Gate these diagnostic jobs behind explicit, separately selectable settings, default off for normal gameplay. Keep fault recovery, termination/deadlock protection and user-selected lightweight CPU/GPU overlay operational. This is a low-effort Madeira-only change with a clear mechanism; the degree of p99/thermal improvement needs hardware measurement.

## Backlog and validation

| ID | Finding / evidence | Change | Potential / effort / risk | Validation and owner |
|---|---|---|---|---|
| X1 | C: profiling runs despite quiet | Explicit runtime/build gates around diagnostic job launch; no gate around recovery | Medium / low / low | Prove no sampler suspends with gate off; same gameplay/correctness, A/B p99/energy; Madeira |
| W1 | S: one wake token per request, recurring full scans | Race-safe coalescing retaining timers/network tick | Medium / medium / medium | Burst/idle lost-wake tests, request p50/p99, scans/request, CPU and quit; Madeira |
| W2 | H: O(registered slots) scans | Maintain active ready/index sets or type-specific descriptor lists; retain reuse identity checks | Medium / medium / medium | Hundreds of INET/client FDs, close/reuse storms and idle power; Madeira |
| W3 | H: synchronization policy workload-dependent | Instrument event/sem/multiwait mix and spin success; bounded per-game configuration | Medium / low–medium / medium | Event ping-pong, job fanout, timeout/APC/close stress; Madeira + Wine fork |
| W4 | H: madsync global lock | Ordered per-object locks with explicit wait-all protocol only after contention proof | High on contended madsync workloads / high / high | Linearizability, abandonment, termination, mixed waits; Wine/Madeira sync engine |
| W5 | C serialization, H performance relevance: child boot mutex | Explicit per-process native context, then narrow bootstrap lock | Medium at launch / high / high | Concurrent mixed-bitness launch/reload/exit, cwd/environment isolation; Madeira + Wine |
| W6 | H: thread oversubscription/priority competition | Role-based QoS and bounded worker experiments, no assumed core affinity | Medium / medium / medium | Warm sustained runs, audio glitches, input latency, thermal state; Madeira + DXMT |

Existing fastsync cell/semaphore tests passed on Linux. They exercise protocol models/extracted code; they do not establish Darwin ulock performance, full Wine correctness or safe multiwait lock sharding. Detailed commands/results and required iPad workloads are in [benchmark-plan](benchmark-plan.md).
