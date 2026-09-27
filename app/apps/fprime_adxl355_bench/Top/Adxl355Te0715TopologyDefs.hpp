#ifndef ADXL355TE0715_ADXL355TE0715TOPOLOGYDEFS_HPP
#define ADXL355TE0715_ADXL355TE0715TOPOLOGYDEFS_HPP

#include "TeBench/Support/BenchSpi.hpp"
#include "Top/FppConstantsAc.hpp"

namespace Adxl355Te0715 {

struct TopologyState {
    U32 spiHz;  //!< requested SPI clock
    U8 spiMode;
    mutable bool appConfigured = false;  //!< the application accepted sensor count 1
};

}  // namespace Adxl355Te0715

#endif
