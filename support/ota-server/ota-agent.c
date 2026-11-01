#define _XOPEN_SOURCE 700
#include "ota-common.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void stop_agent(int sig)
{
    (void)sig;
    ota_stop = 1;
}

static int download(const char *url, const char *path, unsigned long long limit)
{
    char maximum[32];
    snprintf(maximum, sizeof(maximum), "%llu", limit);
    char *args[] = {"curl", "--disable", "--fail", "--silent", "--show-error",
        "--noproxy", "*", "--proto", "=http,https", "--connect-timeout", "10",
        "--max-time", "1800", "--speed-limit", "1024", "--speed-time", "30",
        "--max-filesize", maximum, "--output", (char *)path, "--url", (char *)url, NULL};
    if (ota_run(args, NULL, 0))
        return -1;
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    int rc = fsync(fd);
    close(fd);
    return rc;
}

static int poll_release(const char *server, const char *cache, const char *product, const char *layout)
{
    char temp[OTA_PATH], path[OTA_PATH], url[OTA_PATH], current[OTA_PATH], dest[OTA_PATH], name[64];
    struct release r, old;
    int rc = -1, unchanged = 0;
    if (ota_path(temp, cache, ".download-XXXXXX") || !mkdtemp(temp))
        return -1;
    if (ota_path(path, temp, "manifest") || ota_path(url, server, "latest") ||
        download(url, path, 2048) || ota_read(path, &r))
        goto done;
    if (strcmp(r.product, product) || strcmp(r.layout, layout)) {
        fprintf(stderr, "OTA product/layout mismatch\n");
        goto done;
    }
    if (ota_path(current, cache, "current"))
        goto done;
    if (!access(current, F_OK)) {
        if (ota_read(current, &old)) {
            fprintf(stderr, "Invalid local current record; inspect cache\n");
            goto done;
        }
        if (strcmp(old.product, product) || strcmp(old.layout, layout)) {
            fprintf(stderr, "Cache belongs to a different product/layout\n");
            goto done;
        }
        if (r.version < old.version) {
            fprintf(stderr, "Refusing older publication %llu (cached %llu)\n", r.version, old.version);
            goto done;
        }
        if (r.version == old.version) {
            for (int i = 0; i < 3; i++)
                if (strcmp(r.hash[i], old.hash[i]) || r.size[i] != old.size[i]) {
                    fprintf(stderr, "Published version changed unexpectedly\n");
                    goto done;
                }
            unchanged = 1;
        }
    }
    snprintf(name, sizeof(name), "%llu", r.version);
    if (ota_path(dest, cache, name))
        goto done;
    if (!access(dest, F_OK)) {
        if (ota_verify(dest, &r)) {
            fprintf(stderr, "Cached files damaged; remove affected version directory and retry\n");
            goto done;
        }
    } else {
        for (int i = 0; i < 3; i++) {
            char relative[96];
            snprintf(relative, sizeof(relative), "releases/%llu/%s", r.version, ota_files[i]);
            if (ota_path(url, server, relative) || ota_path(path, temp, ota_files[i]) ||
                download(url, path, r.size[i]))
                goto done;
        }
        if (ota_verify(temp, &r) || ota_sync_dir(temp) || rename(temp, dest) || ota_sync_dir(cache))
            goto done;
        printf("Downloaded and SHA256-verified publication %llu\n", r.version);
    }
    if (unchanged) {
        printf("Already cached publication %llu\n", r.version);
        rc = 0;
        goto done;
    }
    /* current means downloaded, NOT installed or boot-confirmed. */
    char record[OTA_PATH];
    snprintf(name, sizeof(name), ".current-%ld", (long)getpid());
    if (ota_path(record, cache, name))
        goto done;
    unlink(record);
    if (ota_write(record, &r) || rename(record, current) || ota_sync_dir(cache))
        goto done;
    printf("Ready: fwctl update %s/release.itb\n", dest);
    rc = 0;
done:
    for (int i = 0; i < 3; i++)
        if (!ota_path(path, temp, ota_files[i]))
            unlink(path);
    if (!ota_path(path, temp, "manifest"))
        unlink(path);
    rmdir(temp);
    return rc;
}

int main(int argc, char **argv)
{
    const char *server = NULL, *cache_arg = NULL, *product = NULL, *layout = NULL;
    unsigned long interval = 60;
    int once = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--once")) {
            once = 1;
            continue;
        }
        if (i + 1 == argc)
            goto usage;
        if (!strcmp(argv[i], "--server"))
            server = argv[++i];
        else if (!strcmp(argv[i], "--cache"))
            cache_arg = argv[++i];
        else if (!strcmp(argv[i], "--product"))
            product = argv[++i];
        else if (!strcmp(argv[i], "--layout"))
            layout = argv[++i];
        else if (!strcmp(argv[i], "--interval")) {
            char *end;
            errno = 0;
            interval = strtoul(argv[++i], &end, 10);
            if (errno || *end || interval < 1 || interval > 86400)
                goto usage;
        } else
            goto usage;
    }
    if (!server || !cache_arg || !product || !layout || !ota_identifier(product) ||
        !ota_identifier(layout) || (strncmp(server, "http://", 7) && strncmp(server, "https://", 8)) ||
        strchr(server, '?') || strchr(server, '#') || strlen(server) > 3000)
        goto usage;
    char base[OTA_PATH], cache[OTA_PATH];
    strcpy(base, server);
    size_t length = strlen(base);
    while (length && base[length - 1] == '/')
        base[--length] = 0;
    if (ota_mkdir(cache_arg) || !realpath(cache_arg, cache)) {
        perror("OTA cache (create its parent first)");
        return 1;
    }
    int lock = ota_lock(cache);
    if (lock < 0) {
        fprintf(stderr, "Another agent is active or cache lock unavailable\n");
        return 1;
    }
    struct sigaction action = {.sa_handler = stop_agent};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    int rc;
    do {
        rc = poll_release(base, cache, product, layout);
        if (rc)
            fprintf(stderr, "OTA check/download failed; cached current remains unchanged\n");
        fflush(stdout);
        if (once || ota_stop)
            break;
        struct timespec delay = {.tv_sec = (time_t)interval};
        while (nanosleep(&delay, &delay) && errno == EINTR && !ota_stop)
            ;
    } while (!ota_stop);
    close(lock);
    return ota_stop ? 0 : (rc ? 1 : 0);
usage:
    fprintf(stderr, "Usage: ota-agent --server URL --cache DIR --product ID --layout ID "
            "[--interval SECONDS] [--once]\n");
    return 1;
}
