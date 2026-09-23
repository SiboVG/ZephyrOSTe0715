/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Unit tests of the shell's number and parameter value parsing
 * (apps/fprime_csp_bench/param_value.c): what `param set` sends to a remote
 * node must be exactly the typed value, or nothing.
 */

#include <errno.h>
#include <string.h>

#include <zephyr/ztest.h>

#include "param_value.h"

static const struct param_value_type *type(const char *name)
{
	const struct param_value_type *t = param_value_type_find(name);

	zassert_not_null(t, "type %s", name);
	return t;
}

/* Parse, expect success, and return the bytes (unused bytes stay 0xAA) */
static void parse_ok(const char *name, const char *arg, const uint8_t *expect)
{
	const struct param_value_type *t = type(name);
	uint8_t out[PARAM_VALUE_MAX_SIZE];

	memset(out, 0xAA, sizeof(out));
	zassert_ok(param_value_parse(t, arg, out), "%s '%s'", name, arg);
	zassert_mem_equal(out, expect, t->size, "%s '%s'", name, arg);
	for (size_t i = t->size; i < sizeof(out); i++) {
		zassert_equal(out[i], 0xAA, "%s '%s' wrote past its size", name, arg);
	}
}

static void parse_fails(const char *name, const char *arg, int err)
{
	uint8_t out[PARAM_VALUE_MAX_SIZE];

	memset(out, 0xAA, sizeof(out));
	zassert_equal(param_value_parse(type(name), arg, out), err, "%s '%s'", name, arg);
	for (size_t i = 0; i < sizeof(out); i++) {
		zassert_equal(out[i], 0xAA, "%s '%s' wrote output on failure", name, arg);
	}
}

ZTEST(param_value, test_types)
{
	static const struct {
		const char *name;
		enum param_value_kind kind;
		uint8_t size;
	} expect[] = {
		{"u8", PARAM_VALUE_UNSIGNED, 1},  {"i8", PARAM_VALUE_SIGNED, 1},
		{"u16", PARAM_VALUE_UNSIGNED, 2}, {"i16", PARAM_VALUE_SIGNED, 2},
		{"u32", PARAM_VALUE_UNSIGNED, 4}, {"i32", PARAM_VALUE_SIGNED, 4},
		{"u64", PARAM_VALUE_UNSIGNED, 8}, {"i64", PARAM_VALUE_SIGNED, 8},
		{"float", PARAM_VALUE_FLOAT, 4},  {"double", PARAM_VALUE_FLOAT, 8},
	};

	zassert_equal(param_value_type_count, ARRAY_SIZE(expect));
	for (size_t i = 0; i < ARRAY_SIZE(expect); i++) {
		const struct param_value_type *t = type(expect[i].name);

		zassert_equal(t->kind, expect[i].kind, "%s", expect[i].name);
		zassert_equal(t->size, expect[i].size, "%s", expect[i].name);
	}
	zassert_is_null(param_value_type_find("uint32"), "libparam's names are not shell types");
	zassert_is_null(param_value_type_find("U32"));
	zassert_is_null(param_value_type_find(""));
}

ZTEST(param_value, test_ulong)
{
	unsigned long v = 7;

	zassert_ok(param_value_parse_ulong("6061", 16381, &v));
	zassert_equal(v, 6061);
	zassert_ok(param_value_parse_ulong("0x17AD", 16381, &v));
	zassert_equal(v, 6061);
	zassert_ok(param_value_parse_ulong("16381", 16381, &v), "the maximum itself");
	zassert_ok(param_value_parse_ulong("0", 16381, &v));
	zassert_equal(v, 0);

	v = 7;
	zassert_equal(param_value_parse_ulong("16382", 16381, &v), -ERANGE);
	zassert_equal(param_value_parse_ulong("99999999999999999999999", 16381, &v), -ERANGE);
	zassert_equal(param_value_parse_ulong("", 16381, &v), -EINVAL);
	zassert_equal(param_value_parse_ulong("-1", 16381, &v), -EINVAL);
	zassert_equal(param_value_parse_ulong("+1", 16381, &v), -EINVAL);
	zassert_equal(param_value_parse_ulong(" 1", 16381, &v), -EINVAL);
	zassert_equal(param_value_parse_ulong("12a", 16381, &v), -EINVAL);
	zassert_equal(param_value_parse_ulong("0x", 16381, &v), -EINVAL);
	zassert_equal(v, 7, "output changed on failure");
}

