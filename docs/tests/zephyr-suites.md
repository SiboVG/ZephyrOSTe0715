# Zephyr test suites

Zephyr ships test suites (ztest) for its kernel and drivers. Running them on the
TE0715 checks the board port before anything project-specific is involved.

These tests need only the board on the JTAG/UART cable. The CAN suites run in the
controller's internal loopback mode, so no transceiver or bus is needed.

## 1. Kernel suites

```bash
app/scripts/hw_test.py test tests/kernel/common tests/kernel/timer/timer_api \
    tests/kernel/sched/schedule_api tests/kernel/mem_protect/stackprot
```

For each suite, `hw_test.py` builds it for `te0715`, loads it over JTAG and follows
the console until the suite prints its verdict. Successful output:

```text
    SUITE PASS - 100.00% [timer_api]: pass = 15, fail = 0, skip = 0, total = 15 duration = 3.465 seconds
SUCCESSFUL   tests/kernel/timer/timer_api
```

`timer_api` is the one that checks the system timer rate. The `stackprot` log contains
a deliberate `Stack overflow` fatal error: the test triggers one and checks that
Zephyr catches it.

## 2. UART suite

```bash
app/scripts/hw_test.py test tests/drivers/uart/uart_basic_api
```

This suite tests the console UART itself, including reconfiguration and
interrupt-driven transmission. Some of its tests wait for keyboard input ("Please send
characters to serial console"); `hw_test.py` answers them automatically. It also
counts garbled characters and fails the test if there are any, which is how the
[UART driver bugs](../architecture/uart-driver.md) were found.

## 3. CAN suites

```bash
app/scripts/hw_test.py test --timeout 150 \
    -x-DEXTRA_DTC_OVERLAY_FILE=$PWD/app/boards/te0701-can1.overlay \
    tests/drivers/can/api tests/drivers/can/timing
```

The overlay enables CAN1. The `api` suite exercises sending, receiving, filters,
modes, bit timing and error handling; `timing` checks the bit-timing calculation.
Expect `can_classic` with 47 passed and 3 skipped tests. The skipped tests need remote
frames (`CONFIG_CAN_ACCEPT_RTR`) or a minimum bitrate. To run the remote-frame and
manual-recovery tests as well, add
`-x-DCONFIG_CAN_ACCEPT_RTR=y -x-DCONFIG_CAN_MANUAL_RECOVERY_MODE=y`.

To test the upstream PR branch instead of the workspace's Zephyr, see
[Building and running](../getting-started/build-and-run.md#upstream-main-builds).
