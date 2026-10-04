#define _DEFAULT_SOURCE
#include "recursant/netinfo.h"
#include <arpa/inet.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

static bool cgnat(uint32_t host_order) { return (host_order & 0xFFC00000u) == 0x64400000u; } /* 100.64.0.0/10 */

bool rc_tailnet_address(const char *host) {
    if (!host || !*host) return false;
    struct in_addr a;
    if (inet_pton(AF_INET, host, &a) == 1) return cgnat(ntohl(a.s_addr));
    size_t n = strlen(host);
    if (n && host[n - 1] == '.') n--; /* fully qualified form */
    return n > 7 && !strncasecmp(host + n - 7, ".ts.net", 7);
}

bool rc_tailnet_ipv4(char *addr, size_t addr_size, char *ifname, size_t ifname_size) {
    struct ifaddrs *list = NULL;
    if (getifaddrs(&list) != 0) return false;
    const struct ifaddrs *best = NULL;
    for (const struct ifaddrs *i = list; i; i = i->ifa_next) {
        if (!i->ifa_addr || i->ifa_addr->sa_family != AF_INET || !(i->ifa_flags & IFF_UP)) continue;
        const struct sockaddr_in *sin = (const struct sockaddr_in *)(const void *)i->ifa_addr;
        if (!cgnat(ntohl(sin->sin_addr.s_addr))) continue;
        if (!best || (!strncmp(i->ifa_name, "tailscale", 9) && strncmp(best->ifa_name, "tailscale", 9))) best = i;
    }
    bool ok = false;
    if (best) {
        const struct sockaddr_in *sin = (const struct sockaddr_in *)(const void *)best->ifa_addr;
        ok = inet_ntop(AF_INET, &sin->sin_addr, addr, (socklen_t)addr_size) != NULL;
        if (ok && ifname && ifname_size) snprintf(ifname, ifname_size, "%s", best->ifa_name);
    }
    freeifaddrs(list);
    return ok;
}

bool rc_listen_resolve(const char *host, char *addr, size_t addr_size) {
    if (!host) return false;
    const char *literal = !strcmp(host, "localhost") ? "127.0.0.1" : !strcmp(host, "any") ? "0.0.0.0" : NULL;
    if (!strcmp(host, "tailnet")) return rc_tailnet_ipv4(addr, addr_size, NULL, 0);
    if (!literal) literal = host;
    struct in_addr a;
    if (inet_pton(AF_INET, literal, &a) != 1) return false;
    return snprintf(addr, addr_size, "%s", literal) < (int)addr_size;
}
