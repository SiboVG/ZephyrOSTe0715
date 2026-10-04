/* SPDX-License-Identifier: Apache-2.0 */
#ifndef ADXL355_BENCH_API_H
#define ADXL355_BENCH_API_H

/*
 * Shell command handlers of the ADXL355 bench, implemented in C++ (bench_cmds.cpp)
 * and registered by shell_cmds.c.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct shell;

#ifdef __cplusplus
extern "C" {
#endif

/* Called by main() once the topology is set up: starts the frame timing thread,
 * prints the banner and the ready marker */
void adxl_bench_started(uint32_t spi_hz, uint8_t spi_mode, bool app_configured);

/* Registers the manager's and the application's telemetry channels with the printer */
void adxl_bench_register_telemetry(void);

int adxl_cmd_info(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_spi(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_id(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_reg(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_soak(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_drdy(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_phase(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_capture(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_init(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_measure(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_read(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_temp(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_selftest(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_timing(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_stream_start(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_stream_start_pl(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_stream_stop(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_stream_status(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_fprime(const struct shell *sh, size_t argc, char **argv);
int adxl_cmd_tlm(const struct shell *sh, size_t argc, char **argv);

#ifdef __cplusplus
}
#endif

#endif
