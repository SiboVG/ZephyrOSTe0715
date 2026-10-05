// SPDX-License-Identifier: Apache-2.0
#include "Components/Client/Client.hpp"

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "Fw/Buffer/Buffer.hpp"
#include "TeBench/Support/EnumName.hpp"

namespace Ina229Te0715 {

Client::Client(const char* compName) : ClientComponentBase(compName) {}

Ina229::DriverStatus Client::configureSensor(const Ina229::DeviceConfig& config) {
    return this->configure_out(0, config);
}

Ina229::DriverStatus Client::readSensor(Ina229::Reading& reading) {
    return this->read_out(0, reading);
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

bool Client::startSampling(U32 periodTicks, U32 rows) {
    if ((periodTicks == 0U) || this->m_sampling.load()) {
        return false;
    }
    this->m_rows.store(0U);
    this->m_notReady.store(0U);
    this->m_failures.store(0U);
    this->m_periodTicks.store(periodTicks);
    this->m_rowLimit.store(rows);
    this->m_tick = 0U;
    this->m_sampling.store(true);
    return true;
}

void Client::stopSampling() {
    this->m_sampling.store(false);
}

Client::SamplingCounts Client::samplingCounts() const {
    return SamplingCounts{this->m_rows.load(), this->m_notReady.load(), this->m_failures.load()};
}

void Client::printHeader() {
    printk("INA_HEADER,time_ms,status,valid,bus_V,shunt_V,temp_C,current_A,power_W,energy_J,charge_C,diag\n");
}

void Client::printRow(U32 timeMs, const char* status, const Ina229::Reading& r) {
    printk("INA_ROW,%u,%s,0x%02x,%.6f,%.9f,%.4f,%.6f,%.6f,%.6f,%.6f,0x%04x\n", timeMs, status, r.get_validMask(),
           r.get_busVolts(), r.get_shuntVolts(), r.get_temperatureC(), r.get_currentAmps(), r.get_powerWatts(),
           r.get_energyJoules(), r.get_chargeCoulombs(), r.get_diagnostics());
}

void Client::run_handler(FwIndexType portNum, U32 context) {
    (void)portNum;
    (void)context;
    if (!this->m_sampling.load()) {
        return;
    }
    if (++this->m_tick < this->m_periodTicks.load()) {
        return;
    }
    this->m_tick = 0U;

    Ina229::Reading reading;
    const Ina229::DriverStatus status = this->read_out(0, reading);
    char name[24];
    TeBench::enumName(status, name, sizeof(name));
    const U32 now = k_uptime_get_32();
    if (status == Ina229::DriverStatus::NOT_READY) {
        this->m_notReady.fetch_add(1U);
        return;
    }
    if (status == Ina229::DriverStatus::OK) {
        printRow(now, name, reading);
        this->m_rows.fetch_add(1U);
    } else {
        this->m_failures.fetch_add(1U);
        printk("INA_ROW,%u,%s\n", now, name);
    }
    // A failed read is a printed row too, so a stream of failures also ends at the limit
    const U32 rows = this->m_rows.load();
    const U32 failures = this->m_failures.load();
    const U32 limit = this->m_rowLimit.load();
    if ((limit != 0U) && ((rows + failures) >= limit)) {
        this->m_sampling.store(false);
        printk("INA_STREAM_DONE rows=%u not_ready=%u failures=%u\n", rows, this->m_notReady.load(), failures);
    }
}

}  // namespace Ina229Te0715
