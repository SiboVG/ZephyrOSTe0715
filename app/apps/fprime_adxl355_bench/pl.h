/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * The PL of the cubespec-pl pp bitstream as the ADXL355 bench uses it: identification
 * (sysctrl), the time base, and the accelerometer timing core (acc), which generates
 * the ADXL355 external clock and synchronization pulse and interrupts the PS a
 * programmable delay after every sync instant. Registers and addresses come from
 * cubespec-pl (sw/include/pp_regs.h, sw/dts/pp-pl.dtsi).
 *
 * Only use these with the cubespec-pl bitstream loaded: without a PL design the
 * register window does not answer and an access stalls the bus.
 */

#ifndef ADXL355_BENCH_PL_H
#define ADXL355_BENCH_PL_H

#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#ifdef __cplusplus
extern "C" {
#endif

int pl_cmd_info(const struct shell *sh, size_t argc, char **argv);
int pl_cmd_clk(const struct shell *sh, size_t argc, char **argv);
int pl_cmd_sync(const struct shell *sh, size_t argc, char **argv);
int pl_cmd_delay(const struct shell *sh, size_t argc, char **argv);
int pl_cmd_status(const struct shell *sh, size_t argc, char **argv);
int pl_cmd_time(const struct shell *sh, size_t argc, char **argv);

#ifdef __cplusplus
}

namespace Pl {

//! One published sync instant of the acc core
struct SyncEvent {
    uint32_t count;  //!< sequence number since the pulse train started
    uint64_t ticks;  //!< time base value of the sync instant
};

//! EXT_CLK and the SYNC pulse train are both running
bool timingRunning();

//! SYNC period in microseconds
uint32_t syncPeriodUs();

//! SYNC period in time base ticks
uint64_t syncPeriodTicks();

//! The time base now (a snapshot, about 1 us of register accesses)
uint64_t nowTicks();

//! Enable the acc SYNC and OVERRUN interrupts and the GIC line
void startEvents();

//! Disable them again
void stopEvents();

//! Wait for the next sync event; false on timeout
bool waitEvent(SyncEvent& event, k_timeout_t timeout);

//! Time base ticks to microseconds
uint64_t ticksToUs(uint64_t ticks);

//! OVERRUN interrupts seen since startEvents()
uint32_t overruns();

}  // namespace Pl
#endif

#endif
