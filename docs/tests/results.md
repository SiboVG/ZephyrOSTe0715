# Results

Latest full run: `scripts/collect_results.sh`, 2026-09-23, on the TE0715-05-71I33-L +
TE0701, SN65HVD233 on Pmod J1, Kvaser USBcan `can0` at 1 Mbit/s. All logs are in
[`results/2026-09-23/`](../results/2026-09-23/environment.txt) (start with
`environment.txt` for the exact revisions).

| # | Test | Result | Log |
|---|---|---|---|
| 1 | `kernel/common` | all suites pass (1 skip) | [log](../results/2026-09-23/tests_kernel_common.log) |
| 1 | `kernel/timer/timer_api` | 15/15 | [log](../results/2026-09-23/tests_kernel_timer_timer_api.log) |
| 1 | `kernel/sched/schedule_api` | 21 pass, 8 skip | [log](../results/2026-09-23/tests_kernel_sched_schedule_api.log) |
| 1 | `kernel/mem_protect/stackprot` | 3/3 | [log](../results/2026-09-23/tests_kernel_mem_protect_stackprot.log) |
| 2 | `drivers/uart/uart_basic_api` | 7/7, no garbled output | [log](../results/2026-09-23/tests_drivers_uart_uart_basic_api.log) |
| 3 | `drivers/can/api` (v4.4.2) | 47 pass, 3 skip | [log](../results/2026-09-23/tests_drivers_can_api-9e7671a0.log) |
| 3 | `drivers/can/timing` (v4.4.2) | 1 pass, 1 skip | [log](../results/2026-09-23/tests_drivers_can_timing-9e7671a0.log) |
| 3 | `drivers/can/api` (upstream `main`) | 48 pass, 4 skip | [log](../results/2026-09-23/upstream-main-tests_drivers_can_api-9e7671a0.log) |
| 3 | `drivers/can/timing` (upstream `main`) | 1 pass, 1 skip | [log](../results/2026-09-23/upstream-main-tests_drivers_can_timing-9e7671a0.log) |
| 5 | CAN echo, 1000 frames | 1000/1000, heartbeat 0.999 s, error-active | [log](../results/2026-09-23/can-echo.txt), [board](../results/2026-09-23/can-bringup.txt) |
| 6-7 | F Prime server + shell, JTAG | 13/13 checks; client PASS 5/5 | [summary](../results/2026-09-23/fprime-e2e-jtag.txt), [transcript](../results/2026-09-23/fprime-e2e-jtag-transcript.log) |
| 8 | Standalone SD boot + 6-7 | 13/13 checks; ready 14.7 s after reset | [summary](../results/2026-09-23/fprime-e2e-sd-boot.txt), [transcript](../results/2026-09-23/fprime-e2e-sd-boot-transcript.log) |

The transceiver wiring check (test 4) and the UART driver comparisons (stock versus
fixed) were run interactively during bring-up; their observations are quoted on the
[CAN bus](can-bus.md#wiring-check) and [Zephyr test suites](zephyr-suites.md#uart)
pages.

## Checks of the end-to-end test

```text
PASS  start window announced
PASS  server ready on node 6061 (14.7 s after reset)
PASS  bench info
PASS  Linux client against node 6061: [CSP_BENCH_RESULT] PASS attempts=5 successes=5 failures=0
PASS  csp ping 102 (CRC32)
PASS  csp ping 102 --nocrc is dropped by the CRC-requiring peer
PASS  param get 102 200 u32 = 0x12345678
PASS  param set without --confirm is refused
PASS  param set --confirm writes and reads back 0xCAFEBABE
PASS  param get reads the new value
PASS  param set --confirm restores 0x12345678
PASS  csp ping to an absent node times out
PASS  can show: no bus errors
13/13 checks passed
```

## Timing

| Quantity | Value |
|---|---|
| CSP ping round trip, board ↔ Linux (32 bytes, 1 Mbit/s) | 3-4 ms |
| Standalone boot, reset → CSP ready (incl. 10 s start window) | 14.7 s |
| Load over JTAG, reset → CSP ready (start window skipped) | 4.9 s |
| 1000 CAN echo round trips | 6.0 s |
