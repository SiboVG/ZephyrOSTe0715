# TE0715 Zephyr application

Zephyr application and out-of-tree board (`te0715`) for the Trenz
TE0715-05-71I33-L (Zynq-7030) on a TE0701 carrier.

## Workspace setup

```sh
west init -l app      # app/west.yml pins Zephyr and the modules it needs
west update
```

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

## Board notes

- UART0 pins are configured by Zephyr pinctrl. The GPIO pins (MIO7, MIO9) are
  muxed by `ps7_init.tcl`, because the Zynq GPIO driver does not apply pinctrl.
- LED D4 (green, on the module) is on MIO7, available as `led0`. MIO7 is an
  output-only pin on the Zynq, so its level cannot be read back.
- MIO9 goes to Pmod J1 on the TE0701 only (no other connections).
