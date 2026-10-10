// Mac-only harness: production FEX pool header; host allocation adapters below.
#include <FEXCore/Utils/ThreadPoolAllocator.h>
#include <algorithm>
#include <barrier>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>

static void require(bool ok, const char *why) {
  if (!ok) throw std::runtime_error(why);
}
constexpr size_t MiB = 1024 * 1024;
constexpr size_t Scratch = 16 * MiB;

// This deliberately models a bounded contiguous arena. It does NOT implement
// Wine's VA scanner, rpmalloc, iPad JIT mappings or physical-memory pressure.
class Arena {
  char *base;
  size_t capacity;
  std::map<size_t, size_t> gaps;
  std::map<void *, size_t> live;
  std::mutex mutex;
public:
  size_t calls = 0, failures = 0, used = 0, peak = 0;
  explicit Arena(size_t size): capacity(size) {
    base = static_cast<char *>(::mmap(nullptr, size, PROT_NONE,
                                   MAP_PRIVATE | MAP_ANON, -1, 0));
    require(base != MAP_FAILED, "host arena reservation failed");
    gaps.emplace(0, size);
  }
  ~Arena() { ::munmap(base, capacity); }
  void *allocate(size_t size) {
    std::lock_guard lock(mutex);
    ++calls;
    require(size && size % static_cast<size_t>(getpagesize()) == 0, "unaligned request");
    for (auto it = gaps.begin(); it != gaps.end(); ++it) {
      if (it->second < size) continue;
      size_t offset = it->first, rest = it->second - size;
      void *p = base + offset;
      require(::mprotect(p, size, PROT_READ | PROT_WRITE) == 0, "host mprotect failed");
      gaps.erase(it);
      if (rest) gaps.emplace(offset + size, rest);
      live.emplace(p, size);
      used += size; peak = std::max(peak, used);
      return p;
    }
    ++failures;
    return nullptr; // Windows VirtualAlloc failure contract used by device path.
  }
  void release(void *p, size_t size) {
    if (!p) return;
    std::lock_guard lock(mutex);
    auto found = live.find(p);
    require(found != live.end() && found->second == size, "invalid free");
    live.erase(found); used -= size;
    require(::mprotect(p, size, PROT_NONE) == 0, "host release protection failed");
    ::madvise(p, size, MADV_DONTNEED);
    size_t offset = static_cast<char *>(p) - base;
    auto next = gaps.lower_bound(offset);
    if (next != gaps.begin()) {
      auto prev = std::prev(next);
      if (prev->first + prev->second == offset) {
        offset = prev->first; size += prev->second; gaps.erase(prev);
      }
    }
    next = gaps.lower_bound(offset);
    if (next != gaps.end() && offset + size == next->first) {
      size += next->second; gaps.erase(next);
    }
    gaps.emplace(offset, size);
  }
};
static Arena *arena;

