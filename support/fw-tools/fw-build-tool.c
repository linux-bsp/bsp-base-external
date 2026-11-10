#define _GNU_SOURCE
#include <cjson/cJSON.h>
#include <errno.h>
#include <fcntl.h>
#include <libfdt.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void fail(const char *message)
{
    fprintf(stderr, "fw-build-tool: %s\n", message);
    exit(EXIT_FAILURE);
}

static unsigned char *read_file(const char *path, size_t *size)
{
    FILE *file = fopen(path, "rb");
    struct stat info;
    if (!file || fstat(fileno(file), &info) || info.st_size < 0 || info.st_size > 512 * 1024 * 1024)
        fail("missing, oversized or invalid input file");
    *size = (size_t)info.st_size;
    unsigned char *data = calloc(*size + 1, 1);
    if (!data || fread(data, 1, *size, file) != *size || fclose(file))
        fail("cannot read input");
    return data;
}

static void check_keys(const cJSON *value, unsigned depth)
{
    if (depth > 64)
        fail("JSON nesting exceeds 64 levels");
    for (const cJSON *item = value->child; item; item = item->next) {
        if (cJSON_IsObject(value)) {
            for (const cJSON *next = item->next; next; next = next->next) {
                if (!strcmp(item->string, next->string))
                    fail("duplicate JSON object key");
            }
        }
        check_keys(item, depth + 1);
    }
}

static cJSON *read_json(const char *path)
{
    size_t size;
    unsigned char *raw = read_file(path, &size);
    cJSON *value = cJSON_ParseWithLengthOpts((char *)raw, size + 1, NULL, 1);
    free(raw);
    if (!value)
        fail("invalid JSON");
    check_keys(value, 0);
    return value;
}

static void put16(unsigned char *p, uint16_t n)
{
    p[0] = n; p[1] = n >> 8;
}

static void put32(unsigned char *p, uint32_t n)
{
    for (unsigned i = 0; i < 4; ++i)
        p[i] = n >> (i * 8);
}

static void put64(unsigned char *p, uint64_t n)
{
    for (unsigned i = 0; i < 8; ++i)
        p[i] = n >> (i * 8);
}

static uint32_t crc32(const unsigned char *p, size_t size)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < size; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320U : 0);
    }
    return ~crc;
}

static const char *text(const cJSON *json, const char *key)
{
    const cJSON *value = cJSON_GetObjectItemCaseSensitive(json, key);
    if (!cJSON_IsString(value))
        fail("missing identity string");
    return value->valuestring;
}

static uint64_t number(const cJSON *json, const char *key)
{
    const cJSON *value = cJSON_GetObjectItemCaseSensitive(json, key);
    if (!cJSON_IsNumber(value) || !isfinite(value->valuedouble) || value->valuedouble < 0 ||
        value->valuedouble > 9007199254740991.0 || value->valuedouble != (double)(uint64_t)value->valuedouble)
        fail("invalid identity integer");
    return (uint64_t)value->valuedouble;
}

static void hash(unsigned char *out, const char *input)
{
    if (strlen(input) != 64)
        fail("expected SHA256");
    for (unsigned i = 0; i < 32; ++i) {
        unsigned byte;
        char hex[3] = {input[i * 2], input[i * 2 + 1], 0};
        if (strspn(hex, "0123456789abcdef") != 2 || sscanf(hex, "%x", &byte) != 1)
            fail("invalid SHA256");
        out[i] = byte;
    }
}

static uint32_t fit_integer(const void *fit, const char *key)
{
    int size, node = fdt_path_offset(fit, "/configurations/conf-1");
    const fdt32_t *value = fdt_getprop(fit, node, key, &size);
    if (!value || size != 4)
        fail("missing FIT metadata property");
    return fdt32_to_cpu(*value);
}

static void metadata(char **args)
{
    cJSON *identity = read_json(args[0]);
    unsigned char record[4096] = {0};
    uint64_t version = number(identity, "version");
    if (!version || version > UINT32_MAX || strlen(text(identity, "tag")) >= 32)
        fail("invalid firmware version");
    put32(record, 0x46574d44); put16(record + 4, 1); put16(record + 6, 128);
    record[13] = 255; record[15] = 255; record[16] = 4;
    record[18] = 'I'; record[19] = 'D';
    for (unsigned i = 0; i < 3; ++i) {
        size_t size;
        unsigned char *fit = read_file(args[1 + i], &size);
        if (fdt_check_header(fit) || (size_t)fdt_totalsize(fit) > size)
            fail("invalid component FIT");
        uint32_t minutes = fit_integer(fit, "fw,build-time-minutes");
        record[21 + i * 12] = 1;
        put16(record + 22 + i * 12, minutes & 65535);
        put32(record + 24 + i * 12, fit_integer(fit, "fw,version"));
        put32(record + 28 + i * 12, fit_integer(fit, "fw,rollback-index"));
        put16(record + 112 + i * 2, minutes >> 16);
        free(fit);
    }
    record[56] = 4; record[58] = 1;
    put32(record + 60, version); put32(record + 108, 0x314d5442);
    put32(record + 128, 0x31444946); put32(record + 132, 1);
    memcpy(record + 136, text(identity, "tag"), strlen(text(identity, "tag")));
    hash(record + 168, text(identity, "firmware_id"));
    put64(record + 200, number(identity, "kernel_bytes"));
    put64(record + 208, number(identity, "rootfs_bytes"));
    hash(record + 216, text(identity, "kernel_sha256"));
    hash(record + 248, text(identity, "rootfs_sha256"));
    for (unsigned copy = 0; copy < 2; ++copy) {
        char path[4096];
        if (snprintf(path, sizeof(path), "%s/meta%u.bin", args[4], copy) >= (int)sizeof(path))
            fail("metadata output path too long");
        put32(record + 8, copy + 1);
        put32(record + 124, crc32(record, 124));
        put32(record + 4092, crc32(record, 4092));
        FILE *file = fopen(path, "wb");
        if (!file || fwrite(record, 1, sizeof(record), file) != sizeof(record) || fclose(file))
            fail("cannot write metadata");
    }
    cJSON_Delete(identity);
}

int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "check-json")) {
        cJSON_Delete(read_json(argv[2]));
    } else if (argc == 4 && !strcmp(argv[1], "exchange")) {
        if (access(argv[3], F_OK) == -1 && errno == ENOENT) {
            if (rename(argv[2], argv[3]))
                fail("cannot install release");
        } else if (renameat2(AT_FDCWD, argv[2], AT_FDCWD, argv[3], RENAME_EXCHANGE)) {
            fail("atomic release directory exchange failed");
        }
    } else if (argc == 4 && !strcmp(argv[1], "dtb-offset")) {
        size_t fit_size, dtb_size;
        unsigned char *fit = read_file(argv[2], &fit_size), *dtb = read_file(argv[3], &dtb_size);
        unsigned char *at = memmem(fit, fit_size, dtb, dtb_size);
        if (!dtb_size || !at || memmem(at + 1, fit_size - (size_t)(at + 1 - fit), dtb, dtb_size))
            fail("FIT must contain exactly one matching DTB");
        printf("%zu\n", (size_t)(at - fit));
        free(fit); free(dtb);
    } else if (argc == 7 && !strcmp(argv[1], "metadata")) {
        metadata(argv + 2);
    } else {
        fail("usage: check-json FILE | exchange NEW OLD | dtb-offset FIT DTB | metadata ID BOOT KERNEL ROOTFS OUTPUT");
    }
    return 0;
}
