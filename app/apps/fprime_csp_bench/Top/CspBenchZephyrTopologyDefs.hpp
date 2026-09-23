#ifndef CSPBENCHZEPHYR_CSPBENCHZEPHYRTOPOLOGYDEFS_HPP
#define CSPBENCHZEPHYR_CSPBENCHZEPHYRTOPOLOGYDEFS_HPP

#include "Components/CspLibparam/CspLibparamCore.hpp"
#include "Top/FppConstantsAc.hpp"

namespace CspBenchZephyr {

struct TopologyState {
    CubeSpec::CspTest::Config config;
    mutable bool startupOk = true;
};

}  // namespace CspBenchZephyr

#endif
