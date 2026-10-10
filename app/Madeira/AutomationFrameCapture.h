/* Debug automation only. Fixed storage; no allocation or I/O on Present. */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int madeira_automation_capture_start(void);
void madeira_automation_capture_stop(void);
const char *madeira_automation_capture_export(void);
void madeira_automation_record_present(void);
#ifdef __cplusplus
}
#endif