ZTEST(param_value, test_unsigned)
{
	parse_ok("u8", "0", (const uint8_t[]){0x00});
	parse_ok("u8", "255", (const uint8_t[]){0xFF});
	parse_ok("u8", "0x7f", (const uint8_t[]){0x7F});
	parse_ok("u16", "65535", (const uint8_t[]){0xFF, 0xFF});
	parse_ok("u32", "0x12345678", (const uint8_t[]){0x78, 0x56, 0x34, 0x12});
	parse_ok("u32", "305419896", (const uint8_t[]){0x78, 0x56, 0x34, 0x12});
	parse_ok("u32", "0xCAFEBABE", (const uint8_t[]){0xBE, 0xBA, 0xFE, 0xCA});
	parse_ok("u64", "18446744073709551615",
		 (const uint8_t[]){0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF});
}

ZTEST(param_value, test_unsigned_range)
{
	/* Would have been truncated to 44, 0 and 0x2345678 */
	parse_fails("u8", "300", -ERANGE);
	parse_fails("u8", "256", -ERANGE);
	parse_fails("u16", "65536", -ERANGE);
	parse_fails("u32", "0x123456789", -ERANGE);
	parse_fails("u64", "18446744073709551616", -ERANGE);
	/* Would have been sent as 0xFF */
	parse_fails("u8", "-1", -EINVAL);
	parse_fails("u32", "-305419896", -EINVAL);
}

ZTEST(param_value, test_signed)
{
	parse_ok("i8", "-128", (const uint8_t[]){0x80});
	parse_ok("i8", "127", (const uint8_t[]){0x7F});
	parse_ok("i8", "-1", (const uint8_t[]){0xFF});
	parse_ok("i16", "-32768", (const uint8_t[]){0x00, 0x80});
	parse_ok("i32", "-2", (const uint8_t[]){0xFE, 0xFF, 0xFF, 0xFF});
	parse_ok("i32", "+42", (const uint8_t[]){42, 0, 0, 0});
	parse_ok("i64", "-9223372036854775808", (const uint8_t[]){0, 0, 0, 0, 0, 0, 0, 0x80});

	parse_fails("i8", "128", -ERANGE);
	parse_fails("i8", "-129", -ERANGE);
	parse_fails("i16", "32768", -ERANGE);
	parse_fails("i32", "2147483648", -ERANGE);
	parse_fails("i32", "-2147483649", -ERANGE);
	parse_fails("i64", "9223372036854775808", -ERANGE);
}

ZTEST(param_value, test_float)
{
	float f = 1.5f;
	double d = -0.25;
	uint8_t bytes[8];

	memcpy(bytes, &f, sizeof(f));
	parse_ok("float", "1.5", bytes);
	memcpy(bytes, &d, sizeof(d));
	parse_ok("double", "-0.25", bytes);
	d = 1e300;
	memcpy(bytes, &d, sizeof(d));
	parse_ok("double", "1e300", bytes);

	parse_fails("float", "1e39", -ERANGE);
	parse_fails("float", "inf", -ERANGE);
	parse_fails("float", "nan", -ERANGE);
	parse_fails("double", "1e999", -ERANGE);
	parse_fails("double", "-inf", -ERANGE);
}

ZTEST(param_value, test_not_a_number)
{
	static const char *const bad[] = {"", " 1", "1 ", "abc", "0x", "1.5.2", "--1", "1e"};

	for (size_t i = 0; i < ARRAY_SIZE(bad); i++) {
		parse_fails("u32", bad[i], -EINVAL);
		parse_fails("i32", bad[i], -EINVAL);
		parse_fails("double", bad[i], -EINVAL);
	}
	parse_fails("u32", "1.5", -EINVAL);
	parse_fails("i8", "0.5", -EINVAL);
}

ZTEST_SUITE(param_value, NULL, NULL, NULL, NULL, NULL);
