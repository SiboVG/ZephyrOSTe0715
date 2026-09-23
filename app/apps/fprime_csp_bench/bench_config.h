/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * The board configuration file te0715.txt, which U-Boot's boot.cmd copies
 * from the SD card into RAM before starting Zephyr. Kept free of Zephyr, so
 * it can be unit tested on its own (app/tests/bench).
 *
 * RAM layout at CONFIG_APP_BOOT_CONFIG_ADDR, written by boot.cmd:
 *   +0x000  magic BENCH_CONFIG_MAGIC (only if the file was found)
 *   +0x004  file length in bytes
 *   +0x100  the file
 *
 * File format, one setting per line; '#' starts a comment:
 *   csp_node=6062
 *   csp_prefix=8
 */

#ifndef BENCH_CONFIG_H_
#define BENCH_CONFIG_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BENCH_CONFIG_MAGIC       0x37304554U /* "TE07" */
#define BENCH_CONFIG_TEXT_OFFSET 0x100U
#define BENCH_CONFIG_AREA_SIZE   0x1000U
#define BENCH_CONFIG_MAX_TEXT    (BENCH_CONFIG_AREA_SIZE - BENCH_CONFIG_TEXT_OFFSET)

#define BENCH_CONFIG_NODE_MAX   16381U
#define BENCH_CONFIG_PREFIX_MAX 13U

struct bench_config {
	bool has_node;
	uint16_t node;
	bool has_prefix;
	uint8_t prefix;
};

/*
 * Parse the file text (len bytes, need not be terminated). Returns 0, or
 * -EINVAL with *bad_line set to the first line (from 1) that is not a known
 * setting with a valid value; then cfg is left empty.
 */
int bench_config_parse(const char *text, size_t len, struct bench_config *cfg, int *bad_line);

/*
 * Parse the RAM area written by boot.cmd (area_size bytes). Returns 0 if a
 * file was parsed, -ENOENT if boot.cmd found no file (or did not run), or
 * -EINVAL for a bad header or a bad file (then *bad_line as above, 0 for the
 * header).
 */
int bench_config_from_area(const uint8_t *area, size_t area_size, struct bench_config *cfg,
			   int *bad_line);

#endif /* BENCH_CONFIG_H_ */
