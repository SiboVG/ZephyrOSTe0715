/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Parsing of the numbers and parameter values typed in the serial shell.
 */

#include "param_value.h"

#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

const struct param_value_type param_value_types[] = {
	{"u8", PARAM_VALUE_UNSIGNED, 1},  {"i8", PARAM_VALUE_SIGNED, 1},
	{"u16", PARAM_VALUE_UNSIGNED, 2}, {"i16", PARAM_VALUE_SIGNED, 2},
	{"u32", PARAM_VALUE_UNSIGNED, 4}, {"i32", PARAM_VALUE_SIGNED, 4},
	{"u64", PARAM_VALUE_UNSIGNED, 8}, {"i64", PARAM_VALUE_SIGNED, 8},
	{"float", PARAM_VALUE_FLOAT, 4},  {"double", PARAM_VALUE_FLOAT, 8},
};

const size_t param_value_type_count = sizeof(param_value_types) / sizeof(param_value_types[0]);

const struct param_value_type *param_value_type_find(const char *name)
{
	for (size_t i = 0; i < param_value_type_count; i++) {
		if (strcmp(param_value_types[i].name, name) == 0) {
			return &param_value_types[i];
		}
	}
	return NULL;
}

/* strto*() skip leading white space; a typed argument has none */
static bool starts_with_number(const char *arg)
{
	return *arg != '\0' && !isspace((unsigned char)*arg);
}

/* strtoull() accepts a sign and negates the value; a typed "-1" is not a large number */
static int parse_unsigned(const char *arg, unsigned long long *out)
{
	char *end;

	if (!starts_with_number(arg) || *arg == '-' || *arg == '+') {
		return -EINVAL;
	}
	errno = 0;
	*out = strtoull(arg, &end, 0);
	if (*end != '\0') {
		return -EINVAL;
	}
	return (errno == ERANGE) ? -ERANGE : 0;
}

int param_value_parse_ulong(const char *arg, unsigned long max, unsigned long *out)
{
	unsigned long long v;
	int err = parse_unsigned(arg, &v);

	if (err != 0) {
		return err;
	}
	if (v > max) {
		return -ERANGE;
	}
	*out = (unsigned long)v;
	return 0;
}

static int parse_signed(const struct param_value_type *t, const char *arg, uint8_t *out)
{
	/* Limits of an integer of t->size bytes */
	const long long max = (long long)((1ULL << (8U * t->size - 1U)) - 1U);
	const long long min = -max - 1;
	char *end;
	long long v;

	if (!starts_with_number(arg)) {
		return -EINVAL;
	}
	errno = 0;
	v = strtoll(arg, &end, 0);
	if (*end != '\0') {
		return -EINVAL;
	}
	if (errno == ERANGE || v < min || v > max) {
		return -ERANGE;
	}
	memcpy(out, &v, t->size); /* little endian: the low bytes */
	return 0;
}

static int parse_float(const struct param_value_type *t, const char *arg, uint8_t *out)
{
	char *end;
	double d;

	if (!starts_with_number(arg)) {
		return -EINVAL;
	}
	errno = 0;
	d = strtod(arg, &end);
	if (*end != '\0') {
		return -EINVAL;
	}
	if (!isfinite(d)) {
		/* "inf", "nan", or out of range for a double */
		return -ERANGE;
	}
	if (t->size == sizeof(float)) {
		float f;

		if (fabs(d) > (double)FLT_MAX) {
			return -ERANGE;
		}
		f = (float)d;
		memcpy(out, &f, sizeof(f));
	} else {
		memcpy(out, &d, sizeof(d));
	}
	return 0;
}

int param_value_parse(const struct param_value_type *t, const char *arg,
		      uint8_t out[PARAM_VALUE_MAX_SIZE])
{
	unsigned long long v;
	int err;

	switch (t->kind) {
	case PARAM_VALUE_SIGNED:
		return parse_signed(t, arg, out);
	case PARAM_VALUE_FLOAT:
		return parse_float(t, arg, out);
	case PARAM_VALUE_UNSIGNED:
	default:
		err = parse_unsigned(arg, &v);
		if (err != 0) {
			return err;
		}
		if (t->size < sizeof(v) && v >> (8U * t->size) != 0U) {
			return -ERANGE;
		}
		memcpy(out, &v, t->size);
		return 0;
	}
}
