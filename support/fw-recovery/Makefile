CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Werror
fw-init: fw-init.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(LDFLAGS) -lcrypto -pthread -o $@
.PHONY: clean
clean:
	rm -f fw-init
