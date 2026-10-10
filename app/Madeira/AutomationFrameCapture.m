#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import "AutomationFrameCapture.h"
#if DEBUG && MADEIRA_AUTOMATION
#include "automation_frame_ring.h"
#include <sys/resource.h>
#include <mach/mach.h>
extern int madeira_automation_frame_hook_available(void) __attribute__((weak_import));
static NSString *captureID;
static int completed;
static id backgroundObserver;
static char exportStatus[80];
static uint64_t wallStart, wallEnd;
static struct rusage cpuStart, cpuEnd;
static int cpuValid;
static NSNumber *footprintStart, *footprintEnd;
static uint64_t monotonicNS(void) {
    struct timespec t; if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static NSNumber *footprint(void) {
    task_vm_info_data_t v = {0}; mach_msg_type_number_t n = TASK_VM_INFO_COUNT;
    return task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&v, &n) == KERN_SUCCESS ? @(v.phys_footprint) : nil;
}
static uint64_t timeNS(struct timeval t) { return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_usec * 1000; }

int madeira_automation_capture_start(void) {
    if (!madeira_automation_frame_hook_available || !madeira_automation_frame_hook_available()) return -1;
    if (atomic_load(&madeira_frame_active)) return 0;
    footprintStart = footprint(); cpuValid = getrusage(RUSAGE_SELF, &cpuStart) == 0;
    wallStart = monotonicNS(); wallEnd = 0;
    if (!madeira_frame_begin()) return 0;
    captureID = NSUUID.UUID.UUIDString; completed = 0;
    if (!backgroundObserver) backgroundObserver = [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationWillResignActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { madeira_automation_capture_stop(); }];
    return 1;
}
void madeira_automation_record_present(void) { madeira_frame_record(); }
void madeira_automation_capture_stop(void) {
    if (!atomic_load(&madeira_frame_active)) return;
    madeira_frame_end(); wallEnd = monotonicNS();
    cpuValid = (getrusage(RUSAGE_SELF, &cpuEnd) == 0) && cpuValid;
    footprintEnd = footprint(); completed = captureID != nil;
}
const char *madeira_automation_capture_export(void) {
    if (!completed || atomic_load(&madeira_frame_active)) return "capture_not_stopped";
    /* Export after measurement, away from the Present hot path. Start/stop/export
       are serialized on main by AutomationProbe. Recorder writers are stopped. */
    NSMutableArray *samples = [NSMutableArray arrayWithCapacity:madeira_frame_count];
    for (uint64_t i = 0; i < madeira_frame_count; i++) {
        [samples addObject:@{@"sequence": @(madeira_frames[i].sequence), @"timestamp_ns": @(madeira_frames[i].timestamp_ns)}];
    }
    NSDictionary *trace = @{@"schema_version": @1, @"clock": @"clock_monotonic_ns",
        @"scope": @"present_submission", @"capture_id": captureID, @"complete": @YES,
        @"dropped_samples": @(atomic_load(&madeira_frame_dropped)), @"samples": samples};
    NSData *data = [NSJSONSerialization dataWithJSONObject:trace options:0 error:nil];
    NSURL *folder = [[[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask] firstObject];
    NSURL *file = [folder URLByAppendingPathComponent:@"automation-submission-trace.json"];
    if (!data || data.length > 32 * 1024 * 1024 || ![data writeToURL:file options:NSDataWritingAtomic error:nil]) return "capture_export_failed";
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @0600} ofItemAtPath:file.path error:nil];
    uint64_t userStart = timeNS(cpuStart.ru_utime), userEnd = timeNS(cpuEnd.ru_utime);
    uint64_t systemStart = timeNS(cpuStart.ru_stime), systemEnd = timeNS(cpuEnd.ru_stime);
    cpuValid = cpuValid && userEnd >= userStart && systemEnd >= systemStart;
    NSDictionary *metadata = @{@"schema_version": @1, @"capture_id": captureID,
        @"scope": @"whole_app_process", @"clock": @"clock_monotonic_ns",
        @"wall_ns": wallEnd > wallStart ? @(wallEnd - wallStart) : NSNull.null,
        @"user_cpu_ns": cpuValid ? @(userEnd - userStart) : NSNull.null,
        @"system_cpu_ns": cpuValid ? @(systemEnd - systemStart) : NSNull.null,
        @"footprint_before_bytes": footprintStart ?: NSNull.null,
        @"footprint_after_bytes": footprintEnd ?: NSNull.null};
    NSData *sidecar = [NSJSONSerialization dataWithJSONObject:metadata options:0 error:nil];
    NSURL *metadataFile = [folder URLByAppendingPathComponent:@"automation-capture-metadata.json"];
    if (!sidecar || ![sidecar writeToURL:metadataFile options:NSDataWritingAtomic error:nil]) return "capture_metadata_export_failed";
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @0600} ofItemAtPath:metadataFile.path error:nil];
    snprintf(exportStatus, sizeof exportStatus, "madeira.automation.frame-capture:exported");
    return exportStatus;
}
#endif
