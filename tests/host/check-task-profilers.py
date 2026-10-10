#!/usr/bin/env python3
# Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception.
"""Compile the production task-profiler startup policy with stub workers.

Checks default-off/strict opt-in, every independent job combination, one-time
ownership under concurrent pseudo-process startup, and fixed configuration after
first startup. The workers/dispatch are stubs: this is not iPad sampler evidence.
Needs a C compiler supporting Blocks and pthreads (Apple clang on this Mac).
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[2]
source = (root / "build/ntdll-unix/server_ios.c").read_text()
start = source.index("static pthread_once_t ios_task_profilers_once")
end = source.index("\n\n/* iOS-Madeira 2026-07-05: per-present", start)
policy = source[start:end]
names = ("MADEIRA_PROFILE_THREADS", "MADEIRA_PROFILE_XP", "MADEIRA_PROFILE_STACKS")
jobs = ("ios_thread_sampler_main", "ios_xprobe_main", "ios_wprof_main")

# A job must have exactly one launch site, all inside the tested policy; process
# init must call the one-time wrapper. Keep the independent legacy quiet gate.
for job in jobs:
    assert source.count(f"^{{ {job}(); }}") == 1, job
    assert f"^{{ {job}(); }}" in policy, job
init = source[source.index("void server_init_process_done("):]
assert init.count("ios_start_task_profilers();") == 1
assert 'if (!getenv("MADEIRA_QUIET"))' in init

harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
static atomic_int jobs[3], logs;
static void ios_thread_sampler_main(void) { atomic_fetch_add(&jobs[0], 1); }
static void ios_xprobe_main(void) { atomic_fetch_add(&jobs[1], 1); }
static void ios_wprof_main(void) { atomic_fetch_add(&jobs[2], 1); }
static void wine_log_write(const char *fmt, ...) { (void)fmt; atomic_fetch_add(&logs, 1); }
#define QOS_CLASS_UTILITY 0
static int dispatch_get_global_queue(int qos, int flags) { (void)qos; (void)flags; return 0; }
static void dispatch_async(int queue, void (^worker)(void)) { (void)queue; worker(); }
''' + policy + r'''
static void *startup(void *unused)
{
    (void)unused;
    for (int i = 0; i < 100; ++i) ios_start_task_profilers();
    return NULL;
}
int main(int argc, char **argv)
{
    assert(argc == 4);
    const char *names[] = {"MADEIRA_PROFILE_THREADS", "MADEIRA_PROFILE_XP", "MADEIRA_PROFILE_STACKS"};
    pthread_t clients[32];
    for (int i = 0; i < 32; ++i) assert(!pthread_create(&clients[i], NULL, startup, NULL));
    for (int i = 0; i < 32; ++i) assert(!pthread_join(clients[i], NULL));
    int enabled = 0;
    for (int i = 0; i < 3; ++i) {
        int want = atoi(argv[i + 1]);
        assert(atomic_load(&jobs[i]) == want);
        enabled |= want;
        /* Changing env after startup must neither start nor duplicate jobs. */
        assert(!setenv(names[i], want ? "0" : "1", 1));
    }
    ios_start_task_profilers();
    for (int i = 0; i < 3; ++i) assert(atomic_load(&jobs[i]) == atoi(argv[i + 1]));
    assert(atomic_load(&logs) == enabled);
    return 0;
}
'''

cases = 0
with tempfile.TemporaryDirectory(prefix="madeira-task-profilers-") as tmp:
    path = Path(tmp)
    c = path / "startup.c"
    binary = path / "startup"
    c.write_text(harness)
    cc = shlex.split(os.environ.get("CC", "clang"))
    subprocess.run(cc + ["-std=c11", "-fblocks", "-pthread", "-Wall", "-Wextra",
                         "-Werror", "-fsanitize=address,undefined", str(c), "-o", str(binary)]
                         + (["-lBlocksRuntime"] if sys.platform == "linux" else []), check=True)

    def check(values, wanted, quiet):
        global cases
        env = os.environ.copy()
        for name in names + ("MADEIRA_QUIET",):
            env.pop(name, None)
        for name, value in zip(names, values):
            if value is not None:
                env[name] = value
        if quiet is not None:
            env["MADEIRA_QUIET"] = quiet
        subprocess.run([str(binary)] + [str(v) for v in wanted], env=env,
                       check=True, timeout=15)
        cases += 1

    for quiet in (None, "1"):
        for mask in range(8):
            wanted = tuple((mask >> i) & 1 for i in range(3))
            check(tuple("1" if bit else None for bit in wanted), wanted, quiet)
        for value in ("on", "ON", "yes", "YeS", "true", "TRUE"):
            check((value,) * 3, (1, 1, 1), quiet)
        for value in ("", "0", "off", "false", "no", "2", "-1", "garbage", "1junk", " on "):
            check((value,) * 3, (0, 0, 0), quiet)

print(f"PASS: {cases} policy cases, 32 concurrent clients per case, fixed startup settings; ASan/UBSan")
print("PASS: gated launch sites and legacy quiet gate retained (stub workers, no device measurements)")
