/*
 * Ethernet bring-up for the TE0715 on a TE0701 (TE-ETH-002, TC-24):
 * - the interface comes up with the static IPv4 address of prj.conf;
 * - the image waits up to LINK_TIMEOUT_MS for the carrier and prints one line,
 *   [ETH_BRINGUP_READY] carrier=on|off mac=... ipv4=... waited_ms=...;
 * - the network shell (net iface, net ping, net stats) and the kernel shell
 *   (kernel reboot cold, used by uboot_load.py) stay available.
 */

#include <zephyr/kernel.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/sys/printk.h>

#define LINK_TIMEOUT_MS 10000
#define LINK_POLL_MS    100

int main(void)
{
	struct net_if *iface = net_if_get_default();
	char mac[sizeof("xx:xx:xx:xx:xx:xx")] = "?";
	char ipv4[NET_IPV4_ADDR_LEN] = "none";
	uint32_t waited = 0U;

	if (iface == NULL) {
		printk("[ETH_BRINGUP_READY] carrier=off mac=? ipv4=none waited_ms=0 (no interface)\n");
		return 0;
	}

	while (!net_if_is_carrier_ok(iface) && waited < LINK_TIMEOUT_MS) {
		k_msleep(LINK_POLL_MS);
		waited += LINK_POLL_MS;
	}

	const struct net_linkaddr *link = net_if_get_link_addr(iface);

	if (link->len == 6U) {
		snprintk(mac, sizeof(mac), "%02x:%02x:%02x:%02x:%02x:%02x", link->addr[0],
			 link->addr[1], link->addr[2], link->addr[3], link->addr[4],
			 link->addr[5]);
	}

	const struct net_in_addr *addr = net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED);

	if (addr != NULL) {
		(void)net_addr_ntop(NET_AF_INET, addr, ipv4, sizeof(ipv4));
	}

	printk("[ETH_BRINGUP_READY] carrier=%s mac=%s ipv4=%s waited_ms=%u\n",
	       net_if_is_carrier_ok(iface) ? "on" : "off", mac, ipv4, waited);
	return 0;
}