// Only allocation/logging boundaries are supplied by the host harness.
namespace FEXCore::Allocator {
void *malloc(size_t n) { return std::malloc(n); }
void free(void *p) { std::free(p); }
void *aligned_alloc(size_t alignment, size_t n) {
  void *p = nullptr;
  if (::posix_memalign(&p, std::max(alignment, sizeof(void *)), n)) return nullptr;
  return p;
}
void aligned_free(void *p) { std::free(p); }
MMAP_Hook mmap = +[](void *, size_t n, int, int, int, off_t) { return arena->allocate(n); };
MUNMAP_Hook munmap = +[](void *p, size_t n) { arena->release(p, n); return 0; };
void VirtualName(const char *, void *, size_t) {}
}
namespace fextl {
[[noreturn]] void ReportAllocationFailure(size_t, size_t) { std::abort(); }
}
namespace LogMan::Throw {
[[noreturn]] void MFmt(const char *format, const fmt::format_args &args) {
  throw std::runtime_error(fmt::vformat(format, args));
}
}
namespace LogMan::Msg {
void MFmtImpl(DebugLevels, const char *format, const fmt::format_args &args) {
  std::fprintf(stderr, "%s\n", fmt::vformat(format, args).c_str());
}
}
#ifdef PRESSURE_EXPERIMENT
#include "pressure_pool.h"
using Pool = PressurePool;
constexpr bool pressure = true;
#else
using Pool = FEXCore::Utils::PooledAllocatorVirtual;
constexpr bool pressure = false;
#endif
using Base = FEXCore::Utils::IntrusivePooledAllocator;
struct Client {
  Base::BufferOwnedFlag flag{Base::ClientFlags::FLAG_FREE};
  Base::ContainerType::iterator buffer;
};
static void print(const char *name, const Arena &a, size_t nulls = 0,
                  double p95 = 0, size_t workers = 0) {
  std::printf("{\"case\":\"%s\",\"checks_passed\":true,\"allocation_calls\":%zu,"
              "\"allocation_failures\":%zu,\"null_claims\":%zu,\"peak_reserved_mib\":%zu,"
              "\"workers\":%zu,\"claim_p95_us\":%.3f}\n",
              name,a.calls,a.failures,nulls,a.peak/MiB,workers,p95);
}
static void exhaustion() {
  Arena a(8192 * MiB); arena = &a;
  size_t nulls = 0;
  {
    Pool pool;
    std::vector<std::unique_ptr<Client>> clients;
    for (size_t i=0; i<513; ++i) {
      auto c = std::make_unique<Client>();
      c->buffer = pool.ClaimBuffer(Scratch, &c->flag);
      void *p = (*c->buffer)->Ptr;
      require((p != nullptr) == (i < 512), "unexpected capacity boundary");
      if (!p) {
        ++nulls;
        require(Base::IsClientBufferOwned(c->flag), "failure behavior changed: review expected result");
        // Do not dereference it. Production currently records NULL as owned.
      } else {
        *static_cast<volatile uint64_t *>(p) = i;
        require(*static_cast<volatile uint64_t *>(p) == i, "write/read mismatch");
      }
      clients.push_back(std::move(c));
    }
    for (auto &c: clients) pool.UnclaimBuffer(c->buffer, &c->flag);
  }
  require(a.used == 0 && a.failures == (pressure ? 2 : 1) && nulls == 1, "exhaustion cleanup failed");
  print("8gib_exhaustion_known_null_claim", a, nulls);
}
static void reuse() {
  Arena a(8192 * MiB); arena = &a;
  {
    Pool pool; Client c;
    for (int i=0;i<1000;++i) {
      c.buffer = pool.ClaimBuffer(Scratch, &c.flag);
      require((*c.buffer)->Ptr != nullptr, "reuse returned null");
      pool.UnclaimBuffer(c.buffer, &c.flag);
    }
  }
  require(a.calls == 1 && a.used == 0, "pool failed to reuse allocation");
  print("1000_reclaims",a);
}
static void fragmentation() {
  Arena a(8192 * MiB); arena = &a;
  std::vector<void *> blocks;
  for (int i=0;i<1024;++i) blocks.push_back(a.allocate(8*MiB));
  for (int i=0;i<1024;i+=2) a.release(blocks[i],8*MiB);
  require(a.used == 4096*MiB, "fragmentation setup wrong");
  {
    Pool pool; Client c;
    c.buffer = pool.ClaimBuffer(Scratch,&c.flag);
    require((*c.buffer)->Ptr == nullptr, "fragmentation should reject contiguous request");
    pool.UnclaimBuffer(c.buffer,&c.flag);
  }
  for (int i=1;i<1024;i+=2) a.release(blocks[i],8*MiB);
  void *whole = a.allocate(8192*MiB);
  require(whole != nullptr, "coalescing failed"); a.release(whole,8192*MiB);
  require(a.used == 0 && a.failures == (pressure ? 2 : 1), "fragmentation cleanup failed");
  print("4gib_free_but_fragmented",a,1);
}
static void retirement() {
  Arena a(8192 * MiB); arena = &a;
  {
    Pool pool; Client first, second;
    first.buffer = pool.ClaimBuffer(Scratch, &first.flag);
    void *original = (*first.buffer)->Ptr;
    pool.DisownBuffer(first.buffer);
    // Controlled clock fixture: exercise production expiry without sleeping.
    (*first.buffer)->LastUsed.store(Base::ClockType::now()-std::chrono::seconds(6));
    second.buffer = pool.ClaimBuffer(Scratch, &second.flag);
    require(Base::IsClientBufferFree(first.flag), "expired owner not invalidated");
    require((*second.buffer)->Ptr == original, "expired buffer not reused");
    first.buffer = pool.ReownOrClaimBuffer(first.buffer, Scratch, &first.flag);
    require((*first.buffer)->Ptr != original, "reclaimed owner overlaps new owner");
    pool.UnclaimBuffer(first.buffer, &first.flag);
    pool.UnclaimBuffer(second.buffer, &second.flag);
  }
  require(a.calls == 2 && a.used == 0, "retirement cleanup failed");
  print("expired_disowned_buffer_reclaimed", a);
}
static void concurrency(size_t workers) {
  Arena a(8192 * MiB); arena = &a;
  std::vector<std::vector<double>> samples(workers);
  {
    Pool pool;
    std::barrier barrier(static_cast<ptrdiff_t>(workers));
    std::vector<std::thread> threads;
    for (size_t id=0;id<workers;++id) threads.emplace_back([&,id] {
      Client c;
      for (size_t i=0;i<100;++i) {
        barrier.arrive_and_wait();
        auto start=std::chrono::steady_clock::now();
        c.buffer=pool.ClaimBuffer(Scratch,&c.flag);
        samples[id].push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());
        auto *p=static_cast<volatile uint64_t *>((*c.buffer)->Ptr);
        require(p != nullptr,"concurrent allocation failed");
        p[0]=id+1; p[Scratch/8-1]=id+1;
        barrier.arrive_and_wait();
        require(p[0]==id+1 && p[Scratch/8-1]==id+1,"overlapping live allocation");
        pool.UnclaimBuffer(c.buffer,&c.flag);
      }
    });
    for(auto &t:threads)t.join();
  }
  require(a.used==0 && a.failures==0 && a.calls==workers,"concurrent pool leak or extra allocation");
  std::vector<double> all;
  for(auto &s:samples)all.insert(all.end(),s.begin(),s.end());
  std::sort(all.begin(),all.end());
  print("concurrent_claim_reuse",a,0,all[(all.size()-1)*95/100],workers);
}
// Fill the arena with active memory plus young idle buffers. Only the latter
// may be released. Future timestamps make the fixture independent of run time.
static void pressureRecovery(bool disowned, bool split) {
  Arena a(8192 * MiB); arena = &a;
  void *filler = a.allocate(8160 * MiB);
  {
    Pool pool; Client idle1, idle2, active, requester;
    size_t size = split ? 8 * MiB : Scratch;
    idle1.buffer = pool.ClaimBuffer(size, &idle1.flag);
    if (split) idle2.buffer = pool.ClaimBuffer(size, &idle2.flag);
    active.buffer = pool.ClaimBuffer(Scratch, &active.flag);
    auto *live = static_cast<volatile uint64_t *>((*active.buffer)->Ptr);
    live[0] = 0x1234; live[Scratch/8-1] = 0x5678;
    for (Client *c : {&idle1, split ? &idle2 : nullptr}) {
      if (!c) continue;
      if (disowned) pool.DisownBuffer(c->buffer);
      (*c->buffer)->LastUsed.store(Base::ClockType::now()+std::chrono::hours(1));
      if (!disowned) pool.UnclaimBuffer(c->buffer, &c->flag);
    }
    requester.buffer = pool.ClaimBuffer(Scratch, &requester.flag);
    require(((*requester.buffer)->Ptr != nullptr) == pressure, "pressure recovery mismatch");
    require(Base::IsClientBufferOwned(active.flag) && live[0] == 0x1234 &&
            live[Scratch/8-1] == 0x5678, "active buffer reclaimed or corrupted");
    if (disowned) {
      require(Base::IsClientBufferFree(idle1.flag) == pressure, "idle ownership mismatch");
      // A revoked iterator is intentionally stale. Production must check its
      // client flag before dereferencing it (sanitizers exercise this).
      auto reowned = pool.TryToReownBuffer(idle1.buffer, size, &idle1.flag);
      require(reowned.has_value() != pressure, "revoked owner reowned stale buffer");
    }
    pool.UnclaimBuffer(requester.buffer, &requester.flag);
    pool.UnclaimBuffer(active.buffer, &active.flag);
    pool.UnclaimBuffer(idle1.buffer, &idle1.flag);
    if (split) pool.UnclaimBuffer(idle2.buffer, &idle2.flag);
  }
  a.release(filler, 8160 * MiB);
  require(a.used == 0 && a.failures == 1, "pressure fixture leaked or failed retry");
  print(split ? (disowned ? "pressure_adjacent_disowned_8mib" : "pressure_adjacent_unclaimed_8mib")
              : "pressure_young_disowned_16mib", a, pressure ? 0 : 1);
}
static void pressureRace() {
  Arena a(8192 * MiB); arena = &a;
  void *filler = a.allocate(8176 * MiB);
  size_t nulls = 0;
  for (int trial = 0; trial < 100; ++trial) {
    Pool pool; Client owner, requester;
    owner.buffer = pool.ClaimBuffer(Scratch, &owner.flag);
    auto *original = static_cast<volatile uint64_t *>((*owner.buffer)->Ptr);
    original[0] = 42; original[Scratch/8-1] = 43;
    pool.DisownBuffer(owner.buffer);
    (*owner.buffer)->LastUsed.store(Base::ClockType::now()+std::chrono::hours(1));
    std::barrier start(2);
    bool reowned = false;
    std::thread first([&] {
      start.arrive_and_wait();
      reowned = pool.TryToReownBuffer(owner.buffer, Scratch, &owner.flag).has_value();
      if (reowned) require(original[0] == 42 && original[Scratch/8-1] == 43, "active race owner corrupted");
    });
    std::thread second([&] {
      start.arrive_and_wait();
      requester.buffer = pool.ClaimBuffer(Scratch, &requester.flag);
      auto *p = static_cast<volatile uint64_t *>((*requester.buffer)->Ptr);
      if (p) { p[0] = 99; p[Scratch/8-1] = 100; }
    });
    first.join(); second.join();
    bool allocated = (*requester.buffer)->Ptr != nullptr;
    require(reowned != allocated, "race ownership was duplicated or lost");
    if (!allocated) {
      ++nulls;
      require(Base::IsClientBufferOwned(requester.flag), "known null ownership behavior changed");
      require(original[0] == 42 && original[Scratch/8-1] == 43, "active race owner overwritten");
    }
    pool.UnclaimBuffer(owner.buffer, &owner.flag);
    pool.UnclaimBuffer(requester.buffer, &requester.flag);
  }
  a.release(filler, 8176 * MiB);
  require(a.used == 0, "race leaked buffers");
  print("pressure_races_lock_free_reown", a, nulls);
}
int main() {
  try {
    exhaustion(); reuse(); fragmentation(); retirement();
    concurrency(4); concurrency(9); concurrency(84);
    pressureRecovery(true, false); pressureRecovery(true, true);
    pressureRecovery(false, true); pressureRace();
  }
  catch(const std::exception &e) { std::fprintf(stderr,"FAIL: %s\n",e.what()); return 1; }
}
