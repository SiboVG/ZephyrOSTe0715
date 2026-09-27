// SPDX-License-Identifier: Apache-2.0
//
// Shell commands of the INA229 bench. Output lines start with an INA_ marker and use
// key=value fields, so that app/scripts/sensor_bench.py can check them.

// F Prime headers before Zephyr's (see TeBench/ShellCommander/ShellCommander.hpp)
#include "TeBench/Support/BenchSpi.hpp"
#include "TeBench/Support/EnumName.hpp"
#include "TeBench/Support/bench_parse.h"
#include "Top/Ina229Te0715TopologyAc.hpp"
#include "bench_api.h"
#include "bench_revision.h"

#include <cstring>

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>

namespace {

using Ina229Te0715::client;
using Ina229Te0715::commander;
using Ina229Te0715::sensor;
using Ina229Te0715::spi;
using Ina229Te0715::tlmPrinter;

// SPI settings in use (requested clock and mode)
U32 g_spiHz = 0U;
U8 g_spiMode = 0U;

// Data sheet SLYS023A, 7.6.1: register addresses, names and widths in bytes
struct RegisterInfo {
    U8 address;
    const char* name;
    U8 bytes;
};
constexpr RegisterInfo REGISTERS[] = {
    {0x00, "CONFIG", 2},      {0x01, "ADC_CONFIG", 2},       {0x02, "SHUNT_CAL", 2}, {0x03, "SHUNT_TEMPCO", 2},
    {0x04, "VSHUNT", 3},      {0x05, "VBUS", 3},             {0x06, "DIETEMP", 2},   {0x07, "CURRENT", 3},
    {0x08, "POWER", 3},       {0x09, "ENERGY", 5},           {0x0A, "CHARGE", 5},    {0x0B, "DIAG_ALRT", 2},
    {0x0C, "SOVL", 2},        {0x0D, "SUVL", 2},             {0x0E, "BOVL", 2},      {0x0F, "BUVL", 2},
    {0x10, "TEMP_LIMIT", 2},  {0x11, "PWR_LIMIT", 2},        {0x3E, "MANUFACTURER_ID", 2},
    {0x3F, "DEVICE_ID", 2},
};
constexpr U8 MANUFACTURER_ID = 0x3E;
constexpr U8 DEVICE_ID = 0x3F;
constexpr U16 TI_MANUFACTURER = 0x5449;  // "TI"
constexpr U16 INA229_DIE = 0x229;        // DEVICE_ID bits 15..4

//! The manager's opcodes and channel IDs (relative to its base ID), which F Prime makes
//! protected in the generated base class. Never instantiated.
struct ManagerIds : Ina229::ManagerComponentBase {
    using ManagerComponentBase::CHANNELID_ERRORS;
    using ManagerComponentBase::CHANNELID_INITIALIZED;
    using ManagerComponentBase::CHANNELID_LASTSTATUS;
    using ManagerComponentBase::CHANNELID_MEASUREMENT;
    using ManagerComponentBase::CHANNELID_SAMPLES;
    using ManagerComponentBase::OPCODE_CLEAR_EVENT_THROTTLE;
    using ManagerComponentBase::OPCODE_CONFIGURE_ADC;
    using ManagerComponentBase::OPCODE_INITIALIZE;
    using ManagerComponentBase::OPCODE_READ_SNAPSHOT;
    using ManagerComponentBase::OPCODE_REPORT;
    using ManagerComponentBase::OPCODE_RESET_ACCUMULATORS;
    using ManagerComponentBase::OPCODE_SET_ALERT_CONFIG;
    using ManagerComponentBase::OPCODE_SET_THRESHOLD;
    using ManagerComponentBase::OPCODE_STOP;
    using ManagerComponentBase::OPCODE_TRIGGER;
};

const RegisterInfo* findRegister(U32 address) {
    for (const RegisterInfo& info : REGISTERS) {
        if (info.address == address) {
            return &info;
        }
    }
    return nullptr;
}

//! One register read straight over SPI: command byte (address, 0, R=1), then the
//! register bytes MSB first. lead is the byte clocked in with the command byte, which
//! the INA229 drives low (7.5.1).
struct RawRead {
    Drv::SpiStatus status = Drv::SpiStatus::SPI_OTHER_ERR;
    U8 lead = 0xFF;
    U64 value = 0U;
    U32 microseconds = 0U;
    U8 rx[6] = {};
};

RawRead rawRead(const RegisterInfo& info) {
    RawRead result;
    U8 tx[6] = {};
    tx[0] = static_cast<U8>((info.address << 2) | 1U);
    const FwSizeType size = static_cast<FwSizeType>(info.bytes + 1U);
    const U32 start = k_cycle_get_32();
    result.status = client.transfer(tx, result.rx, size);
    result.microseconds = k_cyc_to_us_floor32(k_cycle_get_32() - start);
    result.lead = result.rx[0];
    for (FwSizeType i = 1; i < size; i++) {
        result.value = (result.value << 8) | result.rx[i];
    }
    return result;
}

const char* spiStatusName(Drv::SpiStatus status) {
    static char name[24];
    TeBench::enumName(status, name, sizeof(name));
    return name;
}

//! Timing statistics in microseconds
struct Stats {
    U32 count = 0U;
    U32 min = UINT32_MAX;
    U32 max = 0U;
    U64 sum = 0U;
    void add(U32 us) {
        count++;
        min = (us < min) ? us : min;
        max = (us > max) ? us : max;
        sum += us;
    }
    U32 mean() const { return (count == 0U) ? 0U : static_cast<U32>(sum / count); }
    U32 minimum() const { return (count == 0U) ? 0U : min; }
};

//! <shunt_ohm> <max_current_a> [narrow] [tempcomp] [mode M] [conv BUS SHUNT TEMP] [avg A]
//! [tempco PPM] [delay STEPS]. Defaults: wide range, continuous all channels (mode 15),
//! 1052 us conversions (code 5) and 16 averages (code 2), i.e. about 50 ms per result.
bool parseConfig(const struct shell* sh, size_t argc, char** argv, Ina229::DeviceConfig& config) {
    if (argc < 2) {
        shell_error(sh, "need <shunt_ohm> <max_current_a>");
        return false;
    }
    double shunt = 0.0;
    double current = 0.0;
    if ((bench_parse_double(argv[0], 0.0, 1.0e6, &shunt) != 0) ||
        (bench_parse_double(argv[1], 0.0, 1.0e6, &current) != 0)) {
        shell_error(sh, "shunt and current must be numbers");
        return false;
    }
    bool narrow = false;
    bool tempComp = false;
    U32 mode = 15U, busTime = 5U, shuntTime = 5U, tempTime = 5U, averaging = 2U, tempco = 0U, delay = 0U;
    for (size_t i = 2; i < argc; i++) {
        const char* key = argv[i];
        const size_t left = argc - i - 1;
        int err = 0;
        if (strcmp(key, "narrow") == 0) {
            narrow = true;
        } else if (strcmp(key, "tempcomp") == 0) {
            tempComp = true;
        } else if ((strcmp(key, "mode") == 0) && (left >= 1)) {
            err = bench_parse_u32(argv[++i], 15U, &mode);
        } else if ((strcmp(key, "conv") == 0) && (left >= 3)) {
            err = bench_parse_u32(argv[i + 1], 7U, &busTime);
            err = (err == 0) ? bench_parse_u32(argv[i + 2], 7U, &shuntTime) : err;
            err = (err == 0) ? bench_parse_u32(argv[i + 3], 7U, &tempTime) : err;
            i += 3;
        } else if ((strcmp(key, "avg") == 0) && (left >= 1)) {
            err = bench_parse_u32(argv[++i], 7U, &averaging);
        } else if ((strcmp(key, "tempco") == 0) && (left >= 1)) {
            err = bench_parse_u32(argv[++i], 0x3FFFU, &tempco);
        } else if ((strcmp(key, "delay") == 0) && (left >= 1)) {
            err = bench_parse_u32(argv[++i], 0xFFU, &delay);
        } else {
            err = -1;
        }
        if (err != 0) {
            shell_error(sh, "bad option near '%s'", key);
            return false;
        }
    }
    config.set_shuntOhms(shunt);
    config.set_maxCurrent(current);
    config.set_narrowRange(narrow);
    config.set_temperatureCompensation(tempComp);
    config.set_conversionDelaySteps(static_cast<U8>(delay));
    config.set_shuntTempco(static_cast<U16>(tempco));
    config.set_mode(static_cast<U8>(mode));
    config.set_busTime(static_cast<U8>(busTime));
    config.set_shuntTime(static_cast<U8>(shuntTime));
    config.set_temperatureTime(static_cast<U8>(tempTime));
    config.set_averaging(static_cast<U8>(averaging));
    return true;
}

//! Read through the manager, polling NOT_READY every millisecond for up to timeoutMs
Ina229::DriverStatus readWhenReady(Ina229::Reading& reading, U32 timeoutMs) {
    const int64_t deadline = k_uptime_get() + timeoutMs;
    while (true) {
        const Ina229::DriverStatus status = client.readSensor(reading);
        if ((status != Ina229::DriverStatus::NOT_READY) || (k_uptime_get() >= deadline)) {
            return status;
        }
        k_msleep(1);
    }
}

bool formatReading(Fw::TlmBuffer& value, char* text, FwSizeType size) {
    Ina229::Reading r;
    if (r.deserializeFrom(value) != Fw::FW_SERIALIZE_OK) {
        return false;
    }
    (void)snprintf(text, size, "bus=%.6fV shunt=%.9fV temp=%.4fC current=%.6fA power=%.6fW valid=0x%02x diag=0x%04x",
                   r.get_busVolts(), r.get_shuntVolts(), r.get_temperatureC(), r.get_currentAmps(),
                   r.get_powerWatts(), r.get_validMask(), r.get_diagnostics());
    return true;
}

}  // namespace

