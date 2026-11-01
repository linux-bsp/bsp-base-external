/* Minimal host-side HTTP transport for fwctl FIT releases. */
#define _POSIX_C_SOURCE 200809L
#include "ota-common.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;
static const char *server_directory;

static void stop_server(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static int send_all(int client, const void *data, size_t length)
{
    const char *cursor = data;
    while (length && running) {
        ssize_t count = send(client, cursor, length, 0);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            return -1;
        cursor += count;
        length -= (size_t)count;
    }
    return length ? -1 : 0;
}

static int headers(int client, int status, const char *reason,
                   const char *type, uintmax_t length)
{
    char buffer[512];
    int count = snprintf(buffer, sizeof(buffer),
        "HTTP/1.1 %d %s\r\nContent-Type: %s\r\n"
        "Content-Length: %ju\r\nConnection: close\r\n"
        "Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
        "Allow: GET, HEAD\r\n\r\n", status, reason, type, length);
    if (count < 0 || (size_t)count >= sizeof(buffer))
        return -1;
    return send_all(client, buffer, (size_t)count);
}

static void text_response(int client, int status, const char *reason,
                          const char *body, bool head)
{
    if (!headers(client, status, reason, "text/plain; charset=utf-8", strlen(body)) && !head)
        (void)send_all(client, body, strlen(body));
}

static int open_artifact(int root, const char *name, struct stat *st)
{
    int fd = openat(root, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0)
        return -1;
    if (fstat(fd, st) || !S_ISREG(st->st_mode) || st->st_size <= 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static void index_page(int client, int root, bool head)
{
    char body[4096];
    const char *prefix =
        "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>BSP OTA Server</title><style>"
        "body{font:16px system-ui;max-width:760px;margin:60px auto;padding:0 24px;line-height:1.7}"
        "table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}"
        "code{background:#f1f3f5;padding:3px 6px}a{color:#1458b8}</style>"
        "<h1>BSP OTA Server</h1><p>fwctl 固件下载服务</p>"
        "<table><tr><th>文件</th><th>大小（字节）</th></tr>";
    size_t used = strlen(prefix);
    memcpy(body, prefix, used + 1);
    (void)root;
    struct release r;
    char latest[OTA_PATH];
    if (!ota_path(latest, server_directory, "latest") && !ota_read(latest, &r)) {
        for (int i = 0; i < 3; i++) {
            int count = snprintf(body + used, sizeof(body) - used,
                "<tr><td><a href=\"/releases/%llu/%s\">%s</a></td><td>%llu</td></tr>",
                r.version, ota_files[i], ota_files[i], r.size[i]);
            if (count < 0 || (size_t)count >= sizeof(body) - used)
                return;
            used += (size_t)count;
        }
        int count = snprintf(body + used, sizeof(body) - used,
            "</table><p>%s / %s：发布编号 %llu</p>", r.product, r.layout, r.version);
        if (count < 0 || (size_t)count >= sizeof(body) - used)
            return;
        used += (size_t)count;
    } else {
        const char *empty = "</table><p>尚未发布版本。</p>";
        memcpy(body + used, empty, strlen(empty) + 1);
        used += strlen(empty);
    }
    const char *suffix =
        "<p><a href=\"/latest\">查看最新版本清单</a></p>"
        "<p>设备运行 ota-agent，定期检查发布版本并下载到本地缓存。</p>"
        "<p>下载校验完成后，由 fwctl 安装；此服务不会自动刷写或重启设备。</p></html>";
    if (strlen(suffix) >= sizeof(body) - used)
        return;
    memcpy(body + used, suffix, strlen(suffix) + 1);
    used += strlen(suffix);
    if (!headers(client, 200, "OK", "text/html; charset=utf-8", used) && !head)
        (void)send_all(client, body, used);
}

static void handle_client(int client, int root)
{
    char request[8192], method[16], path[2048], protocol[16], extra;
    size_t used = 0;
    bool complete = false;
    struct timeval timeout = {.tv_sec = 15, .tv_usec = 0};
    (void)setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    while (used < sizeof(request) - 1 && running) {
        ssize_t count = recv(client, request + used, sizeof(request) - 1 - used, 0);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            return;
        if (memchr(request + used, '\0', (size_t)count))
            return;
        used += (size_t)count;
        request[used] = '\0';
        if (strstr(request, "\r\n\r\n")) {
            complete = true;
            break;
        }
    }
    if (!complete) {
        text_response(client, 431, "Request Header Fields Too Large", "Headers too large\n", false);
        return;
    }
    char *line_end = strstr(request, "\r\n");
    *line_end = '\0';
    if (sscanf(request, "%15s %2047s %15s %c", method, path, protocol, &extra) != 3 ||
        (strcmp(protocol, "HTTP/1.0") && strcmp(protocol, "HTTP/1.1"))) {
        text_response(client, 400, "Bad Request", "Invalid request\n", false);
        return;
    }
    bool head = !strcmp(method, "HEAD");
    if (strcmp(method, "GET") && !head) {
        text_response(client, 405, "Method Not Allowed", "Use GET or HEAD\n", false);
        return;
    }
    char *query = strchr(path, '?');
    if (query)
        *query = '\0';
    if (!strcmp(path, "/")) {
        index_page(client, root, head);
        return;
    }
    if (!strcmp(path, "/healthz")) {
        text_response(client, 200, "OK", "ok\n", head);
        return;
    }
    int artifact_root = -1;
    const char *name = NULL;
    if (!strcmp(path, "/latest")) {
        name = "latest";
        artifact_root = dup(root);
    } else {
        unsigned long long version;
        char filename[32], trailing, canonical[128], number[32];
        if (sscanf(path, "/releases/%llu/%31s%c", &version, filename, &trailing) == 2 &&
            version && version <= 2147483647) {
            snprintf(canonical, sizeof(canonical), "/releases/%llu/%s", version, filename);
            if (!strcmp(path, canonical)) {
                for (int i = 0; i < 3; i++)
                    if (!strcmp(filename, ota_files[i]))
                        name = ota_files[i];
                if (!strcmp(filename, "manifest"))
                    name = "manifest";
            }
            if (name) {
                int releases = openat(root, "releases", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
                if (releases >= 0) {
                    snprintf(number, sizeof(number), "%llu", version);
                    artifact_root = openat(releases, number, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
                    close(releases);
                }
            }
        }
    }
    struct stat st;
    int fd = name && artifact_root >= 0 ? open_artifact(artifact_root, name, &st) : -1;
    if (artifact_root >= 0)
        close(artifact_root);
    if (fd < 0) {
        text_response(client, 404, "Not Found", "Artifact unavailable\n", head);
        return;
    }
    if (!headers(client, 200, "OK", "application/octet-stream", (uintmax_t)st.st_size) && !head) {
        char buffer[65536];
        off_t remaining = st.st_size;
        while (remaining > 0 && running) {
            size_t wanted = remaining < (off_t)sizeof(buffer) ? (size_t)remaining : sizeof(buffer);
            ssize_t count = read(fd, buffer, wanted);
            if (count < 0 && errno == EINTR)
                continue;
            if (count <= 0 || send_all(client, buffer, (size_t)count))
                break;
            remaining -= count;
        }
    }
    close(fd);
}

static void usage(const char *program)
{
    printf("Usage: %s --root RELEASE_DIR [--bind IPV4] [--port PORT]\n"
           "Defaults: --bind 127.0.0.1 --port 8080\n"
           "Publish first with: ota-server publish --root DIR --source RELEASE_DIR "
           "--version NUMBER --product ID --layout ID\n", program);
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "publish"))
        return ota_publish(argc, argv);
    const char *directory = NULL, *bind_address = "127.0.0.1";
    long port = 8080;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--help")) {
            usage(argv[0]);
            return 0;
        }
        if (i + 1 >= argc) {
            usage(argv[0]);
            return 1;
        }
        if (!strcmp(argv[i], "--root"))
            directory = argv[++i];
        else if (!strcmp(argv[i], "--bind"))
            bind_address = argv[++i];
        else if (!strcmp(argv[i], "--port")) {
            char *end;
            errno = 0;
            port = strtol(argv[++i], &end, 10);
            if (errno || !argv[i][0] || *end || port < 0 || port > 65535) {
                fprintf(stderr, "Invalid port\n");
                return 1;
            }
        } else {
            usage(argv[0]);
            return 1;
        }
    }
    if (!directory) {
        usage(argv[0]);
        return 1;
    }
    int root = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (root < 0) {
        perror(directory);
        return 1;
    }
    server_directory = directory;
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons((unsigned short)port)};
    if (inet_pton(AF_INET, bind_address, &address.sin_addr) != 1) {
        fprintf(stderr, "--bind must be an IPv4 address\n");
        close(root);
        return 1;
    }
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) {
        perror("socket");
        close(root);
        return 1;
    }
    int enabled = 1;
    (void)setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) || listen(listener, 16)) {
        perror("listen");
        close(listener);
        close(root);
        return 1;
    }
    struct sigaction action = {.sa_handler = stop_server};
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    socklen_t size = sizeof(address);
    (void)getsockname(listener, (struct sockaddr *)&address, &size);
    printf("OTA server: http://%s:%u/ root=%s\n", bind_address, ntohs(address.sin_port), directory);
    fflush(stdout);
    while (running) {
        int client = accept(listener, NULL, NULL);
        if (client < 0) {
            if (errno == EINTR)
                continue;
            perror("accept");
            break;
        }
        handle_client(client, root);
        close(client);
    }
    close(listener);
    close(root);
    return 0;
}
