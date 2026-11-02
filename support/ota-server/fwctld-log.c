#define _POSIX_C_SOURCE 200809L
#include "ota-common.h"
#include "fwctld-log.h"
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int console_fd = -1;

void fwctld_log_init(const char *console)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    if (console && *console) {
        console_fd = open(console, O_WRONLY | O_APPEND | O_NONBLOCK | O_NOCTTY | O_CLOEXEC);
        if (console_fd < 0)
            fprintf(stderr, "fwctld: cannot open console %s: %s; file logging continues\n",
                console, strerror(errno));
    }
}

void fwctld_log(const char *format, ...)
{
    char message[2048];
    strcpy(message, "fwctld: ");
    size_t prefix = strlen(message);
    va_list args;
    va_start(args, format);
    vsnprintf(message + prefix, sizeof(message) - prefix - 1, format, args);
    va_end(args);
    size_t n = strlen(message);
    if (!n || message[n - 1] != '\n') message[n++] = '\n';
    message[n] = 0;
    fputs(message, stdout);
    fflush(stdout);
    /* A blocked/disconnected serial console must not stall an update. */
    if (console_fd >= 0) {
        ssize_t sent;
        do { sent = write(console_fd, message, n); } while (sent < 0 && errno == EINTR);
        (void)sent; /* Best effort; the complete message stays in the log file. */
    }
}

void fwctld_log_stage(const char *stage)
{
    fwctld_log("================ OTA / %s ================", stage);
}

/* Drain fwctl stdout AND stderr while it runs, instead of buffering until exit. */
int fwctld_run_logged(char *const argv[])
{
    int pipes[2], status, failed = 0;
    if (pipe(pipes)) return -1;
    pid_t pid = fork();
    if (!pid) {
        close(pipes[0]);
        if (dup2(pipes[1], STDOUT_FILENO) < 0 || dup2(pipes[1], STDERR_FILENO) < 0) _exit(126);
        close(pipes[1]);
        execvp(argv[0], argv);
        _exit(127);
    }
    close(pipes[1]);
    if (pid < 0) { close(pipes[0]); return -1; }
    char buffer[1024];
    for (;;) {
        ssize_t n = read(pipes[0], buffer, sizeof(buffer) - 1);
        if (n < 0 && errno == EINTR) {
            if (ota_stop) kill(pid, SIGTERM);
            continue;
        }
        if (n <= 0) { failed = n < 0; break; }
        buffer[n] = 0;
        fwctld_log("%s", buffer);
    }
    close(pipes[0]);
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) return -1;
        if (ota_stop) kill(pid, SIGTERM);
    }
    return !failed && WIFEXITED(status) && !ota_stop ? WEXITSTATUS(status) : -1;
}
