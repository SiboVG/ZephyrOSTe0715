/*
 * Serial shell commands for the TE0715 bench server:
 *   bench start [node] [prefix]   start now, optionally on another node
 *   bench info                    show the CSP configuration
 *   csp ping <node> [bytes] [timeout_ms] [--nocrc]
 *   param get <node> <id> <type> [index]
 *   param set <node> <id> <type> <value> [index] --confirm
 *
 * <type> is one of u8 i8 u16 i16 u32 i32 u64 i64 float double. Remote
 * parameters are accessed with libparam protocol version 2 on port 10.
 *
 * At boot the node and prefix come from te0715.txt on the SD card, if
 * boot/boot.cmd found one (see bench_config.h), else from Kconfig.
 *
 * It also serves, next to the F Prime component's bench_integer (200):
 * - led_d4 (201, u8): the green user LED D4 on MIO7, 1 on / 0 off;
 * - libparam's list service (port 12, via vmem_server_loop), so csh can
 *   `list download` this node's parameters.
 */

#include <errno.h>
#include <string.h>

#include <csp/csp.h>
#include <param/param.h>
#include <param/param_client.h>
#include <param/param_list.h>
#include <vmem/vmem_server.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/device_mmio.h>

#include "bench_config.h"
#include "bench_start.h"
#include "bench_value.h"

#define PARAM_VERSION    2
#define PARAM_TIMEOUT_MS 1000
#define PARAM_MAX_INDEX  127

static K_SEM_DEFINE(start_sem, 0, 1);
static uint16_t start_node = CONFIG_APP_CSP_NODE;
static uint8_t start_prefix = CONFIG_APP_CSP_NETMASK;
static const char *start_source = "default";
static bool started;

/* led_d4: the green user LED D4, as a libparam parameter */
#define LED_PARAM_ID 201

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static uint8_t led_value;
static uint16_t local_node; /* 0: a parameter of this node */
static csp_timestamp_t led_timestamp;

static void led_param_changed(param_t *param, int offset)
{
	ARG_UNUSED(offset);

	(void)gpio_pin_set_dt(&led, led_value != 0U);
	printk("PARAM %s = %u: LED D4 %s\n", param->name, led_value, led_value ? "on" : "off");
}

static param_t led_param = {
	.id = LED_PARAM_ID,
	.node = &local_node,
	.type = PARAM_TYPE_UINT8,
	.mask = PM_CONF,
	.name = "led_d4",
	.unit = "",
	.docstr = "Green user LED D4 (MIO7): 1 on, 0 off",
	.addr = &led_value,
	.array_size = 1,
	.array_step = sizeof(uint8_t),
	.timestamp = &led_timestamp,
	.callback = led_param_changed,
};

/* libparam's list and vmem services (ports 12 and 13); no vmem areas are registered */
static void param_server_thread(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	vmem_server_loop(NULL);
}

K_THREAD_DEFINE(param_server, 4096, param_server_thread, NULL, NULL, NULL, 10, 0, SYS_FOREVER_MS);

int bench_start_services(void)
{
	int err;

	if (!gpio_is_ready_dt(&led)) {
		return -ENODEV;
	}
	err = gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	if (err != 0) {
		return err;
	}
	err = param_list_add(&led_param);
	if (err < 0) {
		return err;
	}
	k_thread_name_set(param_server, "param_server");
	k_thread_start(param_server);
	return 0;
}

/*
 * Apply te0715.txt, which boot.cmd left in RAM, and clear the header: RAM
 * keeps its contents over a reset, and a later JTAG load (which does not run
 * boot.cmd) must not pick up an old file.
 */
static void load_boot_config(void)
{
	mm_reg_t area;
	struct bench_config cfg;
	int bad_line;
	int err;

	device_map(&area, CONFIG_APP_BOOT_CONFIG_ADDR, BENCH_CONFIG_AREA_SIZE, K_MEM_CACHE_NONE);
	err = bench_config_from_area((const uint8_t *)area, BENCH_CONFIG_AREA_SIZE, &cfg,
				     &bad_line);
	sys_write32(0, area);
	k_mem_unmap_phys_bare((uint8_t *)area, BENCH_CONFIG_AREA_SIZE);

	if (err == -ENOENT) {
		return;
	}
	if (err != 0) {
		if (bad_line > 0) {
			printk("*** te0715.txt: line %d not understood; using the defaults ***\n",
			       bad_line);
		} else {
			printk("*** te0715.txt: bad header; using the defaults ***\n");
		}
		start_source = "default; te0715.txt refused";
		return;
	}
	if (cfg.has_node) {
		start_node = cfg.node;
	}
	if (cfg.has_prefix) {
		start_prefix = cfg.prefix;
	}
	start_source = "te0715.txt";
}

