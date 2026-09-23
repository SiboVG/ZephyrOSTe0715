/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * The board configuration file te0715.txt (see bench_config.h).
 */

#include "bench_config.h"

#include <errno.h>
#include <string.h>

#include "bench_value.h"

#define MAX_LINE 80

static bool is_blank(char c)
{
	return c == ' ' || c == '\t' || c == '\r';
}

/* Parse one line without its '\n'; blank lines and comments are fine */
static int parse_line(const char *line, size_t len, struct bench_config *cfg)
{
	char buf[MAX_LINE + 1];
	const char *comment = memchr(line, '#', len);
	char *key;
	char *value;
	char *eq;
	char *end;
	unsigned long v;

	if (comment != NULL) {
		len = (size_t)(comment - line);
	}
	while (len > 0 && is_blank(line[len - 1])) {
		len--;
	}
	while (len > 0 && is_blank(*line)) {
		line++;
		len--;
	}
	if (len == 0) {
		return 0;
	}
	if (len > MAX_LINE) {
		return -EINVAL;
	}
	memcpy(buf, line, len);
	buf[len] = '\0';

	eq = strchr(buf, '=');
	if (eq == NULL) {
		return -EINVAL;
	}
	/* Trim around '=' */
	key = buf;
	end = eq;
	while (end > key && is_blank(end[-1])) {
		end--;
	}
	*end = '\0';
	value = eq + 1;
	while (is_blank(*value)) {
		value++;
	}

	if (strcmp(key, "csp_node") == 0) {
		if (bench_value_parse_ulong(value, BENCH_CONFIG_NODE_MAX, &v) != 0 || v == 0) {
			return -EINVAL;
		}
		cfg->has_node = true;
		cfg->node = (uint16_t)v;
		return 0;
	}
	if (strcmp(key, "csp_prefix") == 0) {
		if (bench_value_parse_ulong(value, BENCH_CONFIG_PREFIX_MAX, &v) != 0) {
			return -EINVAL;
		}
		cfg->has_prefix = true;
		cfg->prefix = (uint8_t)v;
		return 0;
	}
	/* An unknown key is refused, so a typo does not go unnoticed */
	return -EINVAL;
}

int bench_config_parse(const char *text, size_t len, struct bench_config *cfg, int *bad_line)
{
	struct bench_config parsed = {0};
	int line_no = 1;

	memset(cfg, 0, sizeof(*cfg));
	while (len > 0) {
		const char *nl = memchr(text, '\n', len);
		size_t line_len = (nl != NULL) ? (size_t)(nl - text) : len;

		if (memchr(text, '\0', line_len) != NULL || parse_line(text, line_len, &parsed) != 0) {
			*bad_line = line_no;
			return -EINVAL;
		}
		if (nl == NULL) {
			break;
		}
		text = nl + 1;
		len -= line_len + 1;
		line_no++;
	}
	*cfg = parsed;
	return 0;
}

int bench_config_from_area(const uint8_t *area, size_t area_size, struct bench_config *cfg,
			   int *bad_line)
{
	uint32_t magic;
	uint32_t len;

	memset(cfg, 0, sizeof(*cfg));
	*bad_line = 0;
	if (area_size < BENCH_CONFIG_TEXT_OFFSET) {
		return -EINVAL;
	}
	memcpy(&magic, area, sizeof(magic));
	memcpy(&len, area + 4, sizeof(len));
	if (magic != BENCH_CONFIG_MAGIC) {
		return -ENOENT;
	}
	if (len > area_size - BENCH_CONFIG_TEXT_OFFSET || len > BENCH_CONFIG_MAX_TEXT) {
		return -EINVAL;
	}
	return bench_config_parse((const char *)area + BENCH_CONFIG_TEXT_OFFSET, len, cfg,
				  bad_line);
}
