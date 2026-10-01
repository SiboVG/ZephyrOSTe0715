/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Serial shell commands of the ADXL355 bench (implemented in bench_cmds.cpp):
 *   adxl info                         revisions, SPI settings, streaming state
 *   adxl spi [hz [mode]]              show or change the SPI clock and mode
 *   adxl id                           identity registers over raw SPI
 *   adxl reg <addr> [count]           registers over raw SPI
 *   adxl soak <n>                     n raw identity reads, checked (link integrity)
 *   adxl drdy [n]                     STATUS reserved bits and DATA_RDY clearing
 *   adxl phase [n]                    where in the PL's SYNC period DATA_RDY sets
 *   adxl init [range] [odr] [hpf]     initialize (internal clock) through the manager
 *   adxl measure on|off               measurement mode through the manager
 *   adxl read [count] [rows]          fresh samples through the manager, with statistics
 *   adxl temp [count]                 temperature through the manager
 *   adxl selftest [samples]           electrostatic self test against the data sheet
 *   adxl timing [n]                   duration of n successful manager reads
 *   adxl stream start|start-pl|stop|status  frames through the synchronized application,
 *                                     triggered by a timer or by the PL's sync interrupt
 *   adxl cmd <command> [args]         a manager or application command through cmdDisp
 *   adxl tlm [on|off]                 console telemetry printing
 *   pl info|clk|sync|delay|status|time  the cubespec-pl bitstream (pl.cpp)
 */

#include <zephyr/shell/shell.h>

#include "bench_api.h"
#include "pl.h"

SHELL_STATIC_SUBCMD_SET_CREATE(adxl_stream_cmds,
	SHELL_CMD_ARG(start, NULL,
		      "<rate_hz> [frames] [print_every]: trigger acquireFrame at rate_hz",
		      adxl_cmd_stream_start, 2, 2),
	SHELL_CMD_ARG(start-pl, NULL,
		      "[frames] [print_every]: trigger acquireFrame from the PL sync interrupt",
		      adxl_cmd_stream_start_pl, 1, 2),
	SHELL_CMD_ARG(stop, NULL, "Stop, disable the application, print the counts",
		      adxl_cmd_stream_stop, 1, 0),
	SHELL_CMD_ARG(status, NULL, "Print the counts", adxl_cmd_stream_status, 1, 0),
	SHELL_SUBCMD_SET_END);

SHELL_STATIC_SUBCMD_SET_CREATE(adxl_cmds,
	SHELL_CMD_ARG(info, NULL, "Revisions and SPI settings", adxl_cmd_info, 1, 0),
	SHELL_CMD_ARG(spi, NULL, "[hz [mode]]: show or set SPI clock request and mode",
		      adxl_cmd_spi, 1, 2),
	SHELL_CMD_ARG(id, NULL, "Read DEVID_AD..REVID over raw SPI", adxl_cmd_id, 1, 0),
	SHELL_CMD_ARG(reg, NULL, "<addr> [count]: read registers over raw SPI", adxl_cmd_reg, 2,
		      1),
	SHELL_CMD_ARG(soak, NULL, "<n>: n checked identity reads over raw SPI", adxl_cmd_soak,
		      2, 0),
	SHELL_CMD_ARG(drdy, NULL, "[n]: STATUS reserved bits and DATA_RDY clearing, raw SPI",
		      adxl_cmd_drdy, 1, 1),
	SHELL_CMD_ARG(phase, NULL, "[n]: where in the PL's SYNC period DATA_RDY sets, raw SPI",
		      adxl_cmd_phase, 1, 1),
	SHELL_CMD_ARG(init, NULL, "[range 2|4|8] [odr_hz] [hpf 0..6]: initialize, internal clock",
		      adxl_cmd_init, 1, 3),
	SHELL_CMD_ARG(measure, NULL, "on|off: measurement mode", adxl_cmd_measure, 2, 0),
	SHELL_CMD_ARG(read, NULL, "[count] [rows 0|1]: fresh samples and statistics",
		      adxl_cmd_read, 1, 2),
	SHELL_CMD_ARG(temp, NULL, "[count]: temperature", adxl_cmd_temp, 1, 1),
	SHELL_CMD_ARG(selftest, NULL, "[samples]: self-test response against the data sheet",
		      adxl_cmd_selftest, 1, 1),
	SHELL_CMD_ARG(timing, NULL, "[n]: duration of n successful reads", adxl_cmd_timing, 1,
		      1),
	SHELL_CMD(stream, &adxl_stream_cmds, "Frames through the synchronized application",
		  NULL),
	SHELL_CMD_ARG(cmd, NULL, "<command> [args]: send a manager or application command",
		      adxl_cmd_fprime, 2, 4),
	SHELL_CMD_ARG(tlm, NULL, "[on|off]: console telemetry printing", adxl_cmd_tlm, 1, 1),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(adxl, &adxl_cmds, "ADXL355 bench", NULL);

SHELL_STATIC_SUBCMD_SET_CREATE(pl_cmds,
	SHELL_CMD_ARG(info, NULL, "Identify the bitstream (sysctrl, timebase, acc)", pl_cmd_info,
		      1, 0),
	SHELL_CMD_ARG(clk, NULL, "on|off: the 1.024 MHz ADXL355 external clock", pl_cmd_clk, 2,
		      0),
	SHELL_CMD_ARG(sync, NULL, "on|off [period_clocks] [width_clocks]: the SYNC pulse train",
		      pl_cmd_sync, 2, 2),
	SHELL_CMD_ARG(delay, NULL, "[us]: show or set the sync interrupt delay", pl_cmd_delay, 1,
		      1),
	SHELL_CMD_ARG(status, NULL, "acc core registers", pl_cmd_status, 1, 0),
	SHELL_CMD_ARG(time, NULL, "PL time base against the PS clock", pl_cmd_time, 1, 0),
	SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(pl, &pl_cmds, "cubespec-pl bitstream (load it first)", NULL);
