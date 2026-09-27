// SPDX-License-Identifier: Apache-2.0
//
// INA229 bench on the TE0715: the fprime-ina229 manager on SPI1 (Pmod J1), with the
// serial shell as the operator interface (shell_cmds.c, bench_cmds.cpp). Events and
// telemetry are printed on the console.

#include "Os/Os.hpp"
#include "TeBench/Support/BenchSpi.hpp"
#include "Top/Ina229Te0715TopologyAc.hpp"
#include "bench_api.h"

int main() {
    Os::init();

    // Before setup: the printer's channel table must be complete before telemetry flows
    ina_bench_register_telemetry();

    Ina229Te0715::TopologyState state;
    state.spiHz = CONFIG_APP_SPI_FREQUENCY;
    state.spiMode = CONFIG_APP_SPI_MODE;
    Ina229Te0715::setup(state);
    ina_bench_started(CONFIG_APP_SPI_FREQUENCY, CONFIG_APP_SPI_MODE);

    while (true) {
        Ina229Te0715::rateDriver.cycle();
    }
    return 0;
}
