#ifndef INA229TE0715_INA229TE0715TOPOLOGYDEFS_HPP
#define INA229TE0715_INA229TE0715TOPOLOGYDEFS_HPP

#include "TeBench/Support/BenchSpi.hpp"
#include "Top/FppConstantsAc.hpp"

namespace Ina229Te0715 {

struct TopologyState {
    U32 spiHz;  //!< requested SPI clock
    U8 spiMode;
};

}  // namespace Ina229Te0715

#endif