extern "C" void ina_bench_register_telemetry(void) {
    using Base = ManagerIds;
    using Printer = TeBench::TlmPrinter;
    const FwChanIdType base = sensor.getIdBase();
    (void)tlmPrinter.add(base + Base::CHANNELID_INITIALIZED, "sensor.Initialized", Printer::formatUnsigned<U8>);
    (void)tlmPrinter.add(base + Base::CHANNELID_LASTSTATUS, "sensor.LastStatus",
                         Printer::formatSerializable<Ina229::DriverStatus>);
    (void)tlmPrinter.add(base + Base::CHANNELID_SAMPLES, "sensor.Samples", Printer::formatUnsigned<U64>);
    (void)tlmPrinter.add(base + Base::CHANNELID_ERRORS, "sensor.Errors", Printer::formatUnsigned<U64>);
    (void)tlmPrinter.add(base + Base::CHANNELID_MEASUREMENT, "sensor.Measurement", formatReading);
}

extern "C" void ina_bench_started(uint32_t spi_hz, uint8_t spi_mode) {
    g_spiHz = spi_hz;
    g_spiMode = spi_mode;
    printk("INA229 bench on the TE0715: bench %s, fprime-ina229 %s\n", BENCH_REVISION, LIBRARY_REVISION);
    printk("SPI1 on Pmod J1, CS MIO13: requested %u Hz, SCLK %u Hz, mode %u\n", g_spiHz,
           TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode);
    printk("[INA229_BENCH_READY]\n");
}

