/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Serial shell commands of the INA229 bench (implemented in bench_cmds.cpp):
 *   ina info                          revisions, SPI settings, streaming state
 *   ina spi [hz [mode]]               show or change the SPI clock and mode
 *   ina id                            identity registers over raw SPI
 *   ina reg <addr>                    one register over raw SPI
 *   ina soak <n>                      n raw identity reads, checked (link integrity)
 *   ina init <shunt_ohm> <max_a> [options]   initialize through the manager's port
 *   ina read [count] [period_ms]      readings through the manager's port (CSV)
 *   ina timing [n]                    duration of n successful manager reads
 *   ina stream start|stop|status      periodic readings from the rate group
 *   ina cmd <command> [args]          an Ina229.Manager command through cmdDisp
 *   ina tlm [on|off]                  console telemetry printing
 */

#include <zephyr/shell/shell.h>

#include "bench_api.h"

SHELL_STATIC_SUBCMD_SET_CREATE(ina_stream_cmds,
	SHELL_CMD_ARG(start, NULL, "<period_ms> [rows]: read every period_ms (multiple of 10)",
		      ina_cmd_stream_start, 2, 1),
	SHELL_CMD_ARG(stop, NULL, "Stop and print the counts", ina_cmd_stream_stop, 1, 0),
	SHELL_CMD_ARG(status, NULL, "Print the counts", ina_cmd_stream_status, 1, 0),
	SHELL_SUBCMD_SET_END);

SHELL_STATIC_SUBCMD_SET_CREATE(ina_cmds,
	SHELL_CMD_ARG(info, NULL, "Revisions and SPI settings", ina_cmd_info, 1, 0),
	SHELL_CMD_ARG(spi, NULL, "[hz [mode]]: show or set SPI clock request and mode",
		      ina_cmd_spi, 1, 2),
	SHELL_CMD_ARG(id, NULL, "Read MANUFACTURER_ID and DEVICE_ID over raw SPI", ina_cmd_id,
		      1, 0),
	SHELL_CMD_ARG(reg, NULL, "<addr>: read one register over raw SPI", ina_cmd_reg, 2, 0),
	SHELL_CMD_ARG(wreg, NULL, "<addr> <value> [rst_delay_us]: write one 16-bit register over raw SPI, read back",
		      ina_cmd_wreg, 3, 1),
	SHELL_CMD_ARG(soak, NULL, "<n>: n checked identity reads over raw SPI", ina_cmd_soak, 2,
		      0),
	SHELL_CMD_ARG(init, NULL,
		      "<shunt_ohm> <max_current_a> [narrow] [tempcomp] [mode M] "
		      "[conv BUS SHUNT TEMP] [avg A] [tempco PPM] [delay STEPS]",
		      ina_cmd_init, 3, 14),
	SHELL_CMD_ARG(read, NULL, "[count] [period_ms]: readings through the manager",
		      ina_cmd_read, 1, 2),
	SHELL_CMD_ARG(timing, NULL, "[n]: duration of n successful reads", ina_cmd_timing, 1, 1),
	SHELL_CMD(stream, &ina_stream_cmds, "Periodic readings from the rate group", NULL),
	SHELL_CMD_ARG(cmd, NULL, "<command> [args]: send an Ina229.Manager command",
		      ina_cmd_fprime, 2, 14),
	SHELL_CMD_ARG(tlm, NULL, "[on|off]: console telemetry printing", ina_cmd_tlm, 1, 1),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(ina, &ina_cmds, "INA229 bench", NULL);
