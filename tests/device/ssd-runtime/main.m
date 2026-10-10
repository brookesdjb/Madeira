// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 125hz
// Madeira Converter Exception: see LICENSE-EXCEPTION.md
#import <Foundation/Foundation.h>
#include <dlfcn.h>
extern void madeira_ssd_overlay_install(void);
int main(int argc, char **argv) {
    @autoreleasepool {
        // The exact prebuilt binary is hash-checked by build.py. Use its original
        // app entry point and original JIT/launch UI, not a reimplemented engine.
        void *runtime = dlopen("@executable_path/Madeira.debug.dylib", RTLD_NOW | RTLD_GLOBAL);
        if (!runtime) { fprintf(stderr, "SSD runtime could not load\n"); return 1; }
        int (*entry)(int, char **) = dlsym(runtime, "main");
        if (!entry) return 2;
        [[NSUserDefaults standardUserDefaults] setObject:@"old" forKey:@"madeiraFrontend"];
        madeira_ssd_overlay_install();
        return entry(argc, argv);
    }
}
