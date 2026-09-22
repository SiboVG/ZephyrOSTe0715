/*
 * CSP node on the TE0715 CAN1 (TE0701 Pmod J1), set up like the Linux
 * fprime-csp-libparam SocketCAN transport: CSP v2, the CAN interface as the
 * default route, and the standard CSP services (ping, ident, ...) on all
 * ports. It also pings CONFIG_APP_CSP_PEER periodically.
 */

#include <csp/csp.h>
#include <csp/drivers/can_zephyr.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#define ROUTER_STACK_SIZE 4096
#define ROUTER_PRIORITY   5

static const struct device *const can_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_canbus));

static void router_thread(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	while (true) {
		(void)csp_route_work();
	}
}

K_THREAD_DEFINE(router, ROUTER_STACK_SIZE, router_thread, NULL, NULL, NULL, ROUTER_PRIORITY, 0,
		SYS_FOREVER_MS);

int main(void)
{
	csp_iface_t *iface = NULL;
	uint32_t pings = 0;
	uint32_t replies = 0;
	int err;

	if (!device_is_ready(can_dev)) {
		printk("CAN device %s not ready\n", can_dev->name);
		return 0;
	}

	csp_conf.version = 2;
	csp_conf.hostname = "te0715";
	csp_conf.model = "TE0715-05-71I33-L";
	csp_conf.revision = "zephyr";
	csp_init();

	err = csp_can_open_and_add_interface(can_dev, "CAN", CONFIG_APP_CSP_NODE,
					     DT_PROP(DT_CHOSEN(zephyr_canbus), bitrate),
					     CONFIG_APP_CSP_NODE, 0x3FFF, &iface);
	if (err != CSP_ERR_NONE) {
		printk("failed to add CSP CAN interface (err %d)\n", err);
		return 0;
	}
	iface->netmask = CONFIG_APP_CSP_NETMASK;
	iface->is_default = 1;

	err = csp_bind_callback(csp_service_handler, CSP_ANY);
	if (err != CSP_ERR_NONE) {
		printk("failed to bind CSP service handler (err %d)\n", err);
		return 0;
	}

	k_thread_start(router);

	printk("CSP node %d/%d on %s, pinging %d every %d ms\n", CONFIG_APP_CSP_NODE,
	       CONFIG_APP_CSP_NETMASK, can_dev->name, CONFIG_APP_CSP_PEER,
	       CONFIG_APP_CSP_PING_PERIOD_MS);

	while (CONFIG_APP_CSP_PEER != 0) {
		int rtt = csp_ping(CONFIG_APP_CSP_PEER, 1000, 32, CSP_O_NONE);

		pings++;
		if (rtt >= 0) {
			replies++;
		}
		printk("PING %d: %s %d ms (%u/%u replies)\n", CONFIG_APP_CSP_PEER,
		       rtt >= 0 ? "reply in" : "no reply, err", rtt, replies, pings);

		k_msleep(CONFIG_APP_CSP_PING_PERIOD_MS);
	}

	return 0;
}
