// SPDX-License-Identifier: Apache-2.0
//
// Shell commands and frame timing thread of the ADXL355 bench. Output lines start
// with an ADXL_ marker and use key=value fields, so that app/scripts/sensor_bench.py
// can check them.

// F Prime headers before Zephyr's (see TeBench/ShellCommander/ShellCommander.hpp)
#include "TeBench/Support/BenchSpi.hpp"
#include "TeBench/Support/EnumName.hpp"
#include "TeBench/Support/bench_parse.h"
#include "Top/Adxl355Te0715TopologyAc.hpp"
#include "bench_api.h"
#include "bench_revision.h"

#include <atomic>
#include <cmath>
#include <cstring>

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>

namespace {

using Adxl355Te0715::app;
using Adxl355Te0715::client;
using Adxl355Te0715::commander;
using Adxl355Te0715::sensor;
using Adxl355Te0715::spi;
using Adxl355Te0715::tlmPrinter;

constexpr F64 STANDARD_GRAVITY = 9.80665;

// SPI settings in use (requested clock and mode), and the output data rate of the last
// successful initialization (OutputDataRate code: 4000 Hz / 2^code)
U32 g_spiHz = 0U;
U8 g_spiMode = 0U;
U32 g_odrCode = 5U;

//! The manager's and the application's opcodes and channel IDs (relative to their base
//! IDs), which F Prime makes protected in the generated base classes. Never instantiated.
struct ManagerIds : Adxl355::ManagerComponentBase {
    using ManagerComponentBase::CHANNELID_ACCELERATIONX;
    using ManagerComponentBase::CHANNELID_ACCELERATIONY;
    using ManagerComponentBase::CHANNELID_ACCELERATIONZ;
    using ManagerComponentBase::CHANNELID_ERRORS;
    using ManagerComponentBase::CHANNELID_INITIALIZED;
    using ManagerComponentBase::CHANNELID_LASTSTATUS;
    using ManagerComponentBase::CHANNELID_MEASURING;
    using ManagerComponentBase::CHANNELID_RAWX;
    using ManagerComponentBase::CHANNELID_RAWY;
    using ManagerComponentBase::CHANNELID_RAWZ;
    using ManagerComponentBase::CHANNELID_SAMPLESREAD;
    using ManagerComponentBase::CHANNELID_SELFTEST;
    using ManagerComponentBase::CHANNELID_STATUSREGISTER;
    using ManagerComponentBase::CHANNELID_TEMPERATURECELSIUS;
    using ManagerComponentBase::OPCODE_CLEAR_EVENT_THROTTLE;
    using ManagerComponentBase::OPCODE_INITIALIZE_SYNCED;
    using ManagerComponentBase::OPCODE_READ_SNAPSHOT;
    using ManagerComponentBase::OPCODE_SET_ACTIVITY;
    using ManagerComponentBase::OPCODE_SET_FIFO_WATERMARK;
    using ManagerComponentBase::OPCODE_SET_FILTER;
    using ManagerComponentBase::OPCODE_SET_INTERRUPTS;
    using ManagerComponentBase::OPCODE_SET_OFFSETS;
    using ManagerComponentBase::OPCODE_SET_RANGE;
    using ManagerComponentBase::OPCODE_SET_SELF_TEST;
    using ManagerComponentBase::OPCODE_SET_SYNC;
    using ManagerComponentBase::OPCODE_START;
    using ManagerComponentBase::OPCODE_STOP;
};

struct AppIds : Adxl355::SynchronizedApplicationComponentBase {
    using SynchronizedApplicationComponentBase::CHANNELID_ENABLED;
    using SynchronizedApplicationComponentBase::CHANNELID_FRAMES;
    using SynchronizedApplicationComponentBase::CHANNELID_INITIALIZEDMASK;
    using SynchronizedApplicationComponentBase::CHANNELID_LASTVALIDMASK;
    using SynchronizedApplicationComponentBase::CHANNELID_PARTIALFRAMES;
    using SynchronizedApplicationComponentBase::CHANNELID_SENSORCOUNT;
    using SynchronizedApplicationComponentBase::CHANNELID_SKIPPEDTRIGGERS;
    using SynchronizedApplicationComponentBase::OPCODE_CLEAR_EVENT_THROTTLE;
    using SynchronizedApplicationComponentBase::OPCODE_INITIALIZE_ALL;
    using SynchronizedApplicationComponentBase::OPCODE_INITIALIZE_ALL_INTERNAL;
    using SynchronizedApplicationComponentBase::OPCODE_REPORT;
    using SynchronizedApplicationComponentBase::OPCODE_SET_ENABLED;
    using SynchronizedApplicationComponentBase::OPCODE_SET_SENSOR_COUNT;
};

// ---------------------------------------------------------------------------------
// Raw SPI: command byte (address << 1 | R), then the register bytes, auto-incrementing
// ---------------------------------------------------------------------------------

constexpr U8 DEVID_AD = 0xAD;
constexpr U8 DEVID_MST = 0x1D;
constexpr U8 PARTID = 0xED;
constexpr FwSizeType MAX_RAW_BYTES = 16U;

struct RawRead {
    Drv::SpiStatus status = Drv::SpiStatus::SPI_OTHER_ERR;
    U32 microseconds = 0U;
    U8 rx[MAX_RAW_BYTES + 1U] = {};
};

RawRead rawRead(U8 address, FwSizeType count) {
    RawRead result;
    U8 tx[MAX_RAW_BYTES + 1U] = {};
    tx[0] = static_cast<U8>((address << 1) | 1U);
    const U32 start = k_cycle_get_32();
    result.status = client.transfer(tx, result.rx, count + 1U);
    result.microseconds = k_cyc_to_us_floor32(k_cycle_get_32() - start);
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

// ---------------------------------------------------------------------------------
// Configuration arguments
// ---------------------------------------------------------------------------------

U32 odrPeriodUs(U32 code) {
    return 250U << code;  // 1 / (4000 Hz / 2^code)
}

bool parseRange(const char* text, Adxl355::SensorRange& range) {
    if (strcmp(text, "2") == 0) {
        range = Adxl355::SensorRange::G2;
    } else if (strcmp(text, "4") == 0) {
        range = Adxl355::SensorRange::G4;
    } else if (strcmp(text, "8") == 0) {
        range = Adxl355::SensorRange::G8;
    } else {
        return false;
    }
    return true;
}

//! An output data rate in Hz (4000, 2000, ..., 3.906): Register 0x28, ODR_LPF
bool parseOdr(const char* text, U32& code) {
    double hz = 0.0;
    if (bench_parse_double(text, 1.0, 4000.0, &hz) != 0) {
        return false;
    }
    for (U32 c = 0U; c <= 10U; c++) {
        const double rate = 4000.0 / static_cast<double>(1U << c);
        if (std::fabs(rate - hz) <= 0.01 * rate) {
            code = c;
            return true;
        }
    }
    return false;
}

bool parseHpf(const char* text, U32& code) {
    return bench_parse_u32(text, 6U, &code) == 0;
}

//! [range 2|4|8] [odr_hz] [hpf 0..6], defaults +/-2 g, 125 Hz, high-pass filter off
bool parseSampling(const struct shell* sh, size_t argc, char** argv, Adxl355::SensorRange& range, U32& odr, U32& hpf) {
    range = Adxl355::SensorRange::G2;
    odr = 5U;
    hpf = 0U;
    if (((argc > 0) && !parseRange(argv[0], range)) || ((argc > 1) && !parseOdr(argv[1], odr)) ||
        ((argc > 2) && !parseHpf(argv[2], hpf))) {
        shell_error(sh, "arguments: [range 2|4|8] [odr_hz 4000..3.906] [hpf 0..6]");
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------------
// Reads through the manager
// ---------------------------------------------------------------------------------

//! Wait one output data period after the previous sample, then read; a sample that is
//! not yet new (STALE_DATA) is retried every 1/8 period for up to two periods. Waiting
//! first keeps the manager from counting routine STALE_DATA polls as errors.
Adxl355::DriverStatus readFresh(Adxl355::AccelerationSample& sample, int64_t& lastOkUs) {
    const U32 period = odrPeriodUs(g_odrCode);
    const int64_t now = static_cast<int64_t>(k_cyc_to_us_floor64(k_cycle_get_64()));
    const int64_t due = lastOkUs + period + period / 16;
    if (now < due) {
        k_usleep(static_cast<int32_t>(due - now));
    }
    const int64_t deadline = static_cast<int64_t>(k_cyc_to_us_floor64(k_cycle_get_64())) + 2 * period;
    while (true) {
        const Adxl355::DriverStatus status = client.readSensor(sample);
        const int64_t t = static_cast<int64_t>(k_cyc_to_us_floor64(k_cycle_get_64()));
        if (status == Adxl355::DriverStatus::OK) {
            lastOkUs = t;
            return status;
        }
        if (((status != Adxl355::DriverStatus::STALE_DATA) && (status != Adxl355::DriverStatus::BUSY)) ||
            (t >= deadline)) {
            return status;
        }
        k_usleep(static_cast<int32_t>((period / 8U) > 50U ? period / 8U : 50U));
    }
}

struct AxisStats {
    U32 n = 0U;
    F64 sum[3] = {0.0, 0.0, 0.0};
    F64 sumSq[3] = {0.0, 0.0, 0.0};
    void add(const Adxl355::AccelerationSample& s) {
        const F64 g[3] = {s.get_xMetersPerSecondSquared() / STANDARD_GRAVITY,
                          s.get_yMetersPerSecondSquared() / STANDARD_GRAVITY,
                          s.get_zMetersPerSecondSquared() / STANDARD_GRAVITY};
        for (U32 i = 0; i < 3U; i++) {
            sum[i] += g[i];
            sumSq[i] += g[i] * g[i];
        }
        n++;
    }
    F64 mean(U32 i) const { return (n == 0U) ? 0.0 : sum[i] / n; }
    F64 stdDev(U32 i) const {
        if (n < 2U) {
            return 0.0;
        }
        const F64 m = mean(i);
        const F64 variance = (sumSq[i] - n * m * m) / (n - 1U);
        return (variance > 0.0) ? std::sqrt(variance) : 0.0;
    }
    F64 magnitude() const { return std::sqrt(mean(0) * mean(0) + mean(1) * mean(1) + mean(2) * mean(2)); }
};

//! Average count fresh samples; returns false on any read failure
bool average(U32 count, AxisStats& stats, Adxl355::DriverStatus& failure) {
    int64_t lastOk = 0;
    for (U32 i = 0; i < count; i++) {
        Adxl355::AccelerationSample sample;
        const Adxl355::DriverStatus status = readFresh(sample, lastOk);
        if (status != Adxl355::DriverStatus::OK) {
            failure = status;
            return false;
        }
        stats.add(sample);
    }
    return true;
}

// ---------------------------------------------------------------------------------
// Commands through the dispatcher
// ---------------------------------------------------------------------------------

bool sendCommand(const struct shell* sh, const char* name, Fw::CmdResponse& response) {
    if (!commander.send(10000U, response)) {
        shell_print(sh, "ADXL_CMD %s response=TIMEOUT", name);
        return false;
    }
    char text[24];
    TeBench::enumName(response, text, sizeof(text));
    shell_print(sh, "ADXL_CMD %s response=%s", name, text);
    return response == Fw::CmdResponse::OK;
}

bool setSelfTest(const struct shell* sh, bool enableMode, bool applyForce) {
    Fw::ComBuffer& args = commander.begin(sensor.getIdBase() + ManagerIds::OPCODE_SET_SELF_TEST);
    (void)args.serializeFrom(enableMode);
    (void)args.serializeFrom(applyForce);
    Fw::CmdResponse response;
    return sendCommand(sh, "selftest", response);
}

bool setEnabled(const struct shell* sh, bool enabled) {
    Fw::ComBuffer& args = commander.begin(app.getIdBase() + AppIds::OPCODE_SET_ENABLED);
    (void)args.serializeFrom(enabled);
    Fw::CmdResponse response;
    return sendCommand(sh, "app-enable", response);
}

// ---------------------------------------------------------------------------------
// Frame timing thread: stands in for the FPGA synchronization source
// ---------------------------------------------------------------------------------

K_THREAD_STACK_DEFINE(g_timingStack, 8192);
struct k_thread g_timingThread;
struct k_timer g_frameTimer;
struct k_sem g_streamStart;
std::atomic<bool> g_streaming{false};
std::atomic<U64> g_frameLimit{0U};
std::atomic<U64> g_triggers{0U};
std::atomic<U64> g_missedTicks{0U};
std::atomic<U32> g_acqMin{UINT32_MAX};
std::atomic<U32> g_acqMax{0U};
std::atomic<U64> g_acqSum{0U};
U32 g_periodUs = 0U;

void timingThread(void* p1, void* p2, void* p3) {
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);
    while (true) {
        (void)k_sem_take(&g_streamStart, K_FOREVER);
        while (g_streaming.load()) {
            const U32 expiries = k_timer_status_sync(&g_frameTimer);
            if (!g_streaming.load() || (expiries == 0U)) {
                break;  // stopped
            }
            if (expiries > 1U) {
                g_missedTicks.fetch_add(expiries - 1U);
            }
            const U64 syncUs = k_cyc_to_us_floor64(k_cycle_get_64());
            const U32 start = k_cycle_get_32();
            client.acquire(syncUs);
            const U32 us = k_cyc_to_us_floor32(k_cycle_get_32() - start);
            if (us < g_acqMin.load()) {
                g_acqMin.store(us);
            }
            if (us > g_acqMax.load()) {
                g_acqMax.store(us);
            }
            g_acqSum.fetch_add(us);
            const U64 triggers = g_triggers.fetch_add(1U) + 1U;
            const U64 limit = g_frameLimit.load();
            if ((limit != 0U) && (triggers >= limit)) {
                g_streaming.store(false);
                k_timer_stop(&g_frameTimer);
                printk("ADXL_STREAM_DONE triggers=%llu\n", static_cast<unsigned long long>(triggers));
            }
        }
    }
}

void printStreamStats(const struct shell* sh, const char* marker) {
    const Adxl355Te0715::Client::FrameStats f = client.frameStats();
    const U64 triggers = g_triggers.load();
    const U32 min = (triggers == 0U) ? 0U : g_acqMin.load();
    const U32 mean = (triggers == 0U) ? 0U : static_cast<U32>(g_acqSum.load() / triggers);
    shell_print(sh,
                "%s triggers=%llu frames=%llu complete=%llu partial=%llu stale=%llu implausible=%llu busy=%llu "
                "other=%llu seq_gaps=%llu missed_ticks=%llu acq_min_us=%u acq_mean_us=%u acq_max_us=%u period_us=%u "
                "streaming=%d",
                marker, static_cast<unsigned long long>(triggers), static_cast<unsigned long long>(f.frames),
                static_cast<unsigned long long>(f.complete), static_cast<unsigned long long>(f.partial),
                static_cast<unsigned long long>(f.stale), static_cast<unsigned long long>(f.implausible),
                static_cast<unsigned long long>(f.busy), static_cast<unsigned long long>(f.otherErrors),
                static_cast<unsigned long long>(f.sequenceGaps),
                static_cast<unsigned long long>(g_missedTicks.load()), min, mean, g_acqMax.load(), g_periodUs,
                g_streaming.load() ? 1 : 0);
}

}  // namespace

extern "C" void adxl_bench_register_telemetry(void) {
    using M = ManagerIds;
    using A = AppIds;
    using P = TeBench::TlmPrinter;
    const FwChanIdType m = sensor.getIdBase();
    const FwChanIdType a = app.getIdBase();
    (void)tlmPrinter.add(m + M::CHANNELID_INITIALIZED, "sensor.Initialized", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(m + M::CHANNELID_MEASURING, "sensor.Measuring", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(m + M::CHANNELID_LASTSTATUS, "sensor.LastStatus",
                         P::formatSerializable<Adxl355::DriverStatus>);
    (void)tlmPrinter.add(m + M::CHANNELID_STATUSREGISTER, "sensor.StatusRegister", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(m + M::CHANNELID_RAWX, "sensor.RawX", P::formatSigned<I32>);
    (void)tlmPrinter.add(m + M::CHANNELID_RAWY, "sensor.RawY", P::formatSigned<I32>);
    (void)tlmPrinter.add(m + M::CHANNELID_RAWZ, "sensor.RawZ", P::formatSigned<I32>);
    (void)tlmPrinter.add(m + M::CHANNELID_ACCELERATIONX, "sensor.AccelerationX", P::formatF64);
    (void)tlmPrinter.add(m + M::CHANNELID_ACCELERATIONY, "sensor.AccelerationY", P::formatF64);
    (void)tlmPrinter.add(m + M::CHANNELID_ACCELERATIONZ, "sensor.AccelerationZ", P::formatF64);
    (void)tlmPrinter.add(m + M::CHANNELID_TEMPERATURECELSIUS, "sensor.TemperatureCelsius", P::formatF64);
    (void)tlmPrinter.add(m + M::CHANNELID_SAMPLESREAD, "sensor.SamplesRead", P::formatUnsigned<U64>);
    (void)tlmPrinter.add(m + M::CHANNELID_ERRORS, "sensor.Errors", P::formatUnsigned<U64>);
    (void)tlmPrinter.add(m + M::CHANNELID_SELFTEST, "sensor.SelfTest", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(a + A::CHANNELID_FRAMES, "app.Frames", P::formatUnsigned<U64>);
    (void)tlmPrinter.add(a + A::CHANNELID_PARTIALFRAMES, "app.PartialFrames", P::formatUnsigned<U64>);
    (void)tlmPrinter.add(a + A::CHANNELID_LASTVALIDMASK, "app.LastValidMask", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(a + A::CHANNELID_SENSORCOUNT, "app.SensorCount", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(a + A::CHANNELID_ENABLED, "app.Enabled", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(a + A::CHANNELID_INITIALIZEDMASK, "app.InitializedMask", P::formatUnsigned<U8>);
    (void)tlmPrinter.add(a + A::CHANNELID_SKIPPEDTRIGGERS, "app.SkippedTriggers", P::formatUnsigned<U64>);
}

extern "C" void adxl_bench_started(uint32_t spi_hz, uint8_t spi_mode, bool app_configured) {
    g_spiHz = spi_hz;
    g_spiMode = spi_mode;
    k_timer_init(&g_frameTimer, nullptr, nullptr);
    k_sem_init(&g_streamStart, 0, 1);
    const k_tid_t tid = k_thread_create(&g_timingThread, g_timingStack, K_THREAD_STACK_SIZEOF(g_timingStack),
                                        timingThread, nullptr, nullptr, nullptr, CONFIG_APP_TIMING_THREAD_PRIORITY,
                                        0, K_NO_WAIT);
    k_thread_name_set(tid, "frame_timing");
    printk("ADXL355 bench on the TE0715: bench %s, fprime-adxl355 %s\n", BENCH_REVISION, LIBRARY_REVISION);
    printk("SPI1 on Pmod J1, CS MIO13: requested %u Hz, SCLK %u Hz, mode %u\n", g_spiHz,
           TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode);
    if (!app_configured) {
        printk("*** SynchronizedApplication refused sensor count 1 ***\n");
    }
    printk("[ADXL355_BENCH_READY]\n");
}

extern "C" int adxl_cmd_info(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    shell_print(sh,
                "ADXL_INFO bench=%s library=%s spi_ref_hz=%u requested_hz=%u sclk_hz=%u mode=%u cs=MIO13 odr_code=%u "
                "streaming=%d",
                BENCH_REVISION, LIBRARY_REVISION, TeBench::BenchSpi::referenceClockHz(), g_spiHz,
                TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode, g_odrCode, g_streaming.load() ? 1 : 0);
    return 0;
}

extern "C" int adxl_cmd_spi(const struct shell* sh, size_t argc, char** argv) {
    if (argc == 1) {
        return adxl_cmd_info(sh, argc, argv);
    }
    U32 hz = 0U;
    U32 mode = g_spiMode;
    if ((bench_parse_u32(argv[1], UINT32_MAX, &hz) != 0) || (TeBench::BenchSpi::actualSclkHz(hz) == 0U) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 3U, &mode) != 0))) {
        shell_error(sh, "usage: adxl spi <hz %u..10000000> [mode 0..3]", TeBench::BenchSpi::minimumSclkHz());
        return -EINVAL;
    }
    if (g_streaming.load()) {
        shell_error(sh, "stop the stream first (adxl stream stop)");
        return -EBUSY;
    }
    g_spiHz = hz;
    g_spiMode = static_cast<U8>(mode);
    TeBench::BenchSpi::configure(spi, g_spiHz, g_spiMode);
    shell_print(sh, "ADXL_SPI requested_hz=%u sclk_hz=%u mode=%u", g_spiHz, TeBench::BenchSpi::actualSclkHz(g_spiHz),
                g_spiMode);
    return 0;
}

extern "C" int adxl_cmd_id(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    const RawRead r = rawRead(0x00U, 4U);
    const bool pass = (r.status == Drv::SpiStatus::SPI_OK) && (r.rx[1] == DEVID_AD) && (r.rx[2] == DEVID_MST) &&
                      (r.rx[3] == PARTID);
    shell_print(sh, "ADXL_ID devid_ad=0x%02x devid_mst=0x%02x partid=0x%02x revid=0x%02x spi=%s result=%s", r.rx[1],
                r.rx[2], r.rx[3], r.rx[4], spiStatusName(r.status), pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int adxl_cmd_reg(const struct shell* sh, size_t argc, char** argv) {
    U32 address = 0U;
    U32 count = 1U;
    if ((bench_parse_u32(argv[1], 0x7FU, &address) != 0) ||
        ((argc > 2) && ((bench_parse_u32(argv[2], MAX_RAW_BYTES, &count) != 0) || (count == 0U)))) {
        shell_error(sh, "usage: adxl reg <addr 0..0x7f> [count 1..%u]", static_cast<unsigned>(MAX_RAW_BYTES));
        return -EINVAL;
    }
    const RawRead r = rawRead(static_cast<U8>(address), count);
    char hex[3 * MAX_RAW_BYTES + 1U] = {};
    for (U32 i = 0; i < count; i++) {
        (void)snprintf(&hex[3U * i], 4U, "%02x ", r.rx[1U + i]);
    }
    shell_print(sh, "ADXL_REG addr=0x%02x count=%u bytes=%s spi=%s", address, count, hex, spiStatusName(r.status));
    return (r.status == Drv::SpiStatus::SPI_OK) ? 0 : -EIO;
}

extern "C" int adxl_cmd_soak(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    U32 count = 0U;
    if ((bench_parse_u32(argv[1], 10000000U, &count) != 0) || (count == 0U)) {
        shell_error(sh, "usage: adxl soak <transfers 1..10000000>");
        return -EINVAL;
    }
    // Alternate a 4-byte read from 0x00 (DEVID_AD, DEVID_MST, PARTID, REVID) and a
    // 2-byte read from 0x01 (DEVID_MST, PARTID), so a left-over byte or a shifted frame
    // changes what is read
    U32 badValue = 0U, spiErrors = 0U, reported = 0U;
    I32 revision = -1;
    Stats stats;
    for (U32 i = 0; i < count; i++) {
        const bool even = (i % 2U) == 0U;
        const RawRead r = even ? rawRead(0x00U, 4U) : rawRead(0x01U, 2U);
        bool bad = false;
        if (r.status != Drv::SpiStatus::SPI_OK) {
            spiErrors++;
            bad = true;
        } else {
            stats.add(r.microseconds);
            if (even) {
                if (revision < 0) {
                    revision = r.rx[4];
                }
                bad = (r.rx[1] != DEVID_AD) || (r.rx[2] != DEVID_MST) || (r.rx[3] != PARTID) ||
                      (static_cast<I32>(r.rx[4]) != revision);
            } else {
                bad = (r.rx[1] != DEVID_MST) || (r.rx[2] != PARTID);
            }
            badValue += bad ? 1U : 0U;
        }
        if (bad && (reported < 8U)) {
            reported++;
            shell_print(sh, "ADXL_SOAK_BAD i=%u spi=%s rx=%02x %02x %02x %02x %02x", i, spiStatusName(r.status), r.rx[0],
                        r.rx[1], r.rx[2], r.rx[3], r.rx[4]);
        }
    }
    const bool pass = (badValue == 0U) && (spiErrors == 0U);
    shell_print(sh,
                "ADXL_SOAK n=%u bad_value=%u spi_errors=%u min_us=%u mean_us=%u max_us=%u sclk_hz=%u mode=%u "
                "result=%s",
                count, badValue, spiErrors, stats.minimum(), stats.mean(), stats.max,
                TeBench::BenchSpi::actualSclkHz(g_spiHz), g_spiMode, pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int adxl_cmd_drdy(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 20U;
    if ((argc > 1) && ((bench_parse_u32(argv[1], 1000U, &count) != 0) || (count == 0U))) {
        shell_error(sh, "usage: adxl drdy [n 1..1000]");
        return -EINVAL;
    }
    if (g_streaming.load()) {
        shell_error(sh, "stop the stream first (adxl stream stop)");
        return -EBUSY;
    }
    // Two STATUS reads back to back, once per output data period: bits 7:5 are reserved
    // and read 0, and a STATUS read clears DATA_RDY (data sheet Table 15; ADXL-INT-008)
    constexpr U8 STATUS = 0x04U;
    U32 readyFirst = 0U, clearedSecond = 0U, reserved = 0U, spiErrors = 0U;
    for (U32 i = 0; i < count; i++) {
        k_usleep(static_cast<int32_t>(odrPeriodUs(g_odrCode) + odrPeriodUs(g_odrCode) / 8U));
        const RawRead first = rawRead(STATUS, 1U);
        const RawRead second = rawRead(STATUS, 1U);
        if ((first.status != Drv::SpiStatus::SPI_OK) || (second.status != Drv::SpiStatus::SPI_OK)) {
            spiErrors++;
            continue;
        }
        reserved += (((first.rx[1] | second.rx[1]) & 0xE0U) != 0U) ? 1U : 0U;
        if ((first.rx[1] & 0x01U) != 0U) {
            readyFirst++;
            clearedSecond += ((second.rx[1] & 0x01U) == 0U) ? 1U : 0U;
        }
    }
    const bool pass = (spiErrors == 0U) && (reserved == 0U) && (readyFirst > 0U) && (clearedSecond == readyFirst);
    shell_print(sh, "ADXL_DRDY n=%u ready_first=%u cleared_second=%u reserved_set=%u spi_errors=%u result=%s", count,
                readyFirst, clearedSecond, reserved, spiErrors, pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int adxl_cmd_init(const struct shell* sh, size_t argc, char** argv) {
    Adxl355::SensorRange range;
    U32 odr = 0U;
    U32 hpf = 0U;
    if (!parseSampling(sh, argc - 1, argv + 1, range, odr, hpf)) {
        return -EINVAL;
    }
    if (g_streaming.load()) {
        shell_error(sh, "stop the stream first (adxl stream stop)");
        return -EBUSY;
    }
    // The configuration of the application's INITIALIZE_ALL_INTERNAL: internal clock and
    // synchronization, temperature and DRDY on, no interrupts, FIFO watermark 96
    const Adxl355::DeviceConfiguration configuration(
        range, static_cast<Adxl355::OutputDataRate::T>(odr), static_cast<Adxl355::HighPassCorner::T>(hpf),
        Adxl355::SynchronizationMode::INTERNAL, false, true, true, false, 0U, 96U);
    const U32 start = k_uptime_get_32();
    const Adxl355::DriverStatus status = client.configureSensor(configuration);
    char name[24];
    TeBench::enumName(status, name, sizeof(name));
    if (status == Adxl355::DriverStatus::OK) {
        g_odrCode = odr;
    }
    shell_print(sh, "ADXL_INIT status=%s ms=%u odr_hz=%.3f", name, k_uptime_get_32() - start,
                4000.0 / static_cast<double>(1U << odr));
    return (status == Adxl355::DriverStatus::OK) ? 0 : -EIO;
}

extern "C" int adxl_cmd_measure(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    bool on = false;
    if (bench_parse_bool(argv[1], &on) != 0) {
        shell_error(sh, "usage: adxl measure on|off");
        return -EINVAL;
    }
    const Adxl355::DriverStatus status = client.setMeasurement(on);
    char name[24];
    TeBench::enumName(status, name, sizeof(name));
    shell_print(sh, "ADXL_MEASURE on=%d status=%s", on ? 1 : 0, name);
    return (status == Adxl355::DriverStatus::OK) ? 0 : -EIO;
}

extern "C" int adxl_cmd_read(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 1U;
    U32 printRows = 1U;
    if (((argc > 1) && ((bench_parse_u32(argv[1], 100000U, &count) != 0) || (count == 0U))) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 1U, &printRows) != 0))) {
        shell_error(sh, "usage: adxl read [count 1..100000] [rows 0|1]");
        return -EINVAL;
    }
    if (printRows != 0U) {
        Adxl355Te0715::Client::printHeader();
    }
    AxisStats stats;
    U32 failures = 0U;
    int64_t lastOk = 0;
    for (U32 i = 0; i < count; i++) {
        Adxl355::AccelerationSample sample;
        const Adxl355::DriverStatus status = readFresh(sample, lastOk);
        char name[24];
        TeBench::enumName(status, name, sizeof(name));
        if (status == Adxl355::DriverStatus::OK) {
            stats.add(sample);
            if (printRows != 0U) {
                Adxl355Te0715::Client::printRow(k_uptime_get_32(), name, sample);
            }
        } else {
            failures++;
            printk("ADXL_ROW,%u,%s\n", k_uptime_get_32(), name);
        }
    }
    shell_print(sh,
                "ADXL_READ_DONE ok=%u failures=%u mean_x_g=%.6f mean_y_g=%.6f mean_z_g=%.6f std_x_mg=%.4f "
                "std_y_mg=%.4f std_z_mg=%.4f magnitude_g=%.6f odr_hz=%.3f",
                stats.n, failures, stats.mean(0), stats.mean(1), stats.mean(2), 1000.0 * stats.stdDev(0),
                1000.0 * stats.stdDev(1), 1000.0 * stats.stdDev(2), stats.magnitude(),
                4000.0 / static_cast<double>(1U << g_odrCode));
    return (failures == 0U) ? 0 : -EIO;
}

extern "C" int adxl_cmd_temp(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 1U;
    if ((argc > 1) && ((bench_parse_u32(argv[1], 1000U, &count) != 0) || (count == 0U))) {
        shell_error(sh, "usage: adxl temp [count 1..1000]");
        return -EINVAL;
    }
    U32 failures = 0U;
    for (U32 i = 0; i < count; i++) {
        Adxl355::TemperatureSample sample;
        const Adxl355::DriverStatus status = client.readTemperature(sample);
        char name[24];
        TeBench::enumName(status, name, sizeof(name));
        failures += (status == Adxl355::DriverStatus::OK) ? 0U : 1U;
        shell_print(sh, "ADXL_TEMP status=%s raw=%u celsius=%.3f", name, sample.get_raw(), sample.get_celsius());
        if (i + 1U < count) {
            k_msleep(100);
        }
    }
    return (failures == 0U) ? 0 : -EIO;
}

extern "C" int adxl_cmd_selftest(const struct shell* sh, size_t argc, char** argv) {
    U32 samples = 64U;
    if ((argc > 1) && ((bench_parse_u32(argv[1], 10000U, &samples) != 0) || (samples < 4U))) {
        shell_error(sh, "usage: adxl selftest [samples 4..10000]");
        return -EINVAL;
    }
    if (g_streaming.load()) {
        shell_error(sh, "stop the stream first (adxl stream stop)");
        return -EBUSY;
    }
    // Data sheet: the self-test response is the output with ST2 high minus the output
    // with ST2 low, both with ST1 set; limits from Table 2 (Output Change), in g
    constexpr F64 MIN_G[3] = {0.1, 0.1, 0.5};
    constexpr F64 MAX_G[3] = {0.6, 0.6, 3.0};
    // Samples discarded after each change, so the digital filter settles
    const U32 settle = 32U;

    AxisStats discard, off, on;
    Adxl355::DriverStatus failure = Adxl355::DriverStatus::OK;
    bool ok = setSelfTest(sh, true, false) && average(settle, discard, failure) && average(samples, off, failure) &&
              setSelfTest(sh, true, true) && average(settle, discard, failure) && average(samples, on, failure);
    // Always leave self test off
    const bool cleared = setSelfTest(sh, false, false);
    if (!ok) {
        char name[24];
        TeBench::enumName(failure, name, sizeof(name));
        shell_print(sh, "ADXL_SELFTEST result=FAIL reason=%s", (failure != Adxl355::DriverStatus::OK) ? name : "command");
        return -EIO;
    }
    F64 delta[3];
    bool axisPass[3];
    for (U32 i = 0; i < 3U; i++) {
        delta[i] = on.mean(i) - off.mean(i);
        axisPass[i] = (delta[i] >= MIN_G[i]) && (delta[i] <= MAX_G[i]);
    }
    const bool pass = axisPass[0] && axisPass[1] && axisPass[2] && cleared;
    shell_print(sh,
                "ADXL_SELFTEST samples=%u dx_g=%.4f dy_g=%.4f dz_g=%.4f x=%s y=%s z=%s cleared=%d result=%s", samples,
                delta[0], delta[1], delta[2], axisPass[0] ? "PASS" : "FAIL", axisPass[1] ? "PASS" : "FAIL",
                axisPass[2] ? "PASS" : "FAIL", cleared ? 1 : 0, pass ? "PASS" : "FAIL");
    return pass ? 0 : -EIO;
}

extern "C" int adxl_cmd_timing(const struct shell* sh, size_t argc, char** argv) {
    U32 count = 200U;
    if ((argc > 1) && ((bench_parse_u32(argv[1], 100000U, &count) != 0) || (count == 0U))) {
        shell_error(sh, "usage: adxl timing [ok_reads 1..100000]");
        return -EINVAL;
    }
    Stats ok, stale, failed;
    const U32 period = odrPeriodUs(g_odrCode);
    const int64_t deadline = k_uptime_get() + 60000;
    while ((ok.count < count) && (k_uptime_get() < deadline)) {
        Adxl355::AccelerationSample sample;
        const U32 start = k_cycle_get_32();
        const Adxl355::DriverStatus status = client.readSensor(sample);
        const U32 us = k_cyc_to_us_floor32(k_cycle_get_32() - start);
        if (status == Adxl355::DriverStatus::OK) {
            ok.add(us);
            k_usleep(static_cast<int32_t>(period));
        } else if (status == Adxl355::DriverStatus::STALE_DATA) {
            stale.add(us);
            k_usleep(static_cast<int32_t>((period / 8U) > 50U ? period / 8U : 50U));
        } else {
            failed.add(us);
        }
    }
    shell_print(sh,
                "ADXL_TIMING ok_n=%u ok_min_us=%u ok_mean_us=%u ok_max_us=%u stale_n=%u stale_max_us=%u failed_n=%u "
                "sclk_hz=%u",
                ok.count, ok.minimum(), ok.mean(), ok.max, stale.count, stale.max, failed.count,
                TeBench::BenchSpi::actualSclkHz(g_spiHz));
    return ((ok.count == count) && (failed.count == 0U)) ? 0 : -EIO;
}

extern "C" int adxl_cmd_stream_start(const struct shell* sh, size_t argc, char** argv) {
    double rate = 0.0;
    U32 frames = 0U;
    U32 printEvery = 0U;
    if ((bench_parse_double(argv[1], 1.0, 4000.0, &rate) != 0) ||
        ((argc > 2) && (bench_parse_u32(argv[2], 100000000U, &frames) != 0)) ||
        ((argc > 3) && (bench_parse_u32(argv[3], 1000000U, &printEvery) != 0))) {
        shell_error(sh, "usage: adxl stream start <rate_hz 1..4000> [frames, 0 = until stop] [print_every]");
        return -EINVAL;
    }
    // The timer runs in whole ticks of 50 us (CONFIG_SYS_CLOCK_TICKS_PER_SEC)
    const U32 tickUs = 1000000U / CONFIG_SYS_CLOCK_TICKS_PER_SEC;
    const U32 periodUs = static_cast<U32>(std::lround(1.0e6 / rate));
    if ((periodUs % tickUs) != 0U) {
        shell_error(sh, "the period (%u us) must be a multiple of %u us", periodUs, tickUs);
        return -EINVAL;
    }
    if (g_streaming.load()) {
        shell_error(sh, "already streaming");
        return -EBUSY;
    }
    if (!setEnabled(sh, true)) {
        return -EIO;
    }
    client.resetFrameStats(printEvery);
    g_triggers.store(0U);
    g_missedTicks.store(0U);
    g_acqMin.store(UINT32_MAX);
    g_acqMax.store(0U);
    g_acqSum.store(0U);
    g_frameLimit.store(frames);
    g_periodUs = periodUs;
    if (printEvery != 0U) {
        Adxl355Te0715::Client::printFrameHeader();
    }
    g_streaming.store(true);
    k_timer_start(&g_frameTimer, K_USEC(periodUs), K_USEC(periodUs));
    k_sem_give(&g_streamStart);
    shell_print(sh, "ADXL_STREAM_STARTED rate_hz=%.3f period_us=%u frames=%u print_every=%u", 1.0e6 / periodUs,
                periodUs, frames, printEvery);
    return 0;
}

extern "C" int adxl_cmd_stream_stop(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    g_streaming.store(false);
    k_timer_stop(&g_frameTimer);
    // The application answers only after any frame in progress has finished
    const bool disabled = setEnabled(sh, false);
    printStreamStats(sh, "ADXL_STREAM_STOPPED");
    return disabled ? 0 : -EIO;
}

extern "C" int adxl_cmd_stream_status(const struct shell* sh, size_t argc, char** argv) {
    (void)argc;
    (void)argv;
    printStreamStats(sh, "ADXL_STREAM");
    return 0;
}

extern "C" int adxl_cmd_fprime(const struct shell* sh, size_t argc, char** argv) {
    const char* name = argv[1];
    const FwOpcodeType m = sensor.getIdBase();
    const FwOpcodeType a = app.getIdBase();
    const size_t n = argc - 2;
    char** args = argv + 2;
    Fw::SerializeStatus ok = Fw::FW_SERIALIZE_OK;
    auto put = [&ok](Fw::SerializeStatus status) {
        ok = (ok == Fw::FW_SERIALIZE_OK) ? status : ok;
    };

    // range, odr, hpf commands: the manager's INITIALIZE_SYNCED and the application's two
    // initializations
    const bool sampling = (strcmp(name, "init-synced") == 0) || (strcmp(name, "app-init") == 0) ||
                          (strcmp(name, "app-init-internal") == 0);
    if (sampling) {
        Adxl355::SensorRange range;
        U32 odr = 0U;
        U32 hpf = 0U;
        if ((n != 3U) || !parseSampling(sh, n, args, range, odr, hpf)) {
            shell_error(sh, "usage: adxl cmd %s <range 2|4|8> <odr_hz> <hpf 0..6>", name);
            return -EINVAL;
        }
        const FwOpcodeType opcode = (strcmp(name, "init-synced") == 0) ? m + ManagerIds::OPCODE_INITIALIZE_SYNCED
                                    : (strcmp(name, "app-init") == 0)  ? a + AppIds::OPCODE_INITIALIZE_ALL
                                                                        : a + AppIds::OPCODE_INITIALIZE_ALL_INTERNAL;
        Fw::ComBuffer& buffer = commander.begin(opcode);
        put(range.serializeTo(buffer));
        put(Adxl355::OutputDataRate(static_cast<Adxl355::OutputDataRate::T>(odr)).serializeTo(buffer));
        put(Adxl355::HighPassCorner(static_cast<Adxl355::HighPassCorner::T>(hpf)).serializeTo(buffer));
        Fw::CmdResponse response;
        if (ok != Fw::FW_SERIALIZE_OK) {
            return -EINVAL;
        }
        const bool done = sendCommand(sh, name, response);
        if (done) {
            g_odrCode = odr;
        }
        return done ? 0 : -EIO;
    }

    bool known = true;
    U32 u[3] = {0U, 0U, 0U};
    I32 s[3] = {0, 0, 0};
    bool b[2] = {false, false};
    if ((strcmp(name, "range") == 0) && (n == 1U)) {
        Adxl355::SensorRange range;
        known = parseRange(args[0], range);
        if (known) {
            put(range.serializeTo(commander.begin(m + ManagerIds::OPCODE_SET_RANGE)));
        }
    } else if ((strcmp(name, "filter") == 0) && (n == 2U)) {
        known = parseOdr(args[0], u[0]) && parseHpf(args[1], u[1]);
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_FILTER);
            put(Adxl355::OutputDataRate(static_cast<Adxl355::OutputDataRate::T>(u[0])).serializeTo(buffer));
            put(Adxl355::HighPassCorner(static_cast<Adxl355::HighPassCorner::T>(u[1])).serializeTo(buffer));
        }
    } else if ((strcmp(name, "sync") == 0) && (n == 2U)) {
        known = (bench_parse_u32(args[0], 2U, &u[0]) == 0) && (bench_parse_bool(args[1], &b[0]) == 0);
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_SYNC);
            put(Adxl355::SynchronizationMode(static_cast<Adxl355::SynchronizationMode::T>(u[0])).serializeTo(buffer));
            put(buffer.serializeFrom(b[0]));
        }
    } else if ((strcmp(name, "offsets") == 0) && (n == 3U)) {
        for (U32 i = 0; (i < 3U) && known; i++) {
            known = bench_parse_i32(args[i], INT16_MIN, INT16_MAX, &s[i]) == 0;
        }
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_OFFSETS);
            for (I32 value : s) {
                put(buffer.serializeFrom(static_cast<I16>(value)));
            }
        }
    } else if ((strcmp(name, "activity") == 0) && (n == 3U)) {
        known = (bench_parse_u32(args[0], 0xFFU, &u[0]) == 0) && (bench_parse_u32(args[1], 0xFFFFU, &u[1]) == 0) &&
                (bench_parse_u32(args[2], 0xFFU, &u[2]) == 0);
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_ACTIVITY);
            put(buffer.serializeFrom(static_cast<U8>(u[0])));
            put(buffer.serializeFrom(static_cast<U16>(u[1])));
            put(buffer.serializeFrom(static_cast<U8>(u[2])));
        }
    } else if ((strcmp(name, "interrupts") == 0) && (n == 2U)) {
        known = (bench_parse_u32(args[0], 0xFFU, &u[0]) == 0) && (bench_parse_bool(args[1], &b[0]) == 0);
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_INTERRUPTS);
            put(buffer.serializeFrom(static_cast<U8>(u[0])));
            put(buffer.serializeFrom(b[0]));
        }
    } else if ((strcmp(name, "selftest") == 0) && (n == 2U)) {
        known = (bench_parse_bool(args[0], &b[0]) == 0) && (bench_parse_bool(args[1], &b[1]) == 0);
        if (known) {
            Fw::ComBuffer& buffer = commander.begin(m + ManagerIds::OPCODE_SET_SELF_TEST);
            put(buffer.serializeFrom(b[0]));
            put(buffer.serializeFrom(b[1]));
        }
    } else if ((strcmp(name, "fifo-wm") == 0) && (n == 1U)) {
        known = bench_parse_u32(args[0], 0xFFU, &u[0]) == 0;
        if (known) {
            put(commander.begin(m + ManagerIds::OPCODE_SET_FIFO_WATERMARK).serializeFrom(static_cast<U8>(u[0])));
        }
    } else if ((strcmp(name, "app-count") == 0) && (n == 1U)) {
        known = bench_parse_u32(args[0], 0xFFU, &u[0]) == 0;
        if (known) {
            put(commander.begin(a + AppIds::OPCODE_SET_SENSOR_COUNT).serializeFrom(static_cast<U8>(u[0])));
        }
    } else if ((strcmp(name, "app-enable") == 0) && (n == 1U)) {
        known = bench_parse_bool(args[0], &b[0]) == 0;
        if (known) {
            put(commander.begin(a + AppIds::OPCODE_SET_ENABLED).serializeFrom(b[0]));
        }
    } else if (n == 0U) {
        static const struct {
            const char* name;
            bool application;
            FwOpcodeType opcode;
        } simple[] = {
            {"start", false, ManagerIds::OPCODE_START},
            {"stop", false, ManagerIds::OPCODE_STOP},
            {"snapshot", false, ManagerIds::OPCODE_READ_SNAPSHOT},
            {"clear-throttle", false, ManagerIds::OPCODE_CLEAR_EVENT_THROTTLE},
            {"app-report", true, AppIds::OPCODE_REPORT},
            {"app-clear-throttle", true, AppIds::OPCODE_CLEAR_EVENT_THROTTLE},
        };
        known = false;
        for (const auto& entry : simple) {
            if (strcmp(name, entry.name) == 0) {
                (void)commander.begin((entry.application ? a : m) + entry.opcode);
                known = true;
                break;
            }
        }
    } else {
        known = false;
    }
    if (!known) {
        shell_error(sh,
                    "manager: init-synced <range> <odr> <hpf>, start, stop, range <r>, filter <odr> <hpf>, "
                    "sync <mode> <extclk>, offsets <x> <y> <z>, activity <mask> <threshold> <count>, "
                    "interrupts <map> <active_high>, selftest <st1> <st2>, fifo-wm <n>, snapshot, clear-throttle; "
                    "application: app-init <range> <odr> <hpf>, app-init-internal <range> <odr> <hpf>, "
                    "app-count <n>, app-enable <0|1>, app-report, app-clear-throttle");
        return -EINVAL;
    }
    if (ok != Fw::FW_SERIALIZE_OK) {
        shell_error(sh, "arguments do not fit a command packet");
        return -EINVAL;
    }
    Fw::CmdResponse response;
    return sendCommand(sh, name, response) ? 0 : -EIO;
}

extern "C" int adxl_cmd_tlm(const struct shell* sh, size_t argc, char** argv) {
    bool on = tlmPrinter.isEnabled();
    if ((argc > 1) && (bench_parse_bool(argv[1], &on) != 0)) {
        shell_error(sh, "usage: adxl tlm [on|off]");
        return -EINVAL;
    }
    tlmPrinter.setEnabled(on);
    shell_print(sh, "ADXL_TLM printing=%s unprinted=%u", on ? "on" : "off", tlmPrinter.unprintedCount());
    return 0;
}
