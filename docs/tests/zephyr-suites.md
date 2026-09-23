# Zephyr test suites

Upstream Zephyr ztest suites, built for the `te0715` board and run with

```bash
app/scripts/hw_test.py test tests/kernel/common tests/kernel/timer/timer_api \
    tests/kernel/sched/schedule_api tests/kernel/mem_protect/stackprot \
    tests/drivers/uart/uart_basic_api
app/scripts/hw_test.py test --timeout 150 \
    -x-DEXTRA_DTC_OVERLAY_FILE=$PWD/app/boards/te0701-can1.overlay \
    tests/drivers/can/api tests/drivers/can/timing
```

Pass criterion: `PROJECT EXECUTION SUCCESSFUL` and no garbled console output.
`hw_test.py` answers the keyboard prompts of `uart_basic_api` itself.

## Kernel

| Suite | Result | Skipped (reason) |
|---|---|---|
| `kernel/common` (12 suites) | all pass | `test_nested_irq_offload` (not supported) |
| `kernel/timer/timer_api` | 15/15 | - |
| `kernel/sched/schedule_api` | 21 pass | 8 (SMP/multi-core cases; Zephyr runs one core here) |
| `kernel/mem_protect/stackprot` | 3/3 | `stackprot_mapped_stack` (option not enabled) |

The `stackprot` log contains a deliberate `Stack overflow` fatal error: the test
triggers one and checks that it is caught.

## UART

`tests/drivers/uart/uart_basic_api` (7 tests) on the console UART:

| Driver | Result |
|---|---|
| Stock v4.4.2 | 7/7 pass, but ~300-800 garbled bytes per run during `test_uart_configure` |
| Drain fix only | garbling gone, `test_uart_fifo_fill` fails (TX stalls after one character) |
| All three fixes | 7/7 pass, 0 garbled bytes, 3 consecutive runs |

A separate application switching the baud rate at runtime (115200 → 57600 → 115200)
confirmed the `set_baudrate()` fix. See [Drivers and patches](../drivers.md#uart-uart_xlnx_ps-fixes).

## CAN

`tests/drivers/can/api` and `tests/drivers/can/timing` run in the controller's
internal loopback mode, so no bus is needed.

| Branch | `can_classic` | `can_stats` | `can_utilities` | `can_timing` |
|---|---|---|---|---|
| v4.4.2 (`te0715-can-v4.4.2`) | 47 pass, 3 skip | 1/1 | 3/3 | 1 pass, 1 skip |
| v4.4.2 with `CONFIG_CAN_ACCEPT_RTR` + `CONFIG_CAN_MANUAL_RECOVERY_MODE` | 47 pass, 3 skip (RTR and recovery tests now run) | 1/1 | 3/3 | - |
| upstream `main` (`xlnx-can`) | 48 pass, 4 skip | 1/1 | 3/3 | 1 pass, 1 skip |

The skipped tests need remote frames (`CONFIG_CAN_ACCEPT_RTR`), a minimum bitrate
(the driver declares none) or features the controller lacks (CAN FD, transceiver,
power management).
