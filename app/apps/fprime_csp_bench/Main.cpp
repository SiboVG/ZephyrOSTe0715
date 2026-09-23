// CSP/libparam bench server on the TE0715, equivalent to
//   CspBench --role server --node <node> --netmask <prefix> --param-id 200 --param-type u32
// on Linux, plus the led_d4 parameter (201) and libparam's list service. The node is
// CONFIG_APP_CSP_NODE unless `bench start <node>` is typed on the serial console during
// the start window (see shell_cmds.c).

#include "Components/CspLibparam/CspLibparamCore.hpp"
#include "Top/CspBenchZephyrTopologyAc.hpp"
#include "bench_start.h"

#include "Fw/Logger/Logger.hpp"
#include "Os/Os.hpp"

int main() {
    Os::init();

    std::uint16_t node = 0;
    std::uint8_t prefix = 0;
    bench_wait_for_start(&node, &prefix);

    CspBenchZephyr::TopologyState state;
    state.config.role = CubeSpec::CspTest::Role::SERVER;
    state.config.canInterface = "can1";  // informational; the transport uses zephyr,canbus
    state.config.localNode = node;
    state.config.peerNode = node;
    state.config.networkPrefix = prefix;
    state.config.parameterId = 200;
    state.config.parameterType = CubeSpec::CspTest::IntegerParameterType::UINT32;
    state.config.serverValue = 0x12345678;
    state.config.routerPriority = CONFIG_APP_CSP_ROUTER_PRIORITY;

    CspBenchZephyr::setup(state);
    if (!state.startupOk) {
        Fw::Logger::log("CSP/libparam bench server failed to start\n");
        return 0;
    }
    const int services = bench_start_services();
    if (services != 0) {
        Fw::Logger::log("led_d4 parameter / parameter list service failed to start (%d)\n", services);
    }
    Fw::Logger::log("CSP/libparam bench server: node %u/%u, parameters 200 bench_integer (u32), "
                    "201 led_d4 (u8)\n",
                    static_cast<unsigned>(node), static_cast<unsigned>(prefix));

    while (true) {
        CspBenchZephyr::rateDriver.cycle();
    }
    return 0;
}
