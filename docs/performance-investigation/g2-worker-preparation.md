# G2 compiler-worker experiment and shutdown prerequisite

Tracks [issue #6](https://github.com/brookesdjb/Madeira/issues/6).

Two unapplied patch assets under `build/dxmt-ios/experiments/` are prepared for
DXMT pin `db546ee466ad50ec6463edb5fa183de11db43761`:

- `scheduler-shutdown.patch`: publishes `destroyed` while holding the workers'
  condition-variable mutex, before notification. This is a correctness
  prerequisite, not a performance variable.
- `compiler-worker-cap.patch`: adds an optional `DXMT_COMPILER_THREADS=2` or `4`
  cap, preserving the current detected-CPU policy for unset/invalid values.
  The cap cannot raise a working existing limit. An explicit cap with zero CPU
  detection retains the two workers the constructor already launches.

Neither patch is applied to a live submodule, a build script or an app. No
native archive, PE DLL, submodule pin, thread-priority policy or telemetry
contract is changed. The cap will have no effect on an installed app until the
DXMT integration is deliberately built with it.

## Host findings

```sh
python3 tests/host/check-compiler-cap.py --dxmt-root ../Madeira-performance/dxmt
```

The test applies both patches only inside a disposable tree and compiles the
production scheduler with host pthread/C++ adapters and stub Win32 priority
calls. ASan/UBSan checks pass for 18 combinations of CPU count 0/1/8 and cap
unset/2/4/invalid. It forces worker growth to its bound, verifies a parked
dependency resumes, handles already-completed dependencies, and joins idle
workers during shutdown. It does not run real shader compilation or Wine thread
creation.

The patched scheduler also compiled through explicit template instantiation with
the actual DXMT headers and LLVM-MinGW adapters for x64, ARM64EC and x86. All
three object compilations passed. Private commands, logs and object hashes are
under `diagnostics/performance-g2-2026-10-10/` beside the worktrees. This is
compile-only validation, not a linked DXMT DLL/archive or native runtime test.

An initial scheduler run hung at idle shutdown. The existing destructor changes
the wait predicate and notifies without holding the waiter's mutex. A forced
predicate-to-wait gap reproduces that lost notification in the original
destructor (bounded negative-control timeout), while the mutex-protected patch
completes. The candidate cap is tested only with this prerequisite. It does not
claim that every baseline hang came from worker-count policy.

## Integration and device gate

Review/land the shutdown fix as a separate DXMT correctness change through the
user fork's agreed integration route. Apply it to **both** benchmark arms. Then
integrate the optional cap in a separate change and rebuild native/PE components
as required by the actual dependency path. Do not casually edit a shared DXMT
checkout or publish to an original upstream repository.

Before device conclusions, agree active/queued/completed telemetry with #2/#14;
this patch creates no competing sampler. Verify shader task dependencies,
cancellation/resource lifetime and shutdown with real Wine threads. Compare
current policy against caps 2 and 4 with fresh processes, cold/warm loading,
raw frame tails, per-role CPU, input/audio correctness and 15-minute thermals.
Use two iPads when available, recording unavailable coverage explicitly.

Unset `DXMT_COMPILER_THREADS` preserves the old worker policy. Do not promote a
cap or change QoS without measured benefit. The shutdown fix should remain
identical in all comparison arms. Native integration and physical acceptance
are still open; these patch assets are host-validated preparation only.
