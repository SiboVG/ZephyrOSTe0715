// SPDX-License-Identifier: Apache-2.0
//
// PL access of the ADXL355 bench (see pl.h): the cubespec-pl sysctrl, timebase and
// acc cores, mapped through the devicetree fragment cubespec-pl generates
// (pl.overlay), and the `pl` shell commands. Output lines start with a PL_ marker
// and use key=value fields, like the adxl commands.

#include "pl.h"

#include "TeBench/Support/bench_parse.h"

#include <atomic>
#include <cstddef>
#include <cstring>

#include <pp_map.h>
#include <pp_regs.h>

#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/spinlock.h>
#include <zephyr/sys/device_mmio.h>
#include <zephyr/sys/sys_io.h>

namespace {

#define PL_SYSCTRL DT_NODELABEL(pl_sysctrl)
#define PL_TIMEBASE DT_NODELABEL(pl_timebase)
#define PL_ACC DT_NODELABEL(pl_acc)

constexpr uint32_t CUBESPEC_MAGIC = 0x43534757U;
constexpr uint32_t ACC_CLK_HZ = 1024000U;

#define REG(block, name) offsetof(pp__##block##_t, name)

mm_reg_t g_sysctrl = 0;
mm_reg_t g_timebase = 0;
mm_reg_t g_acc = 0;
bool g_mapped = false;

struct k_sem g_eventSem;
struct k_spinlock g_eventLock;
Pl::SyncEvent g_event = {0U, 0U};
std::atomic<uint32_t> g_overruns{0U};

void map() {
    if (g_mapped) {
        return;
    }
    // Zephyr's Zynq-7000 SoC code does not map the PL window: map each core uncached
    device_map(&g_sysctrl, DT_REG_ADDR(PL_SYSCTRL), DT_REG_SIZE(PL_SYSCTRL), K_MEM_CACHE_NONE);
    device_map(&g_timebase, DT_REG_ADDR(PL_TIMEBASE), DT_REG_SIZE(PL_TIMEBASE), K_MEM_CACHE_NONE);
    device_map(&g_acc, DT_REG_ADDR(PL_ACC), DT_REG_SIZE(PL_ACC), K_MEM_CACHE_NONE);
    k_sem_init(&g_eventSem, 0, 1);
    g_mapped = true;
}

uint32_t rd(mm_reg_t base, size_t offset) {
    return sys_read32(base + offset);
}

void wr(mm_reg_t base, size_t offset, uint32_t value) {
    sys_write32(value, base + offset);
}

uint32_t clockHz() {
    return rd(g_timebase, REG(timebase, FREQ));
}

void accIsr(const void* arg) {
    ARG_UNUSED(arg);
    const uint32_t status = rd(g_acc, REG(acc, IRQ_STATUS));
    if ((status & PP__ACC__IRQ_STATUS__SYNC_bm) != 0U) {
        const k_spinlock_key_t key = k_spin_lock(&g_eventLock);
        g_event.count = rd(g_acc, REG(acc, EVENT_COUNT));
        g_event.ticks = (static_cast<uint64_t>(rd(g_acc, REG(acc, EVENT_TIME_HI))) << 32) |
                        rd(g_acc, REG(acc, EVENT_TIME_LO));
        k_spin_unlock(&g_eventLock, key);
    }
    if ((status & PP__ACC__IRQ_STATUS__OVERRUN_bm) != 0U) {
        g_overruns.fetch_add(1U);
    }
    // Clear what was seen, and read back so the write completes before the end of
    // interrupt: the line is level-sensitive
    wr(g_acc, REG(acc, IRQ_STATUS), status);
    (void)rd(g_acc, REG(acc, IRQ_STATUS));
    if ((status & PP__ACC__IRQ_STATUS__SYNC_bm) != 0U) {
        k_sem_give(&g_eventSem);
    }
}

void connectIrq() {
    static bool connected = false;
    if (!connected) {
        IRQ_CONNECT(DT_IRQN(PL_ACC), DT_IRQ(PL_ACC, priority), accIsr, nullptr, DT_IRQ(PL_ACC, flags));
        connected = true;
    }
}

bool parseOnOff(const char* text, bool* on) {
    if (strcmp(text, "on") == 0) {
        *on = true;
        return true;
    }
    if (strcmp(text, "off") == 0) {
        *on = false;
        return true;
    }
    return false;
}

}  // namespace