extern "C" int ina_cmd_info(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    shell_print(sh, "INA_INFO bench=%s library=%s spi_ref_hz=%u requested_hz=%u sclk_hz=%u mode=%u cs=MIO13 sampling=%d",
                BENCH_REVISION, LIBRARY_REVISION, TeBench::BenchSpi::referenceClockHz(), g_spiHz,
                TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode, client.isSampling() ? 1 : 0);
    return 0;
}

extern "C" int ina_cmd_spi(const struct shell* sh, size_t argc, char** argv) {
    if (argc == 1) {
        return ina_cmd_info(sh, argc, argv);
    }
    U32 hz = 0U;
    U32 mode = g_spiMode;
    if ((bench_parse_u32(argv[1], UINT32_MAX, &hz) != 0) || (TeBench::BenchSpi::actualSclkHz(hz) == 0U) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 3U, &mode) != 0))) {
        shell_error(sh, "usage: ina spi <hz %u..10000000> [mode 0..3]", TeBench::BenchSpi::minimumSclkHz());
        return -EINVAL;
    }
    if (client.isSampling()) {
        shell_error(sh, "stop the stream first (ina stream stop)");
        return -EBUSY;
    }
    g_spiHz = hz;
    g_spiMode = static_cast<U8>(mode);
    TeBench::BenchSpi::configure(spi, g_spiHz, g_spiMode);
    shell_print(sh, "INA_SPI requested_hz=%u sclk_hz=%u mode=%u", g_spiHz, TeBench::BenchSpi::actualSclkHz(g_spiHz),
                g_spiMode);
    return 0;
}

