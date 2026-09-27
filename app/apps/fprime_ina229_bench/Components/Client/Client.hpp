// SPDX-License-Identifier: Apache-2.0
#ifndef INA229TE0715_CLIENT_HPP
#define INA229TE0715_CLIENT_HPP

#include <atomic>

#include "Components/Client/ClientComponentAc.hpp"

namespace Ina229Te0715 {

class Client final : public ClientComponentBase {
  public:
    //! Rate-group ticks per second (rateDriver period 10 ms)
    static constexpr U32 TICKS_PER_SECOND = 100U;

    explicit Client(const char* compName);

    Ina229::DriverStatus configureSensor(const Ina229::DeviceConfig& config);
    Ina229::DriverStatus readSensor(Ina229::Reading& reading);

    //! One full-duplex transfer of size bytes under one chip-select assertion
    Drv::SpiStatus transfer(const U8* tx, U8* rx, FwSizeType size);

    //! Periodic sampling from the rate group: one read every periodTicks ticks, printed
    //! as an INA_ROW line, until rows OK readings (0: until stopSampling()).
    bool startSampling(U32 periodTicks, U32 rows);
    void stopSampling();
    bool isSampling() const { return this->m_sampling.load(); }

    struct SamplingCounts {
        U32 rows;
        U32 notReady;
        U32 failures;
    };
    SamplingCounts samplingCounts() const;

    //! Prints one reading as a CSV row (INA_ROW)
    static void printRow(U32 timeMs, const char* status, const Ina229::Reading& r);
    static void printHeader();

  private:
    void run_handler(FwIndexType portNum, U32 context) override;

    std::atomic<bool> m_sampling{false};
    std::atomic<U32> m_periodTicks{0U};
    std::atomic<U32> m_rowLimit{0U};
    U32 m_tick = 0U;
    std::atomic<U32> m_rows{0U};
    std::atomic<U32> m_notReady{0U};
    std::atomic<U32> m_failures{0U};
};

}  // namespace Ina229Te0715

#endif
