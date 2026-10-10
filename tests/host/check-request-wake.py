#!/usr/bin/env python3
# Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception.
"""Production coalescing helper/wake wrapper using real macOS Mach semaphores.

No periodic timer rescues requests. Temporary host queues substitute Wine FDs;
this does not establish guest, INET, timer or iPad shutdown correctness.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / "build/wineserver/fd_ios.c").read_text()
wrapper = source[source.index("semaphore_t ios_srv_wake_sem = 0;"):source.index("/* __WINESRC__ must")]
clear = source.index("/* Clear before any readiness scan.")
assert clear < source.index("/* Real sockets first:", clear)
assert source.index("ios_request_wake_begin_scan( &ios_srv_request_wake );", clear) < source.index("set_current_time();", clear)
assert 'coalesce && !strcmp( coalesce, "1" )' in source
assert 'if (ios_next_timer_ns < sleep_ns) sleep_ns = ios_next_timer_ns;' in source
assert 'if (g_wineserver_should_stop)' in source

harness = r"""
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <mach/mach.h>
#include <mach/semaphore.h>
#include "request_wake_ios.h"
""" + wrapper + r"""
static void create(int enabled) {
  assert(semaphore_create(mach_task_self(), &ios_srv_wake_sem, SYNC_POLICY_FIFO, 0) == KERN_SUCCESS);
  ios_srv_coalesce = enabled; ios_request_wake_begin_scan(&ios_srv_request_wake);
}
static void destroy(void) { assert(semaphore_destroy(mach_task_self(), ios_srv_wake_sem) == KERN_SUCCESS); ios_srv_wake_sem = 0; }
static int take(void) { mach_timespec_t zero = {0,0}; return semaphore_timedwait(ios_srv_wake_sem, zero) == KERN_SUCCESS; }
static int drain(void) { int n = 0; while (take()) ++n; return n; }
static atomic_uint queue[4];
static atomic_uint seen;
static void *producer(void *arg) {
  int slot = (int)(intptr_t)arg;
  for (unsigned i = 0; i < 20000; ++i) {
    atomic_fetch_add_explicit(&queue[slot], 1, memory_order_seq_cst);
    ios_wineserver_wake();
    if (!(i & 63)) sched_yield();
  }
  return NULL;
}
static void *consumer(void *arg) {
  int enabled = (int)(intptr_t)arg;
  while (atomic_load(&seen) < 80000) {
    // Deliberately unbounded wait: Python's process timeout fails this test if
    // a signal is lost. There is no 1 ms timer or periodic recovery scan.
    assert(semaphore_wait(ios_srv_wake_sem) == KERN_SUCCESS);
    if (enabled) ios_request_wake_begin_scan(&ios_srv_request_wake);
    for (int i = 0; i < 4; ++i) {
      atomic_fetch_add(&seen, atomic_exchange(&queue[i], 0));
      sched_yield();
    }
  }
  return NULL;
}
int main(void) {
  // Before semaphore availability, preserve the existing no-op fallback.
  ios_wineserver_wake(); assert(!ios_srv_request_wake.pending);
  for (int enabled = 0; enabled < 2; ++enabled) {
    create(enabled);
    for (int i = 0; i < 10000; ++i) ios_wineserver_wake();
    assert(drain() == (enabled ? 1 : 10000));
    destroy();
  }
  create(1);
  // Coalesced pre-clear publication is picked up by the upcoming scan.
  atomic_store(&queue[0], 1); ios_wineserver_wake(); assert(take());
  atomic_fetch_add(&queue[0], 1); ios_wineserver_wake(); assert(!take());
  ios_request_wake_begin_scan(&ios_srv_request_wake);
  assert(atomic_exchange(&queue[0], 0) == 2);
  // Publication after a descriptor was scanned must leave a future wake.
  atomic_store(&queue[0], 1); ios_wineserver_wake(); assert(take());
  ios_request_wake_begin_scan(&ios_srv_request_wake); assert(atomic_exchange(&queue[0], 0) == 1);
  // Negative control: clear-after-scan loses the post-scan request while pending
  // remains set. This is the race the production clear-before-scan avoids.
  ios_wineserver_wake(); assert(take());
  assert(atomic_exchange(&queue[0], 0) == 0);
  atomic_store(&queue[0], 1); ios_wineserver_wake();
  ios_request_wake_begin_scan(&ios_srv_request_wake);
  assert(!take() && atomic_load(&queue[0]) == 1);
  atomic_store(&queue[0], 0);
  // A publisher delayed between marking and kernel signalling can leave an
  // extra token, but must not erase another publisher's later wake.
  assert(ios_request_wake_mark(&ios_srv_request_wake));
  ios_request_wake_begin_scan(&ios_srv_request_wake);
  ios_wineserver_wake(); assert(semaphore_signal(ios_srv_wake_sem) == KERN_SUCCESS);
  assert(drain() == 2); destroy();
  for (int enabled = 0; enabled < 2; ++enabled) {
    for (int trial = 0; trial < 5; ++trial) {
      create(enabled); atomic_store(&seen, 0);
      pthread_t server, clients[4];
      assert(!pthread_create(&server, NULL, consumer, (void *)(intptr_t)enabled));
      for (int i = 0; i < 4; ++i) assert(!pthread_create(&clients[i], NULL, producer, (void *)(intptr_t)i));
      for (int i = 0; i < 4; ++i) assert(!pthread_join(clients[i], NULL));
      assert(!pthread_join(server, NULL)); assert(atomic_load(&seen) == 80000);
      for (int i = 0; i < 4; ++i) assert(!atomic_load(&queue[i]));
      destroy();
    }
  }
  puts("PASS: exact burst signal counts, clear/scan race cases and negative control, delayed publisher, 800000 requests without timeout rescue");
  return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="madeira-request-wake-") as tmp:
    path = Path(tmp)
    src, binary = path / "wake.c", path / "wake"
    src.write_text(harness)
    subprocess.run(["clang", "-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(root / "build/wineserver"), str(src), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=45)
print("PASS: production scan placement/deadline/stop source guards; ASan/UBSan, host queues only")
