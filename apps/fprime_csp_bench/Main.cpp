// CSP/libparam bench server on the TE0715, equivalent to
//   CspBench --role server --node 101 --netmask 8 --param-id 200 --param-type u32
// on Linux. Zephyr has no command line, so the configuration is set here.

#include "Components/CspLibparam/CspLibparamCore.hpp"
#include "Top/CspBenchZephyrTopologyAc.hpp"

#include "Fw/Logger/Logger.hpp"
#include "Os/Os.hpp"

int main() {
    Os::init();

    CspBenchZephyr::TopologyState state;
    state.config.role = CubeSpec::CspTest::Role::SERVER;
    state.config.canInterface = "can1";  // informational; the transport uses zephyr,canbus
    state.config.localNode = 101;
    state.config.networkPrefix = 8;
    state.config.parameterId = 200;
    state.config.parameterType = CubeSpec::CspTest::IntegerParameterType::UINT32;
    state.config.serverValue = 0x12345678;

    CspBenchZephyr::setup(state);
    if (!state.startupOk) {
        Fw::Logger::log("CSP/libparam bench server failed to start\n");
        return 0;
    }
    Fw::Logger::log("CSP/libparam bench server: node 101/8, parameter 200 (u32)\n");

    while (true) {
        CspBenchZephyr::rateDriver.cycle();
    }
    return 0;
}
