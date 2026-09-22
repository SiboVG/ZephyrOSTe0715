# TE0715 Zephyr application

Zephyr application and out-of-tree board (`te0715`) for the Trenz
TE0715-05-71I33-L (Zynq-7030) on a TE0701 carrier.

## Workspace setup

```sh
west init -l app      # app/west.yml pins Zephyr and the modules it needs
west update
west patch clean && west patch apply   # patches in zephyr/patches.yml
```

`west update` resets the patched projects (libcsp, libparam, fprime-zephyr),
so rerun the patch commands after every update.

Toolchain: Zephyr SDK 1.0.1 (`west sdk install -t arm-zephyr-eabi`).
Loading over JTAG needs AMD `xsdb` (Vitis 2022.1 in `/tools/Xilinx`) and the
Digilent JTAG/UART cable on the TE0701.

## Build and run

```sh
west build -b te0715 app
PATH=/tools/Xilinx/Vitis/2022.1/bin:$PATH west flash
```

`west flash` resets the board, initialises the PS with
`boards/trenz/te0715/support/ps7_init.tcl` (from the Trenz test_board
reference design, variant `04_30_1i_1gb`) and loads `zephyr.elf` into DDR.
Nothing is written to QSPI flash or the SD card; a power cycle boots whatever
is on the boot medium again. The console is UART0 (MIO14/15) on the cable's
second interface, 115200 8N1:
`/dev/serial/by-id/usb-Digilent_*-if01-port0`.

## Hardware tests

`scripts/hw_test.py` builds, loads and checks images on the board:

```sh
# ztest suites (exit code 1 if any fails or prints garbled output)
app/scripts/hw_test.py test tests/kernel/common tests/drivers/uart/uart_basic_api

# an application, capturing its console for 10 s or until a regex matches
app/scripts/hw_test.py run app --seconds 10
app/scripts/hw_test.py run app --until "D4 on"
```

Build directories and console logs go to `build/hw/`. Tests that ask for
keyboard input are answered automatically.

## Applications

| Directory | What it does |
|---|---|
| `.` (`src/main.c`) | Blinks LED D4 and toggles MIO9 on Pmod J1 |
| `apps/can_bringup` | Echoes CAN ID 0x100 as 0x101, 1 Hz heartbeat on 0x7F0 |
| `apps/csp_node` | libcsp node 101/8 with the CSP services and a libparam server |
| `apps/fprime_csp_bench` | F Prime `CspBench` server role (node 101, parameter 200) |

The CAN applications use CAN1 on the TE0701 Pmod J1 (`boards/te0701-can1.overlay`,
1 Mbit/s) with an external 3.3 V transceiver:

| Pmod J1 | Signal | Transceiver (e.g. SN65HVD233) |
|---|---|---|
| 10 | MIO12, CAN1 TX | D (TXD) |
| 7 | MIO13, CAN1 RX | R (RXD) |
| 6 | 3.3 V (check with a meter) | V<sub>CC</sub> |
| 12 | GND (check with a meter) | GND |

Raw CAN check against a SocketCAN interface on the host:

```sh
app/scripts/hw_test.py run app/apps/can_bringup --seconds 5
sudo ip link set can0 type can bitrate 1000000 && sudo ip link set can0 up
app/scripts/can_echo_test.py can0 --count 1000
```

`apps/fprime_csp_bench` is an F Prime project, built with `fprime-util` from the
workspace virtual environment. It expects the `fprime-csp-libparam`
(`zephyr-can-transport` branch) and `CspLibparamFprimeTest` (`zephyr-transport`
branch) checkouts next to this workspace:

```sh
cd app/apps/fprime_csp_bench
fprime-util generate && fprime-util build
PATH=/tools/Xilinx/Vitis/2022.1/bin:$PATH xsdb ../../boards/trenz/te0715/support/xsdb.cfg \
    build-fprime-automatic-zephyr/zephyr/zephyr.elf
```

The Linux bench then talks to it as usual, e.g.
`CspBench --role client --can can0 --node 100 --peer 101`.

## Board notes

- UART0 pins are configured by Zephyr pinctrl. The GPIO pins (MIO7, MIO9) are
  muxed by `ps7_init.tcl`, because the Zynq GPIO driver does not apply pinctrl.
- LED D4 (green, on the module) is on MIO7, available as `led0`. MIO7 is an
  output-only pin on the Zynq, so its level cannot be read back.
- MIO9 goes to Pmod J1 on the TE0701 only (no other connections).
