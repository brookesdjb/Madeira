#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import "AutomationFrameCapture.h"
#if DEBUG && MADEIRA_AUTOMATION
#include "automation_frame_ring.h"
extern int madeira_automation_frame_hook_available(void) __attribute__((weak_import));
static NSString *captureID;
static int completed;
static id backgroundObserver;
static char exportStatus[80];
int madeira_automation_capture_start(void) {
    if (!madeira_automation_frame_hook_available || !madeira_automation_frame_hook_available()) return -1;
    if (!madeira_frame_begin()) return 0;
    captureID = NSUUID.UUID.UUIDString; completed = 0;
    if (!backgroundObserver) backgroundObserver = [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationWillResignActiveNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { madeira_automation_capture_stop(); }];
    return 1;
}
void madeira_automation_record_present(void) { madeira_frame_record(); }
void madeira_automation_capture_stop(void) { madeira_frame_end(); completed = captureID != nil; }
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
    snprintf(exportStatus, sizeof exportStatus, "madeira.automation.frame-capture:exported");
    return exportStatus;
}
#endif