void bench_wait_for_start(uint16_t *node, uint8_t *prefix)
{
	load_boot_config();
	printk("\n*** CSP bench server: node %u/%u (%s). Type `bench start [node] [prefix]` "
	       "within %d s to start (on another node), or wait. ***\n\n",
	       start_node, start_prefix, start_source, CONFIG_APP_START_WINDOW_S);
	(void)k_sem_take(&start_sem, K_SECONDS(CONFIG_APP_START_WINDOW_S));
	started = true;
	*node = start_node;
	*prefix = start_prefix;
}

static int parse_ulong(const struct shell *sh, const char *arg, unsigned long max,
		       unsigned long *out)
{
	int err = bench_value_parse_ulong(arg, max, out);

	if (err != 0) {
		shell_error(sh, "invalid number '%s' (max %lu)", arg, max);
	}
	return err;
}

static int cmd_bench_start(const struct shell *sh, size_t argc, char **argv)
{
	unsigned long v;

	if (started) {
		shell_error(sh, "already started on node %u/%u; reset the board to change it",
			    start_node, start_prefix);
		return -EALREADY;
	}
	if (argc > 1) {
		if (parse_ulong(sh, argv[1], 16381, &v) != 0 || v == 0) {
			return -EINVAL;
		}
		start_node = v;
	}
	if (argc > 2) {
		if (parse_ulong(sh, argv[2], 13, &v) != 0) {
			return -EINVAL;
		}
		start_prefix = v;
	}
	if (argc > 1) {
		start_source = "bench start";
	}
	shell_print(sh, "starting on node %u/%u", start_node, start_prefix);
	k_sem_give(&start_sem);
	return 0;
}

static int cmd_bench_info(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "node %u/%u (%s, %s), libparam server port 10: parameter 200 (u32)",
		    start_node, start_prefix, start_source,
		    started ? "started" : "waiting for start");
	shell_print(sh, "parameter %d led_d4 (u8) = %u: LED D4 %s; parameter list served on port 12",
		    LED_PARAM_ID, led_value, led_value ? "on" : "off");
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_bench,
	SHELL_CMD_ARG(start, NULL, "start [node] [prefix]", cmd_bench_start, 1, 2),
	SHELL_CMD_ARG(info, NULL, "show the CSP configuration", cmd_bench_info, 1, 0),
	SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(bench, &sub_bench, "CSP/libparam bench server", NULL);

static bool require_started(const struct shell *sh)
{
	if (!started) {
		shell_error(sh, "CSP is not started yet (bench start)");
	}
	return started;
}

