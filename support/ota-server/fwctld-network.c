#define _DEFAULT_SOURCE
#include "fwctld-network.h"
#include <ifaddrs.h>
#include <netinet/in.h>
#include <string.h>

/* This gates local link/address readiness, not server reachability. HTTP errors
 * remain visible once the interface is ready. Never depend on ping or ip tools. */
int fwctld_network_ready(const char *interface)
{
    struct ifaddrs *addresses, *a;
    int ready = 0;
    if (getifaddrs(&addresses)) return 0;
    for (a = addresses; a; a = a->ifa_next) {
        if (!a->ifa_name || strcmp(a->ifa_name, interface) || !a->ifa_addr ||
            (a->ifa_flags & (IFF_UP | IFF_RUNNING)) != (IFF_UP | IFF_RUNNING))
            continue;
        if (a->ifa_addr->sa_family == AF_INET) {
            const struct sockaddr_in *v4 = (const void *)a->ifa_addr;
            ready = v4->sin_addr.s_addr != htonl(INADDR_ANY);
        } else if (a->ifa_addr->sa_family == AF_INET6) {
            const struct sockaddr_in6 *v6 = (const void *)a->ifa_addr;
            ready = !IN6_IS_ADDR_UNSPECIFIED(&v6->sin6_addr) &&
                    !IN6_IS_ADDR_LINKLOCAL(&v6->sin6_addr);
        }
        if (ready) break;
    }
    freeifaddrs(addresses);
    return ready;
}
