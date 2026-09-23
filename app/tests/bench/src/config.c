/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Unit tests of the te0715.txt board configuration
 * (apps/fprime_csp_bench/bench_config.c): a file that is not exactly
 * understood must be refused as a whole, so the board falls back to its
 * defaults and says why, instead of starting on a half-read node.
 */

#include <errno.h>
#include <string.h>

#include <zephyr/ztest.h>

#include "bench_config.h"

static int parse(const char *text, struct bench_config *cfg, int *bad_line)
{
	return bench_config_parse(text, strlen(text), cfg, bad_line);
}

static void parse_fails_at(const char *text, int line)
{
	struct bench_config cfg;
	int bad_line = -1;

	zassert_equal(parse(text, &cfg, &bad_line), -EINVAL, "'%s' accepted", text);
	zassert_equal(bad_line, line, "'%s': reported line %d", text, bad_line);
	zassert_false(cfg.has_node || cfg.has_prefix, "'%s' left settings behind", text);
}

ZTEST(bench_config, test_node_and_prefix)
{
	struct bench_config cfg;
	int bad_line;

	zassert_ok(parse("csp_node=6062\ncsp_prefix=8\n", &cfg, &bad_line));
	zassert_true(cfg.has_node && cfg.has_prefix);
	zassert_equal(cfg.node, 6062);
	zassert_equal(cfg.prefix, 8);

	zassert_ok(parse("csp_node=6063", &cfg, &bad_line), "no final newline");
	zassert_true(cfg.has_node);
	zassert_false(cfg.has_prefix, "an absent setting keeps its default");
	zassert_equal(cfg.node, 6063);
}

ZTEST(bench_config, test_editor_friendly)
{
	struct bench_config cfg;
	int bad_line;

	/* Windows line ends, spaces, comments and blank lines, as a text editor leaves them */
	zassert_ok(parse("# TE0715 at the FlatSat\r\n\r\n  csp_node = 6064   # agreed\r\n", &cfg,
			 &bad_line));
	zassert_equal(cfg.node, 6064);
	zassert_ok(parse("", &cfg, &bad_line), "an empty file is fine");
	zassert_false(cfg.has_node);
	zassert_ok(parse("csp_node=0x17AE\n", &cfg, &bad_line));
	zassert_equal(cfg.node, 6062);
}

ZTEST(bench_config, test_refused)
{
	parse_fails_at("csp_nod=6062\n", 1);             /* typo */
	parse_fails_at("csp_node=6062\ncsp_prefix=14\n", 2); /* above 13 */
	parse_fails_at("csp_node=16382\n", 1);           /* above the unicast range */
	parse_fails_at("csp_node=0\n", 1);
	parse_fails_at("csp_node=-1\n", 1);
	parse_fails_at("csp_node=\n", 1);
	parse_fails_at("csp_node 6062\n", 1);            /* no '=' */
	parse_fails_at("csp_node=6062x\n", 1);
	parse_fails_at("\n\n# ok\nnode=6062\n", 4);
}

ZTEST(bench_config, test_embedded_nul_is_refused)
{
	static const char text[] = "csp_node=6062\0\n";
	struct bench_config cfg;
	int bad_line;

	zassert_equal(bench_config_parse(text, sizeof(text) - 1, &cfg, &bad_line), -EINVAL);
	zassert_equal(bad_line, 1);
}

static uint8_t area[BENCH_CONFIG_AREA_SIZE];

static void fill_area(uint32_t magic, uint32_t len, const char *text)
{
	memset(area, 0xEE, sizeof(area)); /* stale RAM */
	memcpy(area, &magic, sizeof(magic));
	memcpy(area + 4, &len, sizeof(len));
	if (text != NULL) {
		memcpy(area + BENCH_CONFIG_TEXT_OFFSET, text, strlen(text));
	}
}

ZTEST(bench_config, test_area)
{
	struct bench_config cfg;
	int bad_line;
	const char *text = "csp_node=6065\n";

	fill_area(BENCH_CONFIG_MAGIC, strlen(text), text);
	zassert_ok(bench_config_from_area(area, sizeof(area), &cfg, &bad_line));
	zassert_equal(cfg.node, 6065);

	/* Only the file's length is read, not the stale bytes after it */
	fill_area(BENCH_CONFIG_MAGIC, strlen(text) - 1, text);
	zassert_ok(bench_config_from_area(area, sizeof(area), &cfg, &bad_line));
	zassert_equal(cfg.node, 6065);
}

ZTEST(bench_config, test_area_without_file)
{
	struct bench_config cfg;
	int bad_line;

	/* boot.cmd did not run (JTAG load) or found no file: the header is not stamped */
	fill_area(0, 14, "csp_node=6065\n");
	zassert_equal(bench_config_from_area(area, sizeof(area), &cfg, &bad_line), -ENOENT);
	zassert_false(cfg.has_node);
	fill_area(0xEEEEEEEE, 0xEEEEEEEE, NULL);
	zassert_equal(bench_config_from_area(area, sizeof(area), &cfg, &bad_line), -ENOENT);
}

ZTEST(bench_config, test_area_bad_length)
{
	struct bench_config cfg;
	int bad_line = -1;

	fill_area(BENCH_CONFIG_MAGIC, BENCH_CONFIG_MAX_TEXT + 1, "csp_node=6065\n");
	zassert_equal(bench_config_from_area(area, sizeof(area), &cfg, &bad_line), -EINVAL);
	zassert_equal(bad_line, 0, "the header, not a line, is at fault");
	zassert_false(cfg.has_node);
}

ZTEST_SUITE(bench_config, NULL, NULL, NULL, NULL, NULL);