static int cmd_csp_ping(const struct shell *sh, size_t argc, char **argv)
{
	unsigned long node;
	unsigned long bytes = 32;
	unsigned long timeout = 1000;
	/* CRC32 like libcsp's own services and csh; peers may require it (CSP_SO_CRC32REQ) */
	uint32_t opts = CSP_O_CRC32;
	int rtt;

	if (strcmp(argv[argc - 1], "--nocrc") == 0) {
		opts = CSP_O_NONE;
		argc--;
	}

	if (!require_started(sh) || parse_ulong(sh, argv[1], 16381, &node) != 0 ||
	    (argc > 2 && parse_ulong(sh, argv[2], 128, &bytes) != 0) ||
	    (argc > 3 && parse_ulong(sh, argv[3], 60000, &timeout) != 0)) {
		return -EINVAL;
	}

	rtt = csp_ping(node, timeout, bytes, opts);
	if (rtt < 0) {
		shell_error(sh, "ping %lu: no reply within %lu ms", node, timeout);
		return -ETIMEDOUT;
	}
	shell_print(sh, "ping %lu: reply in %d ms (%lu bytes)", node, rtt, bytes);
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_csp,
	SHELL_CMD_ARG(ping, NULL, "ping <node> [bytes] [timeout_ms] [--nocrc]", cmd_csp_ping, 2, 3),
	SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(csp, &sub_csp, "CSP tools", NULL);

/* A shell type (bench_value.h) with its libparam type */
struct param_type_info {
	const struct bench_value_type *value;
	param_type_e type;
	uint8_t size;
};

static param_type_e libparam_type(const struct bench_value_type *v)
{
	switch (v->kind) {
	case BENCH_VALUE_FLOAT:
		return (v->size == 4) ? PARAM_TYPE_FLOAT : PARAM_TYPE_DOUBLE;
	case BENCH_VALUE_SIGNED:
		return (v->size == 1)   ? PARAM_TYPE_INT8
		       : (v->size == 2) ? PARAM_TYPE_INT16
		       : (v->size == 4) ? PARAM_TYPE_INT32
					: PARAM_TYPE_INT64;
	case BENCH_VALUE_UNSIGNED:
	default:
		return (v->size == 1)   ? PARAM_TYPE_UINT8
		       : (v->size == 2) ? PARAM_TYPE_UINT16
		       : (v->size == 4) ? PARAM_TYPE_UINT32
					: PARAM_TYPE_UINT64;
	}
}

/* A remote parameter descriptor for one access */
struct remote_param {
	param_t param;
	uint16_t node;
	csp_timestamp_t timestamp;
	uint8_t storage[(PARAM_MAX_INDEX + 1) * 8] __aligned(8);
};

static struct param_type_info type_info; /* shell commands run one at a time */

static const struct param_type_info *find_type(const struct shell *sh, const char *name)
{
	const struct bench_value_type *v = bench_value_type_find(name);

	if (v == NULL) {
		shell_error(sh, "unknown type '%s' (u8 i8 u16 i16 u32 i32 u64 i64 float double)",
			    name);
		return NULL;
	}
	type_info.value = v;
	type_info.type = libparam_type(v);
	type_info.size = v->size;
	return &type_info;
}

static void remote_param_init(struct remote_param *rp, const struct param_type_info *t,
			      uint16_t node, uint16_t id, unsigned int index)
{
	memset(rp, 0, sizeof(*rp));
	rp->node = node;
	rp->param.id = id;
	rp->param.node = &rp->node;
	rp->param.type = t->type;
	rp->param.mask = PM_REMOTE;
	rp->param.name = "remote";
	rp->param.addr = rp->storage;
	rp->param.array_size = index + 1;
	rp->param.array_step = t->size;
	rp->param.timestamp = &rp->timestamp;
}

static void print_value(const struct shell *sh, const char *what, const struct remote_param *rp,
			const struct param_type_info *t, unsigned int index)
{
	const void *p = &rp->storage[index * t->size];

	switch (t->type) {
	case PARAM_TYPE_UINT8:  shell_print(sh, "%s %u", what, *(const uint8_t *)p); break;
	case PARAM_TYPE_INT8:   shell_print(sh, "%s %d", what, *(const int8_t *)p); break;
	case PARAM_TYPE_UINT16: shell_print(sh, "%s %u", what, *(const uint16_t *)p); break;
	case PARAM_TYPE_INT16:  shell_print(sh, "%s %d", what, *(const int16_t *)p); break;
	case PARAM_TYPE_UINT32:
		shell_print(sh, "%s %u (0x%08x)", what, *(const uint32_t *)p, *(const uint32_t *)p);
		break;
	case PARAM_TYPE_INT32:  shell_print(sh, "%s %d", what, *(const int32_t *)p); break;
	case PARAM_TYPE_UINT64:
		shell_print(sh, "%s %llu", what, (unsigned long long)*(const uint64_t *)p);
		break;
	case PARAM_TYPE_INT64:
		shell_print(sh, "%s %lld", what, (long long)*(const int64_t *)p);
		break;
	case PARAM_TYPE_FLOAT:  shell_print(sh, "%s %g", what, (double)*(const float *)p); break;
	case PARAM_TYPE_DOUBLE: shell_print(sh, "%s %g", what, *(const double *)p); break;
	default: break;
	}
}

static int parse_param_args(const struct shell *sh, char **argv, unsigned long *node,
			    unsigned long *id, const struct param_type_info **t)
{
	if (!require_started(sh) || parse_ulong(sh, argv[1], 16381, node) != 0 ||
	    parse_ulong(sh, argv[2], 65535, id) != 0) {
		return -EINVAL;
	}
	*t = find_type(sh, argv[3]);
	return (*t == NULL) ? -EINVAL : 0;
}

static struct remote_param rp; /* shell commands run one at a time */

/*
 * libparam stores replies only in descriptors that are in its parameter list,
 * so the descriptor is registered for the duration of one command.
 */
static int remote_param_register(const struct shell *sh)
{
	int ret = param_list_add(&rp.param);

	if (ret != 0) {
		shell_error(sh, "node %u parameter %u is already known here (this node's own "
			    "parameter?); not accessing it remotely", rp.node, rp.param.id);
		return -EEXIST;
	}
	return 0;
}

static void remote_param_unregister(void)
{
	param_list_remove_specific(&rp.param, 0, 0);
}

static int cmd_param_get(const struct shell *sh, size_t argc, char **argv)
{
	const struct param_type_info *t;
	unsigned long node, id, index = 0;
	int err;

	if (parse_param_args(sh, argv, &node, &id, &t) != 0 ||
	    (argc > 4 && parse_ulong(sh, argv[4], PARAM_MAX_INDEX, &index) != 0)) {
		return -EINVAL;
	}

	remote_param_init(&rp, t, node, id, index);
	if (remote_param_register(sh) != 0) {
		return -EEXIST;
	}
	err = param_pull_single(&rp.param, index, CSP_PRIO_NORM, 0, node, PARAM_TIMEOUT_MS,
				PARAM_VERSION);
	remote_param_unregister();
	if (err != 0) {
		shell_error(sh, "param get %lu:%lu[%lu] failed (%d)", node, id, index, err);
		return -EIO;
	}
	print_value(sh, "value", &rp, t, index);
	return 0;
}

static int parse_value(const struct shell *sh, const struct param_type_info *t, const char *arg,
		       uint8_t *out)
{
	int err = bench_value_parse(t->value, arg, out);

	if (err == -ERANGE) {
		shell_error(sh, "%s value '%s' out of range; nothing written", t->value->name, arg);
	} else if (err != 0) {
		shell_error(sh, "invalid %s value '%s'", t->value->name, arg);
	}
	return err;
}

static int cmd_param_set(const struct shell *sh, size_t argc, char **argv)
{
	const struct param_type_info *t;
	unsigned long node, id, index = 0;
	uint8_t value[BENCH_VALUE_MAX_SIZE] = {0};
	bool confirmed = strcmp(argv[argc - 1], "--confirm") == 0;
	size_t nargs = confirmed ? argc - 1 : argc;
	int err;

	if (!confirmed) {
		shell_error(sh, "writes change the remote node: repeat the command with --confirm");
		return -EPERM;
	}
	if (nargs < 5 || parse_param_args(sh, argv, &node, &id, &t) != 0 ||
	    parse_value(sh, t, argv[4], value) != 0 ||
	    (nargs > 5 && parse_ulong(sh, argv[5], PARAM_MAX_INDEX, &index) != 0)) {
		return -EINVAL;
	}

	remote_param_init(&rp, t, node, id, index);
	if (remote_param_register(sh) != 0) {
		return -EEXIST;
	}
	err = param_push_single(&rp.param, index, CSP_PRIO_NORM, value, 0, node, PARAM_TIMEOUT_MS,
				PARAM_VERSION, false);
	if (err != 0) {
		remote_param_unregister();
		shell_error(sh, "param set %lu:%lu[%lu] failed (%d)", node, id, index, err);
		return -EIO;
	}

	/* Read back with a separate request */
	memset(rp.storage, 0, sizeof(rp.storage));
	err = param_pull_single(&rp.param, index, CSP_PRIO_NORM, 0, node, PARAM_TIMEOUT_MS,
				PARAM_VERSION);
	remote_param_unregister();
	if (err != 0) {
		shell_error(sh, "written, but read-back failed (%d)", err);
		return -EIO;
	}
	if (memcmp(&rp.storage[index * t->size], value, t->size) != 0) {
		print_value(sh, "READ-BACK MISMATCH: value", &rp, t, index);
		return -EIO;
	}
	print_value(sh, "written and read back:", &rp, t, index);
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_param,
	SHELL_CMD_ARG(get, NULL, "get <node> <id> <type> [index]", cmd_param_get, 4, 1),
	SHELL_CMD_ARG(set, NULL, "set <node> <id> <type> <value> [index] --confirm", cmd_param_set,
		      5, 2),
	SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(param, &sub_param, "libparam client (protocol 2, port 10)", NULL);
