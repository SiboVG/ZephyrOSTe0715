# Drivers and patches

## UART: `uart_xlnx_ps` fixes

Upstream PR: [zephyrproject-rtos/zephyr#119996](https://github.com/zephyrproject-rtos/zephyr/pull/119996)
(branch `xuartps-fixes`, on `main`). Found with `tests/drivers/uart/uart_basic_api`
on the TE0715.

| Fix | Problem | Evidence |
|---|---|---|
| Use the requested baud rate in `set_baudrate()` | The function used the stored rate, which `configure()` updates only afterwards, so the hardware was always one `uart_configure()` call behind | A 115200 → 57600 → 115200 switch left the UART at 115200, then programmed 57600; clean after the fix |
| Drain TX before reconfiguring | `configure()` disabled the transmitter mid-character; with a continuously full FIFO the receiver locked onto a wrong start bit | 300-800 garbled bytes per test run (every `=` received as `0xEA`, a 2-bit framing offset); 0 after the fix |
| Fix TX interrupt readiness | `irq_tx_ready()` used the TX trigger flag, which means "FIFO at or above the trigger level"; callbacks ran with a full FIFO, `fifo_fill()` accepted 0 bytes, and `test_uart_fifo_fill` stalled after one character | 7/7 `uart_basic_api` tests in three consecutive runs after the fix |

## CAN: Zynq-7000 PS CAN driver (`drivers/can/can_xlnx.c`)

Zephyr had no driver for the Zynq PS CAN controller. The new driver is based on
the abandoned upstream PR #45101 (Immo Birnbaum, 2022, closed in 2024 without
review follow-up), rewritten for the current CAN driver API. Compatible
`xlnx,zynq-can-1.0`, the same as the Linux binding.

Design decisions:

- **One frame in the TX FIFO at a time.** The controller has no TX FIFO fill level
  register, so with several queued frames a TX OK interrupt cannot be attributed to
  one frame. (The 2022 driver completed every pending callback on each TX OK,
  including frames that were still queued.) With one frame in flight, each TX OK
  completes exactly one `can_send()`; the extra gap is a few microseconds per frame.
- **Software RX filtering.** The four hardware acceptance filters are global (one RX
  FIFO), so they are left disabled and frames are matched against up to
  `CONFIG_CAN_XLNX_MAX_FILTERS` (16) software filters.
- **Controller reset on start/stop.** `can_start()` resets and fully reprograms the
  controller; `can_stop()` resets it, which flushes both FIFOs and aborts a pending
  frame with `-ENETDOWN`.
- **Bus-off.** The pending frame fails with `-ENETUNREACH`, the controller is reset,
  and it restarts after at least 128 × 11 bit times (automatic recovery) or on
  `can_recover()` (`CONFIG_CAN_MANUAL_RECOVERY_MODE`).
- **Error state.** The controller has no interrupt for error-state changes, so the
  state is re-evaluated on every interrupt and read live in `can_get_state()`.
- **Modes.** Normal and internal loopback. The Zynq-7000 controller has no one-shot
  mode, and listen-only is not claimed.
- **Clock.** The driver expects `CAN_REF_CLK` and the APB clock to be enabled (by
  the FSBL or board code) and takes the reference frequency from `clock-frequency`.

### Branches

| Branch | Base | Use |
|---|---|---|
| `xlnx-can` | upstream `main` | For an upstream PR. Independent of the UART fixes. On `main` it uses the new multi-callback state change API (`can_fire_state_change_callbacks()`), which v4.4.2 does not have |
| `te0715-can-v4.4.2` | v4.4.2 + UART fixes | Pinned by this workspace; the same driver on the v4.4.2 API |

Both pass `tests/drivers/can/api` and `tests/drivers/can/timing` on the TE0715; see
[Zephyr test suites](tests/zephyr-suites.md). Before opening the PR, every commit
needs the author's `Signed-off-by` (DCO).

## Patches

Applied with `west patch apply` from `zephyr/patches.yml`:

| Module | Patch | Reason | Upstreamable |
|---|---|---|---|
| libcsp | `0001-zephyr-include-time.h-from-the-C-library` | Zephyr 4.x removed `<zephyr/posix/time.h>` | yes |
| libparam | `0001-vmem-client-do-not-shadow-abort` | A file-scope variable `abort` clashes with `abort()` from picolibc's `<stdlib.h>` | yes |
| fprime-zephyr | `0001-lora-enum-command-handler-signature` | LoRa part of fprime-zephyr `b76db2b`: the pinned F Prime passes enum arguments by const reference | already upstream |
| fprime-zephyr | `0002-os-task-default-stack-size` | `Os::Task::TASK_DEFAULT` was passed to `k_thread_stack_alloc()` as `SIZE_MAX`, so every task started with default arguments failed (e.g. the libcsp router: runtime error -205) | yes |
| fprime-zephyr | `0003-os-task-map-fprime-priorities` | F Prime priorities (higher = more important) were passed through unchanged (Zephyr: lower = more important) and clamped to 14, so all tasks ran at the lowest priority. Now `N - 1 - p` | yes, but changes behavior for existing users |

Other integration changes, not patches:

| Where | Change |
|---|---|
| `zephyr/CMakeLists.txt` | libparam: same source set and dynamic-list profile as the Linux build, `_DEFAULT_SOURCE` for `strlcpy()`, headers as system includes |
| `apps/fprime_csp_bench/config/PlatformCfg.fpp` | Larger F Prime OS handle sizes: the Zephyr handles embed kernel objects (a `k_thread` with FPU context on the Cortex-A9) |
| `apps/fprime_csp_bench/CMakeLists.txt` | Declares the C/C++ compile features, which CMake cannot detect for Zephyr's toolchain |
| fprime-csp-libparam | `FprimeCsp_ZephyrCan` module; host thread library only on POSIX |
| CspLibparamFprimeTest | Transport chosen at compile time; include root relative to the component |
