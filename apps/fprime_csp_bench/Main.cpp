// CSP/libparam bench server on the TE0715, equivalent to
//   CspBench --role server --node <node> --netmask <prefix> --param-id 200 --param-type u32
// on Linux. The node is CONFIG_APP_CSP_NODE unless `bench start <node>` is typed
// on the serial console during the start window (see shell_cmds.c).

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

    CspBenchZephyr::setup(state);
    if (!state.startupOk) {
        Fw::Logger::log("CSP/libparam bench server failed to start\n");
        return 0;
    }
    Fw::Logger::log("CSP/libparam bench server: node %u/%u, parameter 200 (u32)\n",
                    static_cast<unsigned>(node), static_cast<unsigned>(prefix));

    while (true) {
        CspBenchZephyr::rateDriver.cycle();
    }
    return 0;
}
