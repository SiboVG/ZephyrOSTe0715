// SPDX-License-Identifier: Apache-2.0
#ifndef TEBENCH_BENCHSPI_HPP
#define TEBENCH_BENCHSPI_HPP

// No Zephyr headers here (see ShellCommander.hpp): the topology definitions include it.
#include <Fw/FPrimeBasicTypes.hpp>

namespace Zephyr {
class ZephyrSpiDriver;
}

namespace TeBench {

//! The benches use one sensor on SPI1, selected by the controller's SS0 on MIO13
//! (te0701-spi1.overlay).
//! The Zynq controller divides SPI_REF_CLK by 4 to 256 (Xilinx xspips.h,
//! XSPIPS_CLK_PRESCALE_4..256); Zephyr's cdns,spi driver picks the fastest division
//! that does not exceed the request.
namespace BenchSpi {

//! SPI_REF_CLK in Hz (devicetree clock-frequency of spi1)
U32 referenceClockHz();

//! Slowest SCLK (SPI_REF_CLK / 256) and fastest SCLK within the sensors' 10 MHz limit
U32 minimumSclkHz();
U32 maximumSclkHz();

//! The SCLK the driver generates for a request, or 0 when the request is outside
//! [minimumSclkHz(), 10 MHz]
U32 actualSclkHz(U32 requestedHz);

//! Point the driver at SPI1: master, 8-bit words, MSB first, SPI mode 0..3 (bit 1
//! CPOL, bit 0 CPHA), chip select SS0. Call only while no transfer is in progress.
void configure(Zephyr::ZephyrSpiDriver& driver, U32 requestedHz, U8 mode);

}  // namespace BenchSpi
}  // namespace TeBench

#endif
