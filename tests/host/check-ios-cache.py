#!/usr/bin/env python3
# Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception.
"""Exercise pinned DXMT iOS resolver/SQLite implementation on macOS.

Uses temporary paths and a simulated sandbox cache-directory lookup. Does not
run Metal or establish iPad sandbox behavior. No real app caches are touched.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dxmt-root", type=Path, default=root / "dxmt")
args = parser.parse_args()
source = (args.dxmt_root / "src/winemetal/unix/cache.c").read_text()
body = source[source.index("@interface CacheReader :"):source.index("int\n_CacheReader_alloc_init")]
# Leave production methods intact. Substitute only platform lookup and one
# SQLite fault boundary, so tests never resolve the user's real cache directory.
preamble = r"""
#import <Foundation/Foundation.h>
#include <dispatch/dispatch.h>
#include <sqlite3.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <assert.h>
#undef TARGET_OS_IPHONE
#define TARGET_OS_IPHONE 1
static NSString *test_base;
static unsigned long test_wow;
static bool test_disk_full;
unsigned long ios_wow_base(void) { return test_wow; }
static NSArray *test_caches(NSSearchPathDirectory d, NSSearchPathDomainMask m, BOOL expand) {
  (void)d; (void)m; (void)expand;
  return test_base ? @[test_base] : @[];
}
static size_t test_confstr(int name, char *buffer, size_t size) {
  (void)name; (void)buffer; (void)size; return 0;
}
static int test_step(sqlite3_stmt *stmt) {
  if (test_disk_full && !sqlite3_stmt_readonly(stmt)) return SQLITE_FULL;
  return sqlite3_step(stmt);
}
#define NSSearchPathForDirectoriesInDomains test_caches
#define confstr test_confstr
#define sqlite3_step test_step
"""
main = r"""
static NSData *key(const char *value) { return [NSData dataWithBytes:value length:strlen(value)]; }
static void put(CacheWriter *writer, const char *k, const char *v) {
  dispatch_data_t data = dispatch_data_create(v, strlen(v), NULL, DISPATCH_DATA_DESTRUCTOR_DEFAULT);
  [writer set:key(k) value:data]; dispatch_release(data);
}
static bool matches(CacheReader *reader, const char *k, const char *v) {
  dispatch_data_t data = [reader get:key(k)];
  if (!data) return false;
  const void *bytes; size_t size;
  dispatch_data_t mapped = dispatch_data_create_map(data, &bytes, &size);
  bool ok = size == strlen(v) && !memcmp(bytes, v, size);
  dispatch_release(mapped); dispatch_release(data); return ok;
}
int main(int argc, char **argv) {
  assert(argc == 2);
  @autoreleasepool {
    NSString *tmp = [NSString stringWithUTF8String:argv[1]];
    test_base = [tmp stringByAppendingPathComponent:@"sandbox"];
    unsetenv("DXMT_IOS_CACHE_DIR"); test_wow = 0;
    assert(!use_ios_cache_dir());
    assert(!resolve_cache_dir(@"dxmt/title/cache.db", true));
    test_wow = 1; assert(use_ios_cache_dir());
    setenv("DXMT_IOS_CACHE_DIR", "0", 1); assert(!use_ios_cache_dir());
    for (const char **v = (const char *[]){"1", "on", "garbage", NULL}; *v; ++v) {
      setenv("DXMT_IOS_CACHE_DIR", *v, 1);
      test_wow = 0; assert(use_ios_cache_dir());
      test_wow = 1; assert(use_ios_cache_dir());
    }
    setenv("DXMT_IOS_CACHE_DIR", "", 1); test_wow = 0; assert(!use_ios_cache_dir());
    setenv("DXMT_IOS_CACHE_DIR", "1", 1);
    NSString *relative = @"dxmt/title/cache.db";
    NSString *resolved = [test_base stringByAppendingPathComponent:relative];
    assert([resolve_cache_dir(relative, true) isEqualToString:resolved]);
    assert([[NSFileManager defaultManager] fileExistsAtPath:[resolved stringByDeletingLastPathComponent]]);
    NSString *absolute = [tmp stringByAppendingPathComponent:@"absolute/cache.db"];
    assert([resolve_cache_dir(absolute, true) isEqualToString:absolute]);
    assert([resolve_cache_dir(@"metal/title", false) isEqualToString:[test_base stringByAppendingPathComponent:@"metal/title"]]);
    assert(!resolve_cache_dir(@"", true));
    NSString *saved_base = test_base; test_base = nil;
    assert(!resolve_cache_dir(relative, true)); test_base = saved_base;
    NSString *obstacle = [tmp stringByAppendingPathComponent:@"file"];
    assert([@"not a directory" writeToFile:obstacle atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
    assert(!resolve_cache_dir([obstacle stringByAppendingPathComponent:@"cache.db"], true));
    CacheWriter *writer = [[CacheWriter alloc] initWithPath:relative version:41]; assert(writer);
    put(writer, "shader", "compiled-blob"); [writer release];
    // Second and third object sessions read the persisted, versioned SQLite blob.
    for (int i = 0; i < 2; ++i) {
      CacheReader *reader = [[CacheReader alloc] initWithPath:relative version:41]; assert(reader);
      assert(matches(reader, "shader", "compiled-blob"));
      assert(![reader get:key("absent")]); [reader release];
    }
    assert(![[CacheReader alloc] initWithPath:relative version:42]);
    CacheWriter *other = [[CacheWriter alloc] initWithPath:relative version:42]; assert(other);
    put(other, "shader", "new-version"); [other release];
    CacheReader *reader = [[CacheReader alloc] initWithPath:relative version:41]; assert(reader);
    assert(matches(reader, "shader", "compiled-blob")); [reader release];
    // Independent writers/readers share the DB; sequential writes avoid assuming
    // a retry policy for simultaneous SQLITE_BUSY that this source does not have.
    writer = [[CacheWriter alloc] initWithPath:relative version:41]; assert(writer);
    other = [[CacheWriter alloc] initWithPath:relative version:41]; assert(other);
    put(writer, "one", "a"); put(other, "two", "b");
    test_disk_full = true; put(writer, "full", "must-not-appear"); test_disk_full = false;
    put(writer, "recovery", "c"); [writer release]; [other release];
    reader = [[CacheReader alloc] initWithPath:relative version:41]; assert(reader);
    assert(matches(reader, "one", "a") && matches(reader, "two", "b"));
    assert(![reader get:key("full")]); assert(matches(reader, "recovery", "c")); [reader release];
    NSString *corrupt = [tmp stringByAppendingPathComponent:@"corrupt.db"];
    assert([@"not sqlite" writeToFile:corrupt atomically:YES encoding:NSUTF8StringEncoding error:NULL]);
    assert(![[CacheReader alloc] initWithPath:corrupt version:41]);
    assert(![[CacheWriter alloc] initWithPath:corrupt version:41]);
    puts("PASS: bitness/override policy, paths/failure fallback, persisted versioned blobs, independent objects, simulated SQLITE_FULL and corruption");
  }
  return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="madeira-ios-cache-") as tmp:
    path = Path(tmp)
    src, binary = path / "cache.m", path / "cache"
    src.write_text(preamble + body + main)
    subprocess.run(["clang", "-x", "objective-c", "-fblocks", "-fno-objc-arc", "-Wno-incompatible-pointer-types", "-fsanitize=address,undefined", "-framework", "Foundation", "-lsqlite3", str(src), "-o", str(binary)], check=True)
    subprocess.run([str(binary), tmp], check=True, timeout=30)
print("Host Foundation/SQLite checks only; platform lookup and disk-full are simulated, no Metal or iPad claim.")
