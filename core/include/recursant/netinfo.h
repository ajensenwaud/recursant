#ifndef RECURSANT_NETINFO_H
#define RECURSANT_NETINFO_H
#include <stdbool.h>
#include <stddef.h>

/* Tailscale recognition. A tailnet address is IPv4 in 100.64.0.0/10 (the
 * CGNAT range Tailscale assigns) or a MagicDNS name ending in ".ts.net". */
bool rc_tailnet_address(const char *host);
/* This host's tailnet IPv4: the first 100.64.0.0/10 address, preferring an
 * interface named tailscale*. false when none is up. */
bool rc_tailnet_ipv4(char *addr, size_t addr_size, char *ifname, size_t ifname_size);
/* listen.host as written in the config -> literal IPv4 to bind:
 * "localhost" -> 127.0.0.1, "any" -> 0.0.0.0, "tailnet" -> this host's
 * tailnet address, an IPv4 literal -> itself. false when unresolvable. */
bool rc_listen_resolve(const char *host, char *addr, size_t addr_size);
#endif
