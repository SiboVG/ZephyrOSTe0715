// SPDX-License-Identifier: Apache-2.0
#include "Components/Client/Client.hpp"

#include "Fw/Buffer/Buffer.hpp"
#include "TeBench/Support/EnumName.hpp"

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

namespace Adxl355Te0715 {

namespace {
constexpr F64 STANDARD_GRAVITY = 9.80665;
}

Client::Client(const char* compName) : ClientComponentBase(compName) {}

Adxl355::DriverStatus Client::configureSensor(const Adxl355::DeviceConfiguration& configuration) {
    return this->configure_out(0, configuration);
}

Adxl355::DriverStatus Client::readSensor(Adxl355::AccelerationSample& sample) {
    return this->readAcceleration_out(0, sample);
}

Adxl355::DriverStatus Client::readTemperature(Adxl355::TemperatureSample& sample) {
    return this->readTemperature_out(0, sample);
}

Adxl355::DriverStatus Client::setMeasurement(bool enable) {
    return this->measurementControl_out(0, enable);
}

Drv::SpiStatus Client::transfer(const U8* tx, U8* rx, FwSizeType size) {
    Fw::Buffer writeBuffer(const_cast<U8*>(tx), size);
    Fw::Buffer readBuffer(rx, size);
    const Drv::SpiStatus status = this->spi_out(0, writeBuffer, readBuffer);
    if ((status == Drv::SpiStatus::SPI_OK) &&
        ((writeBuffer.getSize() != size) || (readBuffer.getSize() != size) || (readBuffer.getData() != rx))) {
        return Drv::SpiStatus::SPI_OTHER_ERR;
    }
    return status;
}

void Client::acquire(U64 syncTimeMicroseconds) {
    this->acquireFrame_out(0, syncTimeMicroseconds);
}

void Client::resetFrameStats(U32 printEvery) {
    this->m_printEvery.store(printEvery);
    this->m_frames.store(0U);
    this->m_complete.store(0U);
    this->m_partial.store(0U);
    this->m_sequenceGaps.store(0U);
    this->m_stale.store(0U);
    this->m_implausible.store(0U);
    this->m_busy.store(0U);
    this->m_otherErrors.store(0U);
    this->m_haveSequence = false;
}

Client::FrameStats Client::frameStats() const {
    return FrameStats{this->m_frames.load(),       this->m_complete.load(), this->m_partial.load(),
                      this->m_sequenceGaps.load(), this->m_stale.load(),    this->m_implausible.load(),
                      this->m_busy.load(),         this->m_otherErrors.load()};
}

void Client::printHeader() {
    printk("ADXL_HEADER,time_ms,status,raw_x,raw_y,raw_z,x_g,y_g,z_g\n");
}

void Client::printFrameHeader() {
    printk("ADXL_FRAME_HEADER,sequence,sync_us,valid,status,raw_x,raw_y,raw_z,x_g,y_g,z_g\n");
}

void Client::printRow(U32 timeMs, const char* status, const Adxl355::AccelerationSample& s) {
    printk("ADXL_ROW,%u,%s,%d,%d,%d,%.6f,%.6f,%.6f\n", timeMs, status, s.get_rawX(), s.get_rawY(), s.get_rawZ(),
           s.get_xMetersPerSecondSquared() / STANDARD_GRAVITY, s.get_yMetersPerSecondSquared() / STANDARD_GRAVITY,
           s.get_zMetersPerSecondSquared() / STANDARD_GRAVITY);
}

void Client::frameReady_handler(FwIndexType portNum, Adxl355::SampleFrame& frame) {
    (void)portNum;
    const U64 frames = this->m_frames.fetch_add(1U) + 1U;
    const U8 expected = static_cast<U8>((1U << frame.get_sensorCount()) - 1U);
    if (frame.get_validMask() == expected) {
        this->m_complete.fetch_add(1U);
    } else {
        this->m_partial.fetch_add(1U);
    }
    // Every enabled trigger consumes a sequence number, so a gap is a skipped trigger
    if (this->m_haveSequence && (frame.get_sequence() != this->m_lastSequence + 1U)) {
        this->m_sequenceGaps.fetch_add(1U);
    }
    this->m_haveSequence = true;
    this->m_lastSequence = frame.get_sequence();

    const Adxl355::DriverStatus status = frame.get_sensorStatus()[0];
    if (status == Adxl355::DriverStatus::STALE_DATA) {
        this->m_stale.fetch_add(1U);
    } else if (status == Adxl355::DriverStatus::IMPLAUSIBLE_DATA) {
        this->m_implausible.fetch_add(1U);
    } else if (status == Adxl355::DriverStatus::BUSY) {
        this->m_busy.fetch_add(1U);
    } else if (status != Adxl355::DriverStatus::OK) {
        this->m_otherErrors.fetch_add(1U);
    }

    const U32 printEvery = this->m_printEvery.load();
    if ((printEvery != 0U) && ((frames % printEvery) == 0U)) {
        char name[24];
        TeBench::enumName(status, name, sizeof(name));
        const Adxl355::AccelerationSample& s = frame.get_samples()[0];
        printk("ADXL_FRAME,%llu,%llu,0x%02x,%s,%d,%d,%d,%.6f,%.6f,%.6f\n",
               static_cast<unsigned long long>(frame.get_sequence()),
               static_cast<unsigned long long>(frame.get_syncTimeMicroseconds()), frame.get_validMask(), name,
               s.get_rawX(), s.get_rawY(), s.get_rawZ(), s.get_xMetersPerSecondSquared() / STANDARD_GRAVITY,
               s.get_yMetersPerSecondSquared() / STANDARD_GRAVITY, s.get_zMetersPerSecondSquared() / STANDARD_GRAVITY);
    }
}

}  // namespace Adxl355Te0715
