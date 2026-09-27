/* SPDX-License-Identifier: Apache-2.0 */
#include "bench_parse.h"

#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

int bench_parse_u32(const char *text, uint32_t max, uint32_t *out)
{
	char *end;
	unsigned long long value;

	if (text == NULL || *text == '\0' || *text == '-' || *text == '+') {
		return -EINVAL;
	}
	errno = 0;
	value = strtoull(text, &end, 0);
	if (errno != 0 || *end != '\0' || value > max) {
		return -EINVAL;
	}
	*out = (uint32_t)value;
	return 0;
}

int bench_parse_i32(const char *text, int32_t min, int32_t max, int32_t *out)
{
	char *end;
	long long value;

	if (text == NULL || *text == '\0') {
		return -EINVAL;
	}
	errno = 0;
	value = strtoll(text, &end, 10);
	if (errno != 0 || *end != '\0' || value < min || value > max) {
		return -EINVAL;
	}
	*out = (int32_t)value;
	return 0;
}

int bench_parse_double(const char *text, double min, double max, double *out)
{
	char *end;
	double value;

	if (text == NULL || *text == '\0') {
		return -EINVAL;
	}
	errno = 0;
	value = strtod(text, &end);
	if (errno != 0 || *end != '\0' || !isfinite(value) || value < min || value > max) {
		return -EINVAL;
	}
	*out = value;
	return 0;
}

int bench_parse_bool(const char *text, bool *out)
{
	static const char *const yes[] = {"1", "on", "true", "yes"};
	static const char *const no[] = {"0", "off", "false", "no"};

	if (text == NULL) {
		return -EINVAL;
	}
	for (size_t i = 0; i < sizeof(yes) / sizeof(yes[0]); i++) {
		if (strcmp(text, yes[i]) == 0) {
			*out = true;
			return 0;
		}
		if (strcmp(text, no[i]) == 0) {
			*out = false;
			return 0;
		}
	}
	return -EINVAL;
}
