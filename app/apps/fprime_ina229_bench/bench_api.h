/* SPDX-License-Identifier: Apache-2.0 */
#ifndef INA229_BENCH_API_H
#define INA229_BENCH_API_H

/*
 * Shell command handlers of the INA229 bench, implemented in C++ (bench_cmds.cpp)
 * and registered by shell_cmds.c.
 */

#include <stddef.h>
#include <stdint.h>

struct shell;

#ifdef __cplusplus
extern "C" {
#endif

/* Called by main() once the topology is set up: prints the banner and the ready marker */
void ina_bench_started(uint32_t spi_hz, uint8_t spi_mode);

/* Registers the manager's telemetry channels with the console printer */
void ina_bench_register_telemetry(void);

int ina_cmd_info(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_spi(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_id(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_reg(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_soak(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_wreg(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_init(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_read(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_timing(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_stream_start(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_stream_stop(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_stream_status(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_fprime(const struct shell *sh, size_t argc, char **argv);
int ina_cmd_tlm(const struct shell *sh, size_t argc, char **argv);

#ifdef __cplusplus
}
#endif

#endif