extern "C" int ina_cmd_id(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    const RawRead manufacturer = rawRead(*findRegister(MANUFACTURER_ID));
    const RawRead device = rawRead(*findRegister(DEVICE_ID));
    const bool pass = (manufacturer.status == Drv::SpiStatus::SPI_OK) && (device.status == Drv::SpiStatus::SPI_OK) &&
                      (manufacturer.lead == 0U) && (device.lead == 0U) && (manufacturer.value == TI_MANUFACTURER) &&
                      ((device.value >> 4) == INA229_DIE);
    shell_print(sh, "INA_ID manufacturer=0x%04x device=0x%04x die=0x%03x rev=%u lead=0x%02x/0x%02x spi=%s result=%s",
                static_cast<unsigned>(manufacturer.value), static_cast<unsigned>(device.value),
                static_cast<unsigned>(device.value >> 4), static_cast<unsigned>(device.value & 0xFU), manufacturer.lead,
                device.lead, spiStatusName(device.status), pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int ina_cmd_reg(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    U32 address = 0U;
    const RegisterInfo* info = nullptr;
    if ((bench_parse_u32(argv[1], 0x3FU, &address) != 0) || ((info = findRegister(address)) == nullptr)) {
        shell_error(sh, "unknown register; see data sheet 7.6.1");
        return -EINVAL;
    }
    const RawRead r = rawRead(*info);
    shell_print(sh, "INA_REG addr=0x%02x name=%s bytes=%u value=0x%0*llx lead=0x%02x spi=%s", info->address, info->name,
                info->bytes, info->bytes * 2, static_cast<unsigned long long>(r.value), r.lead,
                spiStatusName(r.status));
    return (r.status == Drv::SpiStatus::SPI_OK) ? 0 : -EIO;
}

extern "C" int ina_cmd_soak(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    U32 count = 0U;
    if ((bench_parse_u32(argv[1], 10000000U, &count) != 0) || (count == 0U)) {
        shell_error(sh, "usage: ina soak <transfers 1..10000000>");
        return -EINVAL;
    }
    // Alternate MANUFACTURER_ID and DEVICE_ID, so a byte left over from the previous
    // transfer, or a shifted frame, changes the value read
    const RegisterInfo& manufacturerInfo = *findRegister(MANUFACTURER_ID);
    const RegisterInfo& deviceInfo = *findRegister(DEVICE_ID);
    U32 badValue = 0U, badLead = 0U, spiErrors = 0U, reported = 0U;
    I32 revision = -1;
    Stats stats;
    for (U32 i = 0; i < count; i++) {
        const bool even = (i % 2U) == 0U;
        const RawRead r = rawRead(even ? manufacturerInfo : deviceInfo);
        bool bad = false;
        if (r.status != Drv::SpiStatus::SPI_OK) {
            spiErrors++;
            bad = true;
        } else {
            stats.add(r.microseconds);
            if (r.lead != 0U) {
                badLead++;
                bad = true;
            }
            if (even) {
                bad = bad || (r.value != TI_MANUFACTURER);
                badValue += (r.value != TI_MANUFACTURER) ? 1U : 0U;
            } else {
                if (revision < 0) {
                    revision = static_cast<I32>(r.value & 0xFU);
                }
                const bool wrong = ((r.value >> 4) != INA229_DIE) || (static_cast<I32>(r.value & 0xFU) != revision);
                badValue += wrong ? 1U : 0U;
                bad = bad || wrong;
            }
        }
        if (bad && (reported < 8U)) {
            reported++;
            shell_print(sh, "INA_SOAK_BAD i=%u reg=0x%02x spi=%s rx=%02x %02x %02x", i, even ? MANUFACTURER_ID : DEVICE_ID,
                        spiStatusName(r.status), r.rx[0], r.rx[1], r.rx[2]);
        }
    }
    const bool pass = (badValue == 0U) && (badLead == 0U) && (spiErrors == 0U);
    shell_print(sh,
                "INA_SOAK n=%u bad_value=%u bad_lead=%u spi_errors=%u min_us=%u mean_us=%u max_us=%u sclk_hz=%u mode=%u "
                "result=%s",
                count, badValue, badLead, spiErrors, stats.minimum(), stats.mean(), stats.max,
                TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode, pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int ina_cmd_init(const struct shell* sh, size_t argc, char** argv) {
    Ina229::DeviceConfig config;
    if (!parseConfig(sh, argc - 1, argv + 1, config)) {
        return -EINVAL;
    }
    const U32 start = k_uptime_get_32();
    const Ina229::DriverStatus status = client.configureSensor(config);
    char name[24];
    TeBench::enumName(status, name, sizeof(name));
    shell_print(sh, "INA_INIT status=%s ms=%u", name, k_uptime_get_32() - start);
    return (status == Ina229::DriverStatus::OK) ? 0 : -EIO;
}

extern "C" int ina_cmd_read(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 1U;
    U32 periodMs = 0U;
    if (((argc > 1) && ((bench_parse_u32(argv[1], 100000U, &count) != 0) || (count == 0U))) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 60000U, &periodMs) != 0))) {
        shell_error(sh, "usage: ina read [count 1..100000] [period_ms]");
        return -EINVAL;
    }
    Ina229Te0715::Client::printHeader();
    U32 ok = 0U, failures = 0U;
    for (U32 i = 0; i < count; i++) {
        Ina229::Reading reading;
        // The slowest configuration (4.12 ms x 3 channels x 1024 averages) takes 12.7 s
        const Ina229::DriverStatus status = readWhenReady(reading, 15000U);
        char name[24];
        TeBench::enumName(status, name, sizeof(name));
        if (status == Ina229::DriverStatus::OK) {
            ok++;
            Ina229Te0715::Client::printRow(k_uptime_get_32(), name, reading);
        } else {
            failures++;
            printk("INA_ROW,%u,%s\n", k_uptime_get_32(), name);
        }
        if ((periodMs > 0U) && (i + 1U < count)) {
            k_msleep(periodMs);
        }
    }
    shell_print(sh, "INA_READ_DONE ok=%u failures=%u", ok, failures);
    return (failures == 0U) ? 0 : -EIO;
}

extern "C" int ina_cmd_timing(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 200U;
    if ((argc > 1) && ((bench_parse_u32(argv[1], 100000U, &count) != 0) || (count == 0U))) {
        shell_error(sh, "usage: ina timing [ok_reads 1..100000]");
        return -EINVAL;
    }
    Stats ok, notReady, failed;
    const int64_t deadline = k_uptime_get() + 60000;
    while ((ok.count < count) && (k_uptime_get() < deadline)) {
        Ina229::Reading reading;
        const U32 start = k_cycle_get_32();
        const Ina229::DriverStatus status = client.readSensor(reading);
        const U32 us = k_cyc_to_us_floor32(k_cycle_get_32() - start);
        if (status == Ina229::DriverStatus::OK) {
            ok.add(us);
        } else if (status == Ina229::DriverStatus::NOT_READY) {
            notReady.add(us);
            k_usleep(200);
        } else {
            failed.add(us);
        }
    }
    shell_print(sh,
                "INA_TIMING ok_n=%u ok_min_us=%u ok_mean_us=%u ok_max_us=%u not_ready_n=%u not_ready_max_us=%u "
                "failed_n=%u sclk_hz=%u",
                ok.count, ok.minimum(), ok.mean(), ok.max, notReady.count, notReady.max, failed.count,
                TeBench::BenchSpi::actualSclkHz(g_spiHz));
    return ((ok.count == count) && (failed.count == 0U)) ? 0 : -EIO;
}

extern "C" int ina_cmd_stream_start(const struct shell* sh, size_t argc, char** argv) {
    U32 periodMs = 0U;
    U32 rows = 0U;
    if ((bench_parse_u32(argv[1], 60000U, &periodMs) != 0) || (periodMs < 10U) || ((periodMs % 10U) != 0U) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 1000000U, &rows) != 0))) {
        shell_error(sh, "usage: ina stream start <period_ms: multiple of 10> [rows, 0 = until stop]");
        return -EINVAL;
    }
    Ina229Te0715::Client::printHeader();
    if (!client.startSampling(periodMs / 10U, rows)) {
        shell_error(sh, "already streaming");
        return -EBUSY;
    }
    shell_print(sh, "INA_STREAM_STARTED period_ms=%u rows=%u", periodMs, rows);
    return 0;
}