namespace Pl {

bool timingRunning() {
    map();
    const uint32_t status = rd(g_acc, REG(acc, STATUS));
    return (status & PP__ACC__STATUS__CLK_RUNNING_bm) != 0U && (status & PP__ACC__STATUS__SYNC_RUNNING_bm) != 0U;
}

uint32_t syncPeriodUs() {
    map();
    const uint32_t clocks = rd(g_acc, REG(acc, SYNC_PERIOD)) & PP__ACC__SYNC_PERIOD__CLOCKS_bm;
    return static_cast<uint32_t>((static_cast<uint64_t>(clocks) * 1000000U) / ACC_CLK_HZ);
}

uint64_t syncPeriodTicks() {
    map();
    const uint32_t clocks = rd(g_acc, REG(acc, SYNC_PERIOD)) & PP__ACC__SYNC_PERIOD__CLOCKS_bm;
    return static_cast<uint64_t>(clocks) * (clockHz() / ACC_CLK_HZ);
}

uint64_t nowTicks() {
    map();
    wr(g_timebase, REG(timebase, SNAP_CTRL), PP__TIMEBASE__SNAP_CTRL__CAPTURE_bm);
    const uint32_t low = rd(g_timebase, REG(timebase, SNAP_LO));
    return (static_cast<uint64_t>(rd(g_timebase, REG(timebase, SNAP_HI))) << 32) | low;
}

void startEvents() {
    map();
    connectIrq();
    k_sem_reset(&g_eventSem);
    g_overruns.store(0U);
    wr(g_acc, REG(acc, IRQ_STATUS), PP__ACC__IRQ_STATUS__SYNC_bm | PP__ACC__IRQ_STATUS__OVERRUN_bm);
    wr(g_acc, REG(acc, IRQ_ENABLE), PP__ACC__IRQ_ENABLE__SYNC_bm | PP__ACC__IRQ_ENABLE__OVERRUN_bm);
    irq_enable(DT_IRQN(PL_ACC));
}

void stopEvents() {
    map();
    irq_disable(DT_IRQN(PL_ACC));
    wr(g_acc, REG(acc, IRQ_ENABLE), 0U);
    wr(g_acc, REG(acc, IRQ_STATUS), PP__ACC__IRQ_STATUS__SYNC_bm | PP__ACC__IRQ_STATUS__OVERRUN_bm);
}

bool waitEvent(SyncEvent& event, k_timeout_t timeout) {
    if (k_sem_take(&g_eventSem, timeout) != 0) {
        return false;
    }
    const k_spinlock_key_t key = k_spin_lock(&g_eventLock);
    event = g_event;
    k_spin_unlock(&g_eventLock, key);
    return true;
}

uint64_t ticksToUs(uint64_t ticks) {
    // The time base runs at a whole number of MHz (128 MHz)
    return ticks / (clockHz() / 1000000U);
}

uint32_t overruns() {
    return g_overruns.load();
}

}  // namespace Pl

extern "C" int pl_cmd_info(const struct shell* sh, size_t argc, char** argv) {
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    map();
    const uint32_t magic = rd(g_sysctrl, REG(sysctrl, MAGIC));
    const uint32_t id = rd(g_sysctrl, REG(sysctrl, ID));
    const uint32_t platform = rd(g_sysctrl, REG(sysctrl, PLATFORM));
    const uint32_t slots = rd(g_sysctrl, REG(sysctrl, SLOTS));
    const uint32_t mapMajor = (platform & PP__SYSCTRL__PLATFORM__MAP_MAJOR_bm) >> PP__SYSCTRL__PLATFORM__MAP_MAJOR_bp;
    const uint32_t mapMinor = (platform & PP__SYSCTRL__PLATFORM__MAP_MINOR_bm) >> PP__SYSCTRL__PLATFORM__MAP_MINOR_bp;
    const bool ok = (magic == CUBESPEC_MAGIC) && (mapMajor == PP_MAP_MAJOR) &&
                    ((slots & PP_SLOTS_PRESENT) == PP_SLOTS_PRESENT);
    const uint32_t tbId = ok ? rd(g_timebase, REG(timebase, ID)) : 0U;
    const uint32_t accId = ok ? rd(g_acc, REG(acc, ID)) : 0U;
    shell_print(sh,
                "PL_INFO magic=0x%08x id=0x%08x target=%u carrier=%u map=%u.%u slots=0x%08x git=0x%08x dirty=%u "
                "build_time=%u tb_id=0x%08x tb_hz=%u acc_id=0x%08x header_map=%u.%u result=%s",
                magic, id, (platform & PP__SYSCTRL__PLATFORM__TARGET_ID_bm) >> PP__SYSCTRL__PLATFORM__TARGET_ID_bp,
                (platform & PP__SYSCTRL__PLATFORM__CARRIER_ID_bm) >> PP__SYSCTRL__PLATFORM__CARRIER_ID_bp, mapMajor,
                mapMinor, slots, rd(g_sysctrl, REG(sysctrl, GIT_HASH)),
                rd(g_sysctrl, REG(sysctrl, BUILD_FLAGS)) & PP__SYSCTRL__BUILD_FLAGS__DIRTY_bm,
                rd(g_sysctrl, REG(sysctrl, BUILD_TIME)), tbId, ok ? clockHz() : 0U, accId, PP_MAP_MAJOR,
                PP_MAP_MINOR, ok ? "PASS" : "FAIL");
    return ok ? 0 : -EIO;
}

