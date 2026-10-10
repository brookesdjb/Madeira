#pragma once
#include <stdatomic.h>
#include <stdint.h>
#include <time.h>
#ifndef MADEIRA_FRAME_CAPACITY
#define MADEIRA_FRAME_CAPACITY 250000
#endif
struct madeira_frame_sample { uint64_t sequence, timestamp_ns; };
static struct madeira_frame_sample madeira_frames[MADEIRA_FRAME_CAPACITY];
static atomic_flag madeira_frame_lock = ATOMIC_FLAG_INIT;
static _Atomic int madeira_frame_active;
static _Atomic uint64_t madeira_frame_dropped;
static _Atomic unsigned madeira_frame_writers;
static uint64_t madeira_frame_count;
static inline void madeira_frame_acquire(void) {
    while (atomic_flag_test_and_set_explicit(&madeira_frame_lock, memory_order_acquire)) {}
}
static inline void madeira_frame_release(void) {
    atomic_flag_clear_explicit(&madeira_frame_lock, memory_order_release);
}
static inline int madeira_frame_begin(void) {
    madeira_frame_acquire();
    if (atomic_load(&madeira_frame_active)) { madeira_frame_release(); return 0; }
    madeira_frame_count = 0; atomic_store(&madeira_frame_dropped, 0);
    atomic_store(&madeira_frame_active, 1); madeira_frame_release(); return 1;
}
static inline void madeira_frame_end(void) {
    atomic_store(&madeira_frame_active, 0);
    while (atomic_load(&madeira_frame_writers)) {}
    madeira_frame_acquire(); madeira_frame_release();
}
static inline void madeira_frame_record(void) {
    if (!atomic_load_explicit(&madeira_frame_active, memory_order_relaxed)) return;
    atomic_fetch_add(&madeira_frame_writers, 1);
    if (!atomic_load(&madeira_frame_active)) { atomic_fetch_sub(&madeira_frame_writers, 1); return; }
    if (atomic_flag_test_and_set_explicit(&madeira_frame_lock, memory_order_acquire)) {
        atomic_fetch_add_explicit(&madeira_frame_dropped, 1, memory_order_relaxed); atomic_fetch_sub(&madeira_frame_writers, 1); return;
    }
    if (atomic_load_explicit(&madeira_frame_active, memory_order_relaxed)) {
        struct timespec ts;
        if (madeira_frame_count >= MADEIRA_FRAME_CAPACITY || clock_gettime(CLOCK_MONOTONIC, &ts)) {
            atomic_fetch_add_explicit(&madeira_frame_dropped, 1, memory_order_relaxed);
        } else {
            uint64_t ns = (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
            if (madeira_frame_count && ns <= madeira_frames[madeira_frame_count - 1].timestamp_ns)
                atomic_fetch_add_explicit(&madeira_frame_dropped, 1, memory_order_relaxed);
            else {
                madeira_frames[madeira_frame_count] = (struct madeira_frame_sample){madeira_frame_count + 1, ns};
                madeira_frame_count++;
            }
        }
    }
    madeira_frame_release();
    atomic_fetch_sub(&madeira_frame_writers, 1);
}