extern "C" int ina_cmd_stream_stop(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    client.stopSampling();
    const Ina229Te0715::Client::SamplingCounts counts = client.samplingCounts();
    shell_print(sh, "INA_STREAM_STOPPED rows=%u not_ready=%u failures=%u", counts.rows, counts.notReady,
                counts.failures);
    return 0;
}

extern "C" int ina_cmd_stream_status(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    const Ina229Te0715::Client::SamplingCounts counts = client.samplingCounts();
    shell_print(sh, "INA_STREAM sampling=%d rows=%u not_ready=%u failures=%u", client.isSampling() ? 1 : 0, counts.rows,
                counts.notReady, counts.failures);
    return 0;
}

extern "C" int ina_cmd_fprime(const struct shell* sh, size_t argc, char** argv) {
    using Base = ManagerIds;
    const char* name = argv[1];
    const FwOpcodeType base = sensor.getIdBase();
    Fw::SerializeStatus ok = Fw::FW_SERIALIZE_OK;
    bool known = true;

    if (strcmp(name, "init") == 0) {
        Ina229::DeviceConfig config;
        if (!parseConfig(sh, argc - 2, argv + 2, config)) {
            return -EINVAL;
        }
        ok = config.serializeTo(commander.begin(base + Base::OPCODE_INITIALIZE));
    } else if ((strcmp(name, "adc") == 0) && (argc == 7)) {
        U32 v[5];
        for (size_t i = 0; i < 5; i++) {
            if (bench_parse_u32(argv[2 + i], 0xFFU, &v[i]) != 0) {
                shell_error(sh, "usage: ina cmd adc <mode> <bus> <shunt> <temp> <avg>");
                return -EINVAL;
            }
        }
        Fw::ComBuffer& args = commander.begin(base + Base::OPCODE_CONFIGURE_ADC);
        for (U32 value : v) {
            ok = (ok == Fw::FW_SERIALIZE_OK) ? args.serializeFrom(static_cast<U8>(value)) : ok;
        }
    } else if ((strcmp(name, "alert") == 0) && (argc == 3)) {
        U32 bits = 0U;
        if (bench_parse_u32(argv[2], 0xFFFFU, &bits) != 0) {
            shell_error(sh, "usage: ina cmd alert <bits 0..0xffff>");
            return -EINVAL;
        }
        ok = commander.begin(base + Base::OPCODE_SET_ALERT_CONFIG).serializeFrom(static_cast<U16>(bits));
    } else if ((strcmp(name, "threshold") == 0) && (argc == 4)) {
        U32 address = 0U;
        U32 raw = 0U;
        if ((bench_parse_u32(argv[2], 0xFFU, &address) != 0) || (bench_parse_u32(argv[3], 0xFFFFU, &raw) != 0)) {
            shell_error(sh, "usage: ina cmd threshold <addr> <raw>");
            return -EINVAL;
        }
        Fw::ComBuffer& args = commander.begin(base + Base::OPCODE_SET_THRESHOLD);
        ok = args.serializeFrom(static_cast<U8>(address));
        ok = (ok == Fw::FW_SERIALIZE_OK) ? args.serializeFrom(static_cast<U16>(raw)) : ok;
    } else if (argc == 2) {
        static const struct {
            const char* name;
            FwOpcodeType opcode;
        } simple[] = {
            {"trigger", Base::OPCODE_TRIGGER},
            {"stop", Base::OPCODE_STOP},
            {"reset-acc", Base::OPCODE_RESET_ACCUMULATORS},
            {"snapshot", Base::OPCODE_READ_SNAPSHOT},
            {"report", Base::OPCODE_REPORT},
            {"clear-throttle", Base::OPCODE_CLEAR_EVENT_THROTTLE},
        };
        known = false;
        for (const auto& entry : simple) {
            if (strcmp(name, entry.name) == 0) {
                (void)commander.begin(base + entry.opcode);
                known = true;
                break;
            }
        }
    } else {
        known = false;
    }
    if (!known) {
        shell_error(sh,
                    "commands: init <shunt> <imax> [options], adc <mode> <bus> <shunt> <temp> <avg>, trigger, stop, "
                    "reset-acc, alert <bits>, threshold <addr> <raw>, snapshot, report, clear-throttle");
        return -EINVAL;
    }
    if (ok != Fw::FW_SERIALIZE_OK) {
        shell_error(sh, "arguments do not fit a command packet");
        return -EINVAL;
    }
    Fw::CmdResponse response;
    if (!commander.send(5000U, response)) {
        shell_print(sh, "INA_CMD %s response=TIMEOUT", name);
        return -ETIMEDOUT;
    }
    char text[24];
    TeBench::enumName(response, text, sizeof(text));
    shell_print(sh, "INA_CMD %s response=%s", name, text);
    return (response == Fw::CmdResponse::OK) ? 0 : -EIO;
}

extern "C" int ina_cmd_tlm(const struct shell* sh, size_t argc, char** argv) {
    bool on = tlmPrinter.isEnabled();
    if ((argc > 1) && (bench_parse_bool(argv[1], &on) != 0)) {
        shell_error(sh, "usage: ina tlm [on|off]");
        return -EINVAL;
    }
    tlmPrinter.setEnabled(on);
    shell_print(sh, "INA_TLM printing=%s unprinted=%u", on ? "on" : "off", tlmPrinter.unprintedCount());
    return 0;
}
