/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEBENCH_BENCH_PARSE_H
#define TEBENCH_BENCH_PARSE_H

/*
 * Argument parsing for the bench shell commands. Each function accepts the whole
 * string or nothing: trailing characters, overflow and out-of-range values are
 * refused with -EINVAL, and *out is then unchanged.
 */

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Decimal, or hexadecimal with 0x; at most max */
int bench_parse_u32(const char *text, uint32_t max, uint32_t *out);

/* Signed decimal within [min, max] */
int bench_parse_i32(const char *text, int32_t min, int32_t max, int32_t *out);

/* Finite decimal number within [min, max] */
int bench_parse_double(const char *text, double min, double max, double *out);

/* 1/0, on/off, true/false, yes/no */
int bench_parse_bool(const char *text, bool *out);

#ifdef __cplusplus
}
#endif

#endif
