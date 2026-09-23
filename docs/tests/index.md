# Tests

All tests run on the real TE0715 hardware. Images are loaded into DDR over JTAG
(nothing is written to flash) except the SD card boot test.

| # | Test | Verifies | Setup | Page |
|---|---|---|---|---|
| 1 | Zephyr kernel suites | Kernel, timer, scheduler and stack protection on the Cortex-A9 port | Board only | [Zephyr test suites](zephyr-suites.md) |
| 2 | `uart_basic_api` | Console UART driver (polling, interrupts, configure) incl. the three fixes | Board only | [Zephyr test suites](zephyr-suites.md#uart) |
| 3 | `can/api`, `can/timing` | CAN driver API in internal loopback, on v4.4.2 and upstream `main` | Board only | [Zephyr test suites](zephyr-suites.md#can) |
| 4 | Transceiver wiring check | Pmod wiring and transceiver loop TX back to RX | Transceiver, no peer | [CAN bus](can-bus.md#wiring-check) |
| 5 | CAN echo | 1000 frames each way at 1 Mbit/s, heartbeat, error state | Transceiver + Kvaser | [CAN bus](can-bus.md#echo-test) |
| 6 | F Prime server vs Linux client | CSP ping, libparam get/set/restore through F Prime on Zephyr | Transceiver + Kvaser + Linux CspBench | [CSP, libparam and F Prime](csp-libparam-fprime.md) |
| 7 | Serial shell tools | Board as CSP/libparam client of a Linux CspBench server | idem | [CSP, libparam and F Prime](csp-libparam-fprime.md#shell-tools) |
| 8 | Standalone SD boot | Boot through the card's U-Boot, then test 6 | idem, no JTAG load | [SD card boot](../sd-card-boot.md#standalone-boot-test) |

## Running everything

```bash
app/scripts/collect_results.sh path/to/CspBench can0
```

runs tests 1-8 in order and stores the logs in `docs/results/<date>/` (see
[Results](results.md)). It needs the Kvaser interface up at 1 Mbit/s and the SD card
prepared with `scripts/sd_install.py`, and leaves the board running the FlatSat image
from the SD card.

## Test tools

| Script | Purpose |
|---|---|
| `scripts/hw_test.py test <suite>...` | Build, load and run ztest suites; reports each suite and fails on garbled output |
| `scripts/hw_test.py run <app>` | Build, load and capture an application's console |
| `scripts/can_echo_test.py <iface>` | Host side of the CAN echo test over SocketCAN (no dependencies) |
| `scripts/fprime_e2e.py` | Tests 6-8: Linux client against the board, then the board's shell against a Linux server |
| `scripts/sd_install.py` | Install or restore the SD card boot script |
| `scripts/flatsat_console.py` | Logging serial console for macOS/Linux (FlatSat) |
