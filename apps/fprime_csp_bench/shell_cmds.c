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
 */

#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include <csp/csp.h>
#include <param/param.h>
#include <param/param_client.h>
#include <param/param_list.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "bench_start.h"

#define PARAM_VERSION    2
#define PARAM_TIMEOUT_MS 1000
#define PARAM_MAX_INDEX  127

static K_SEM_DEFINE(start_sem, 0, 1);
static uint16_t start_node = CONFIG_APP_CSP_NODE;
static uint8_t start_prefix = CONFIG_APP_CSP_NETMASK;
static bool started;

void bench_wait_for_start(uint16_t *node, uint8_t *prefix)
{
	printk("\n*** CSP bench server: default node %u/%u. Type `bench start [node] [prefix]` "
	       "within %d s to start (on another node), or wait for the defaults. ***\n\n",
	       start_node, start_prefix, CONFIG_APP_START_WINDOW_S);
	(void)k_sem_take(&start_sem, K_SECONDS(CONFIG_APP_START_WINDOW_S));
	started = true;
	*node = start_node;
	*prefix = start_prefix;
}

static int parse_ulong(const struct shell *sh, const char *arg, unsigned long max,
		       unsigned long *out)
{
	char *end;
	unsigned long v = strtoul(arg, &end, 0);

	if (*arg == '\0' || *end != '\0' || v > max) {
		shell_error(sh, "invalid number '%s' (max %lu)", arg, max);
		return -EINVAL;
	}
	*out = v;
	return 0;
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
	shell_print(sh, "starting on node %u/%u", start_node, start_prefix);
	k_sem_give(&start_sem);
	return 0;
}

static int cmd_bench_info(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	shell_print(sh, "node %u/%u (%s), libparam server port 10: parameter 200 (u32)",
		    start_node, start_prefix, started ? "started" : "waiting for start");
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

struct param_type_info {
	const char *name;
	param_type_e type;
	uint8_t size;
};

static const struct param_type_info param_types[] = {
	{"u8", PARAM_TYPE_UINT8, 1},   {"i8", PARAM_TYPE_INT8, 1},
	{"u16", PARAM_TYPE_UINT16, 2}, {"i16", PARAM_TYPE_INT16, 2},
	{"u32", PARAM_TYPE_UINT32, 4}, {"i32", PARAM_TYPE_INT32, 4},
	{"u64", PARAM_TYPE_UINT64, 8}, {"i64", PARAM_TYPE_INT64, 8},
	{"float", PARAM_TYPE_FLOAT, 4}, {"double", PARAM_TYPE_DOUBLE, 8},
};

/* A remote parameter descriptor for one access */
struct remote_param {
	param_t param;
	uint16_t node;
	csp_timestamp_t timestamp;
	uint8_t storage[(PARAM_MAX_INDEX + 1) * 8] __aligned(8);
};

static const struct param_type_info *find_type(const struct shell *sh, const char *name)
{
	for (size_t i = 0; i < ARRAY_SIZE(param_types); i++) {
		if (strcmp(param_types[i].name, name) == 0) {
			return &param_types[i];
		}
	}
	shell_error(sh, "unknown type '%s' (u8 i8 u16 i16 u32 i32 u64 i64 float double)", name);
	return NULL;
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
	char *end;

	if (t->type == PARAM_TYPE_FLOAT || t->type == PARAM_TYPE_DOUBLE) {
		double d = strtod(arg, &end);

		if (*end != '\0') {
			goto invalid;
		}
		if (t->type == PARAM_TYPE_FLOAT) {
			float f = (float)d;

			memcpy(out, &f, sizeof(f));
		} else {
			memcpy(out, &d, sizeof(d));
		}
		return 0;
	}

	if (t->type == PARAM_TYPE_INT8 || t->type == PARAM_TYPE_INT16 ||
	    t->type == PARAM_TYPE_INT32 || t->type == PARAM_TYPE_INT64) {
		long long v = strtoll(arg, &end, 0);

		if (*end != '\0') {
			goto invalid;
		}
		memcpy(out, &v, t->size); /* little endian: low bytes */
		return 0;
	}

	unsigned long long v = strtoull(arg, &end, 0);

	if (*end != '\0') {
		goto invalid;
	}
	memcpy(out, &v, t->size);
	return 0;

invalid:
	shell_error(sh, "invalid %s value '%s'", t->name, arg);
	return -EINVAL;
}

static int cmd_param_set(const struct shell *sh, size_t argc, char **argv)
{
	const struct param_type_info *t;
	unsigned long node, id, index = 0;
	uint8_t value[8] = {0};
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
