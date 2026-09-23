#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Wait for `bench start` on the shell, or the start window; returns the node to use. */
void bench_wait_for_start(uint16_t *node, uint8_t *prefix);

/* After CSP is up: register led_d4 and start libparam's list service. */
int bench_start_services(void);

#ifdef __cplusplus
}
#endif
