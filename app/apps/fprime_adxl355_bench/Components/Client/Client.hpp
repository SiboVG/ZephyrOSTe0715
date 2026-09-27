// SPDX-License-Identifier: Apache-2.0
#ifndef ADXL355TE0715_CLIENT_HPP
#define ADXL355TE0715_CLIENT_HPP

#include <atomic>

#include "Components/Client/ClientComponentAc.hpp"

namespace Adxl355Te0715 {

class Client final : public ClientComponentBase {
  public:
    explicit Client(const char* compName);

    Adxl355::DriverStatus configureSensor(const Adxl355::DeviceConfiguration& configuration);
    Adxl355::DriverStatus readSensor(Adxl355::AccelerationSample& sample);
    Adxl355::DriverStatus readTemperature(Adxl355::TemperatureSample& sample);
    Adxl355::DriverStatus setMeasurement(bool enable);

    //! One full-duplex transfer of size bytes under one chip-select assertion
    Drv::SpiStatus transfer(const U8* tx, U8* rx, FwSizeType size);

    //! One synchronization instant: runs the application's acquisition synchronously
    void acquire(U64 syncTimeMicroseconds);

    //! Frame statistics, counted from frameReady since resetFrameStats()
    struct FrameStats {
        U64 frames;
        U64 complete;
        U64 partial;
        U64 sequenceGaps;
        U64 stale;
        U64 implausible;
        U64 busy;
        U64 otherErrors;
    };
    void resetFrameStats(U32 printEvery);
    FrameStats frameStats() const;

    //! Prints one sample as a CSV row (ADXL_ROW)
    static void printRow(U32 timeMs, const char* status, const Adxl355::AccelerationSample& s);
    static void printHeader();
    static void printFrameHeader();

  private:
    void frameReady_handler(FwIndexType portNum, Adxl355::SampleFrame& frame) override;

    std::atomic<U32> m_printEvery{0U};
    std::atomic<U64> m_frames{0U};
    std::atomic<U64> m_complete{0U};
    std::atomic<U64> m_partial{0U};
    std::atomic<U64> m_sequenceGaps{0U};
    std::atomic<U64> m_stale{0U};
    std::atomic<U64> m_implausible{0U};
    std::atomic<U64> m_busy{0U};
    std::atomic<U64> m_otherErrors{0U};
    // Written only by the timing thread (frameReady), read after reset
    bool m_haveSequence = false;
    U64 m_lastSequence = 0U;
};

}  // namespace Adxl355Te0715

#endif
