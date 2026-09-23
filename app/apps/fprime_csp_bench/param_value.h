/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Parsing of the numbers and parameter values typed in the serial shell.
 * Kept free of Zephyr and libparam, so it can be unit tested on its own
 * (app/tests/param_value).
 */

#ifndef PARAM_VALUE_H_
#define PARAM_VALUE_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PARAM_VALUE_MAX_SIZE 8

enum param_value_kind {
	PARAM_VALUE_UNSIGNED,
	PARAM_VALUE_SIGNED,
	PARAM_VALUE_FLOAT,
};

struct param_value_type {
	const char *name; /* as typed in the shell, e.g. "u32" */
	enum param_value_kind kind;
	uint8_t size;     /* bytes */
};

/* All types, in the order they are listed in help texts */
extern const struct param_value_type param_value_types[];
extern const size_t param_value_type_count;

/* The type with this name, or NULL */
const struct param_value_type *param_value_type_find(const char *name);

/*
 * Parse an unsigned number (decimal, 0x hex or 0 octal) of at most max.
 * Returns 0, -EINVAL if arg is not a number, or -ERANGE if it is above max.
 */
int param_value_parse_ulong(const char *arg, unsigned long max, unsigned long *out);

/*
 * Parse a value of type t into out (t->size bytes, little endian, as on the
 * wire and in memory on the Cortex-A9). Returns 0, -EINVAL if arg is not a
 * number of that kind, or -ERANGE if it does not fit the type: nothing is
 * truncated, and a float or double must be finite.
 */
int param_value_parse(const struct param_value_type *t, const char *arg,
		      uint8_t out[PARAM_VALUE_MAX_SIZE]);

#endif /* PARAM_VALUE_H_ */