extern "C" int pl_cmd_clk(const struct shell* sh, size_t argc, char** argv) {
    ARG_UNUSED(argc);
    bool on = false;
    if (!parseOnOff(argv[1], &on)) {
        shell_error(sh, "usage: pl clk on|off");
        return -EINVAL;
    }
    map();
    // Turning the clock off also stops the pulse train
    wr(g_acc, REG(acc, CTRL), on ? PP__ACC__CTRL__CLK_EN_bm : 0U);
    shell_print(sh, "PL_CLK clk_en=%d status=0x%x", on ? 1 : 0, rd(g_acc, REG(acc, STATUS)));
    return 0;
}

extern "C" int pl_cmd_sync(const struct shell* sh, size_t argc, char** argv) {
    bool on = false;
    uint32_t period = 0U;
    uint32_t width = 0U;
    if (!parseOnOff(argv[1], &on) || ((argc > 2) && (bench_parse_u32(argv[2], 65535U, &period) != 0)) ||
        ((argc > 3) && (bench_parse_u32(argv[3], 255U, &width) != 0))) {
        shell_error(sh, "usage: pl sync on|off [period_clocks 2..65535] [width_clocks 1..255]");
        return -EINVAL;
    }
    map();
    const uint32_t ctrl = rd(g_acc, REG(acc, CTRL));
    if (on && ((ctrl & PP__ACC__CTRL__CLK_EN_bm) == 0U)) {
        shell_error(sh, "start the clock first (pl clk on)");
        return -EPERM;
    }
    if (argc > 2) {
        wr(g_acc, REG(acc, SYNC_PERIOD), period);
    }
    if (argc > 3) {
        wr(g_acc, REG(acc, SYNC_WIDTH), width);
    }
    wr(g_acc, REG(acc, CTRL), on ? (ctrl | PP__ACC__CTRL__SYNC_EN_bm) : (ctrl & ~PP__ACC__CTRL__SYNC_EN_bm));
    shell_print(sh, "PL_SYNC sync_en=%d period_clocks=%u width_clocks=%u period_us=%u", on ? 1 : 0,
                rd(g_acc, REG(acc, SYNC_PERIOD)), rd(g_acc, REG(acc, SYNC_WIDTH)), Pl::syncPeriodUs());
    return 0;
}

extern "C" int pl_cmd_delay(const struct shell* sh, size_t argc, char** argv) {
    map();
    const uint32_t ticksPerUs = clockHz() / 1000000U;
    if (argc > 1) {
        uint32_t us = 0U;
        if (bench_parse_u32(argv[1], 0xFFFFFFU / ticksPerUs, &us) != 0) {
            shell_error(sh, "usage: pl delay [us]");
            return -EINVAL;
        }
        wr(g_acc, REG(acc, IRQ_DELAY), us * ticksPerUs);
    }
    const uint32_t ticks = rd(g_acc, REG(acc, IRQ_DELAY));
    shell_print(sh, "PL_DELAY ticks=%u us=%u", ticks, ticks / ticksPerUs);
    return 0;
}

extern "C" int pl_cmd_status(const struct shell* sh, size_t argc, char** argv) {
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    map();
    shell_print(sh,
                "PL_ACC ctrl=0x%x status=0x%x period_clocks=%u width_clocks=%u delay_ticks=%u event_count=%u "
                "irq_status=0x%x irq_enable=0x%x overruns=%u",
                rd(g_acc, REG(acc, CTRL)), rd(g_acc, REG(acc, STATUS)), rd(g_acc, REG(acc, SYNC_PERIOD)),
                rd(g_acc, REG(acc, SYNC_WIDTH)), rd(g_acc, REG(acc, IRQ_DELAY)), rd(g_acc, REG(acc, EVENT_COUNT)),
                rd(g_acc, REG(acc, IRQ_STATUS)), rd(g_acc, REG(acc, IRQ_ENABLE)), Pl::overruns());
    return 0;
}

extern "C" int pl_cmd_time(const struct shell* sh, size_t argc, char** argv) {
    ARG_UNUSED(argc);
    ARG_UNUSED(argv);
    map();
    // Bracket the capture with the PS clock: the PL time lies between the two readings
    const uint64_t before = k_cycle_get_64();
    wr(g_timebase, REG(timebase, SNAP_CTRL), PP__TIMEBASE__SNAP_CTRL__CAPTURE_bm);
    (void)rd(g_timebase, REG(timebase, SNAP_LO));
    const uint64_t after = k_cycle_get_64();
    const uint64_t pl = (static_cast<uint64_t>(rd(g_timebase, REG(timebase, SNAP_HI))) << 32) |
                        rd(g_timebase, REG(timebase, SNAP_LO));
    shell_print(sh, "PL_TIME pl_ticks=%llu pl_us=%llu ps_us_before=%llu ps_us_after=%llu",
                static_cast<unsigned long long>(pl), static_cast<unsigned long long>(Pl::ticksToUs(pl)),
                static_cast<unsigned long long>(k_cyc_to_us_floor64(before)),
                static_cast<unsigned long long>(k_cyc_to_us_floor64(after)));
    return 0;
}
