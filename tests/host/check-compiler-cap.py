#!/usr/bin/env python3
# Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception.
"""Apply the optional DXMT patch only in a temporary tree and test scheduler.

Real production scheduler with host thread/Win32 priority adapters. This is not
shader compilation or native/PE integration evidence. Live DXMT is never edited.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dxmt-root", type=Path, default=root / "dxmt")
args = parser.parse_args()
patch = root / "build/dxmt-ios/experiments/compiler-worker-cap.patch"
source = (args.dxmt_root / "src/dxmt/dxmt_tasks.hpp").read_text()
preamble = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <functional>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
static unsigned hardware;
static std::string cap;
static std::atomic_uint created, completed;
static std::atomic_bool release_work;
static void *GetCurrentThread() { return nullptr; }
static void SetThreadPriority(void *, int) {}
#define THREAD_PRIORITY_TIME_CRITICAL 0
namespace dxmt {
using mutex = std::mutex;
static std::atomic_bool gap_mode;
static std::atomic_uint gaps;
struct condition_variable : std::condition_variable {
  template<typename Lock, typename Predicate> void wait(Lock &lock, Predicate predicate) {
    while (!predicate()) {
      if (gap_mode) {
        gaps++;
        // Expand the legal gap between predicate evaluation and wait entry.
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
      }
      std::condition_variable::wait(lock);
    }
  }
};
struct thread : std::thread {
  template<typename F> thread(F &&fn) : std::thread(std::forward<F>(fn)) { created++; }
  thread(thread &&) = default;
  static unsigned hardware_concurrency() { return hardware; }
};
namespace env { std::string getEnvVar(const char *) { return cap; } }
struct Node { std::atomic_bool done{false}; Node *dependency = nullptr; bool hold = false; std::atomic_uint attempts{0}; };
}
"""
main = r"""
namespace dxmt {
template<> Node *task_trait<Node *>::run_task(Node *node) {
  node->attempts++;
  if (node->dependency && !node->dependency->done.load()) return node->dependency;
  if (node->hold) while (!release_work.load()) std::this_thread::yield();
  return node;
}
template<> bool task_trait<Node *>::get_done(Node *node) { return node->done.load(); }
template<> void task_trait<Node *>::set_done(Node *node) { assert(!node->done.exchange(true)); completed++; }
}
template<typename F> void until(F predicate) {
  auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!predicate()) { assert(std::chrono::steady_clock::now() < deadline); std::this_thread::yield(); }
}
int main(int argc, char **argv) {
  assert(argc == 3); cap = argv[1]; hardware = std::stoul(argv[2]);
  if (cap == "shutdown-gap") {
    dxmt::gap_mode = true;
    auto scheduler = new dxmt::task_scheduler<dxmt::Node *>;
    until([] { return dxmt::gaps.load() > 0; });
    delete scheduler;
    puts("PASS: forced predicate/wait shutdown interleaving");
    return 0;
  }
  unsigned expected = hardware * 2;
  if (cap == "2" || cap == "4") expected = std::min(cap == "2" ? 2u : 4u, std::max(2u, expected));
  unsigned effective = std::max(2u, expected); // Upstream always initially launches two.
  {
    dxmt::task_scheduler<dxmt::Node *> scheduler;
    dxmt::Node held[32];
    for (unsigned i = 0; i < effective; ++i) {
      held[i].hold = true;
      scheduler.submit(&held[i]);
      if (i < 2) until([&] { return scheduler.get_running_threads() >= i + 1; });
      else until([&] { return created.load() >= i + 1 && scheduler.get_running_threads() >= i + 1; });
    }
    assert(created.load() == effective);
    release_work = true;
    until([&] { return completed.load() == effective; });
    until([&] { return scheduler.get_running_threads() == 0; });
    assert(created.load() == effective);
    // A dependent task must yield to a missing dependency, then resume exactly
    // once; already-completed dependencies must not strand later submissions.
    dxmt::Node dependency, dependent, ready_dependent;
    dependent.dependency = &dependency;
    scheduler.submit(&dependent);
    until([&] { return dependent.attempts.load() >= 1 && scheduler.get_running_threads() == 0; });
    assert(!dependent.done.load()); scheduler.submit(&dependency);
    until([&] { return dependent.done.load(); });
    ready_dependent.dependency = &dependency; scheduler.submit(&ready_dependent);
    until([&] { return ready_dependent.done.load(); });
    assert(dependent.attempts >= 2);
    assert(completed == effective + 3);
  } // Idle worker wake and join.
  printf("PASS: cap='%s' cpu=%u workers=%u; dependent continuation, completed-dependency retry, idle shutdown\n", cap.c_str(), hardware, created.load());
}
"""
with tempfile.TemporaryDirectory(prefix="madeira-compiler-cap-") as tmp:
    path = Path(tmp)
    header = path / "src/dxmt/dxmt_tasks.hpp"
    header.parent.mkdir(parents=True)
    header.write_text(source)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=path, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=path, check=True)
    shutdown_patch = root / "build/dxmt-ios/experiments/scheduler-shutdown.patch"
    subprocess.run(["git", "apply", str(shutdown_patch)], cwd=path, check=True)
    body = "\n".join(line for line in header.read_text().splitlines() if not line.startswith("#include") and line != "#pragma once")
    cpp, binary = path / "scheduler.cpp", path / "scheduler"
    cpp.write_text(preamble + body + main)
    subprocess.run(["clang++", "-std=c++20", "-pthread", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary), "shutdown-gap", "8"], check=True, timeout=5)
    # Negative control uses the original production destructor with the same
    # expanded gap. It must hang; a subprocess timeout bounds that reproduction.
    original_body = "\n".join(line for line in source.splitlines() if not line.startswith("#include") and line != "#pragma once")
    negative_cpp, negative = path / "negative.cpp", path / "negative"
    negative_cpp.write_text(preamble + original_body + main)
    subprocess.run(["clang++", "-std=c++20", "-pthread", str(negative_cpp), "-o", str(negative)], check=True)
    try:
        subprocess.run([str(negative), "shutdown-gap", "8"], check=True, timeout=2)
    except subprocess.TimeoutExpired:
        print("PASS: original-destructor negative control reproduces lost shutdown notification", flush=True)
    else:
        raise AssertionError("negative control unexpectedly completed")
    for hardware in (0, 1, 8):
        for cap in ("", "2", "4", "0", "2junk", "999"):
            subprocess.run([str(binary), cap, str(hardware)], check=True, timeout=10)
print("PASS: 18 host cases under ASan/UBSan; patch applies to pinned scheduler; live source unchanged")
