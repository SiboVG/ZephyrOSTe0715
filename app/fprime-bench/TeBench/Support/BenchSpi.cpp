// SPDX-License-Identifier: Apache-2.0
#include "TeBench/Support/BenchSpi.hpp"

#include "fprime-zephyr/Drv/ZephyrSpiDriver/ZephyrSpiDriver.hpp"

#include <zephyr/devicetree.h>
#include <zephyr/drivers/spi.h>

#define BENCH_SPI DT_NODELABEL(spi1)

BUILD_ASSERT(DT_NODE_HAS_STATUS_OKAY(BENCH_SPI), "the sensor benches need spi1 (te0701-spi1.overlay)");
// The controller's SS0 is the chip select; a GPIO chip select cannot work on this
// board (see te0715-pinctrl.dtsi)
BUILD_ASSERT(!DT_NODE_HAS_PROP(BENCH_SPI, cs_gpios), "the sensor benches use SPI1's own SS0 as chip select");

namespace TeBench {
namespace BenchSpi {

namespace {
constexpr U32 MAX_SENSOR_SCLK_HZ = 10000000U;  // INA229 and ADXL355 data sheets
constexpr U8 MIN_DIVIDER_CODE = 1U;            // SPI_REF_CLK / 4; code 0 is not supported
constexpr U8 MAX_DIVIDER_CODE = 7U;            // SPI_REF_CLK / 256

U32 sclkForCode(U8 code) {
    return referenceClockHz() / (2U << code);
}
}  // namespace

U32 referenceClockHz() {
    return DT_PROP(BENCH_SPI, clock_frequency);
}

U32 minimumSclkHz() {
    return sclkForCode(MAX_DIVIDER_CODE);
}

U32 maximumSclkHz() {
    U8 code = MIN_DIVIDER_CODE;
    while ((code < MAX_DIVIDER_CODE) && (sclkForCode(code) > MAX_SENSOR_SCLK_HZ)) {
        code++;
    }
    return sclkForCode(code);
}

U32 actualSclkHz(U32 requestedHz) {
    if ((requestedHz < minimumSclkHz()) || (requestedHz > MAX_SENSOR_SCLK_HZ)) {
        return 0U;
    }
    // Same search as spi_cdns_configure(): the first division not above the request
    U8 code = 0U;
    while ((code < MAX_DIVIDER_CODE) && (sclkForCode(code) > requestedHz)) {
        code++;
    }
    return sclkForCode(code);
}

void configure(Zephyr::ZephyrSpiDriver& driver, U32 requestedHz, U8 mode) {
    spi_config config = {};
    config.frequency = requestedHz;
    config.operation = SPI_OP_MODE_MASTER | SPI_WORD_SET(8) | SPI_TRANSFER_MSB |
                       (((mode & 2U) != 0U) ? SPI_MODE_CPOL : 0U) | (((mode & 1U) != 0U) ? SPI_MODE_CPHA : 0U);
    // Native chip select SS0 (slave 0), asserted by the driver over the whole transfer
    config.slave = 0U;
    config.cs.cs_is_gpio = false;
    driver.configure(DEVICE_DT_GET(BENCH_SPI), config);
}

}  // namespace BenchSpi
}  // namespace TeBench
