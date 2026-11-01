CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror

.PHONY: all test clean
all: ota-server ota-agent

ota-server: ota-server.c ota-publish.c ota-common.c ota-common.h
	$(CC) $(CPPFLAGS) $(CFLAGS) ota-server.c ota-publish.c ota-common.c $(LDFLAGS) -o $@

ota-agent: ota-agent.c ota-common.c ota-common.h
	$(CC) $(CPPFLAGS) $(CFLAGS) ota-agent.c ota-common.c $(LDFLAGS) -o $@

test: all
	sh ./tests/test-ota.sh

clean:
	rm -f ota-server ota-agent
