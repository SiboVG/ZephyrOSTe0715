// SPDX-License-Identifier: Apache-2.0
//
// ADXL355 bench on the TE0715: the fprime-adxl355 manager and synchronized application
// on SPI1 (Pmod J1), with the serial shell as the operator interface (shell_cmds.c,
// bench_cmds.cpp) and a timing thread in place of the FPGA synchronization source.
// Events and telemetry are printed on the console.

#include "Os/Os.hpp"
#include "Top/Adxl355Te0715TopologyAc.hpp"
#include "bench_api.h"

#include <zephyr/kernel.h>

int main() {
    Os::init();

    // Before setup: the printer's channel table must be complete before telemetry flows
    adxl_bench_register_telemetry();

    Adxl355Te0715::TopologyState state;
    state.spiHz = CONFIG_APP_SPI_FREQUENCY;
    state.spiMode = CONFIG_APP_SPI_MODE;
    Adxl355Te0715::setup(state);
    adxl_bench_started(CONFIG_APP_SPI_FREQUENCY, CONFIG_APP_SPI_MODE, state.appConfigured);

    while (true) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
