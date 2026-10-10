# Cross-subsystem costs and architectural limits

See [architecture](architecture.md) for pins and [recommendations](recommendations.md) for complete candidate fields. These are interacting critical paths, not additive estimates of speedup.

## Where independent work becomes serialized

| Boundary | Actual mechanism | How to distinguish / candidate |
|---|---|---|
| Guest → ARM64EC native | FEX spill/fill, ABI state and FP mode; existing AFP-off policy reduces one cost | Sample both sides, count transition targets; F5, not “translate Wine faster” |
| Guest code fault → recovery | One native Mach exception service, alias lookup/emulation/invalidation | Count fault causes and handler CPU; high rate can serialize unrelated guest threads; X3 |
| Concurrent compilation → executable code | Per-thread temporary emission then shared code-buffer publication | Measure lock wait vs copy/flush/relocation; F3 |
| Wine client → server | Request pipe/socket, signal-mask changes, counting semaphore wake, serial dispatch | Round-trip latency, server service time and scan count are separate; W1/W2 |
| Native/PE graphics workers → synchronization | PE RtlWaitOnAddress vs native atomic waits; first-use PSO wait | Correlate wait addresses with pipeline jobs and encode sequence; G2/G5 |
| App launch → shader cache | 64-bit relative cache path skips iOS resolver | Inspect actual resolved path and hits; G1 |
| CPU Map → GPU | Required dependency flush/readback, bounded renaming | Distinguish queued/unsubmitted work and GPU execution; G4 |
| D3D12 queues → shared prebuild pool | Global serial PSO prebuild lock and completion wait | Record queue ID, list ID, PSO ID and ready times; G5 |
| Diagnostics → whole app | Thread suspension, stack walking, logging/UI formatting | First remove measurement contamination; X1 |
| Allocation → memory pressure | Guest memory, JIT aliases/code, per-thread caches, rings, shader blobs share one budget | Track footprint and stalled page-ins with frame spikes; F4/G6/X4 |

## Native transitions and fault recovery

Do not optimize away ARM64EC save/restore state merely because native Wine and FEX share a pthread. x86 flags, guest callee-save state, FP semantics and exception unwinding require the boundary. Existing extended-volatile metadata and direct native D3D9 paths already reduce particular costs; broad new thunking needs a measured hot API plus a complete ABI contract.

The Mach handler can redirect PE execution aliases and emulate accesses into protected/aliased pages (`build/ntdll-unix/signal_arm64_ios.c:308–460,2187` onward). Executable-memory writes are tracked separately from ordinary shared buffers. **X3** proposes cause-tagged exception histograms first, then fixing only repeated stable target resolution in the loader/IAT owner. Never patch a transient alias without module generation/lifetime checks, and do not mask a real protection fault. Required regression coverage includes reload, SEH/APCs, copy-on-write, JIT-generated guest code and simultaneous native calls.

## Shared memory does not mean no copies

A guest pointer may be an x86 window offset, an x64 VA, or an executable alias. winemetal must convert and validate it. Resource renaming intentionally preserves bytes the application did not overwrite. CPU/GPU completion establishes reuse eligibility even on unified memory. File-backed guest memory trades footprint pressure against fault and IO cost; it is not “free RAM.” `docs/madeira.cfg.example` describes coverage modes and soft caps, not a universal performance setting.

**X4** is a per-device budget experiment across JIT/code caches, texture/staging spares and file-backed memory. Avoid independently maximizing each cache. Record allocation lifetime/bytes and peak physical footprint rather than adding virtual reservations. Jetsam, long pauses and silent stale aliases are rejection criteria.

## Scheduling and thermal interactions

Guest workers, wineserver, Metal encode/finish threads, shader compiler jobs, Mach handling, audio and Swift UI share the scheduler. Low GPU busy time can result from PSO waits, server handoffs or render-thread translation, while high CPU usage can include diagnostic work. Aggressively increasing workers/QoS may improve the first minute and regress sustained play. A many-core M-series iPad can support more parallel guest execution, but does not remove serial request handling, code publication, immediate-context ordering or global pipeline prebuild barriers.

The Debug app has unoptimized Swift/C app code while native runtime archives are separately optimized. **X2**: introduce a profiling configuration with symbols and selectively optimized app source groups, preserving working runtime flags. Bisect historical Release failures before deployment. This is not a recommendation to strip validation, omit checks or build everything with unsafe math.

## Instrumentation contract

A correlated event carries monotonic timestamp, native TID, Wine PID/TID, subsystem, event kind, correlation/sequence ID and duration. Frame/command-buffer IDs connect CPU recording to encode, commit, GPU completion and Present. Use per-thread bounded buffers and disabled-by-default gates; never allocate or acquire a global logging lock in a fault/signal handler. Handler counters must use preallocated storage and safe atomic updates; flush them from a normal thread.

Separate **CPU execution time**, **wall time blocked**, **runnable scheduling delay** and **GPU interval time**. Do not sum overlapping wall times into a frame budget or treat diagnostic samples as exact retired instructions. Keep an unsampled reference run and report instrumentation overhead.

Architectural improvements are justified only after these traces show the critical path. Shared host process isolation, x86 memory ordering and iPad JIT authorization are constraints that optimizing an individual graphics function cannot eliminate.
