#ifndef OTA_ADMIN_H
#define OTA_ADMIN_H
#include "ota-common.h"
#include <stddef.h>
#define OTA_UPLOAD_MAX (512ULL * 1024 * 1024)
struct ota_report;
int ota_quarantine_blocked(const char *root, const char *directory);
int ota_quarantine_report(const char *root, const struct ota_report *report);
int ota_quarantine_json(const char *root, void *stream);
int ota_firmware_identity(const char *directory, char hash[65], unsigned long *version);
int ota_image_identity(const char *directory, unsigned long long publication, char *body, size_t capacity);
int ota_fit_version(const char *directory, unsigned long *version);
int ota_inspect(const char *directory, struct release *r, unsigned long *version);
int ota_draft_begin(const char *root, char temp[OTA_PATH]);
void ota_draft_cleanup(const char *temp);
int ota_draft_finish(const char *root, const char *temp, char id[32]);
int ota_admin_state(const char *root, char **json);
int ota_admin_publish(const char *root, const char *id, unsigned long long *number);
#endif
