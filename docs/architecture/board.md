# Board support

Zephyr knows the Zynq-7000 SoC family, but a board definition tells it how a
particular board is built: which chip, how much memory, which pins go where, and how
to load software onto it. The `te0715` board lives outside Zephyr, in
`app/boards/trenz/te0715/`, and is found through `app/zephyr/module.yml`.

## Hardware description

| Item | Setting | Notes |
|---|---|---|
| SoC | `xc7z030` | Confirmed on the module: `PSS_IDCODE` reads `0x1372C093` (part `0x372C`) |
| CPU clock | 666.67 MHz | From the reference design |
| System timer | ARM global timer, 333.33 MHz | Always runs at half the CPU clock; checked with `timer_api` and a 1 Hz heartbeat measured on the host |
| Memory | 1 GiB DDR3 at address 0 | |
| Console | UART0 on MIO14 (RX) and MIO15 (TX), 3.3 V, 115200 8N1 | |
| LED | D4 (green, on the module) on MIO7, alias `led0` | MIO7 is output-only |
| CAN1 | MIO12 (TX), MIO13 (RX), 3.3 V | Enabled by the carrier overlay |

## Pin configuration

The Zynq routes its peripherals to the MIO pins through a multiplexer in its System
Level Control Registers (SLCR). The FSBL or `ps7_init.tcl` sets it up for the
reference design; the board's devicetree re-applies the settings that matter for
Zephyr through Zephyr's pinctrl driver, so they do not depend on the boot loader:

- UART0 on MIO14/15 (pull-ups as in the reference design);
- CAN1 on MIO12/13 (pull-up on RX). In the reference design these pins are GPIO.

The GPIO pins (MIO7, MIO9) are left as the boot loader configures them, because the
Zynq GPIO driver does not apply pinctrl.

## CAN clock

The reference design has the CAN controllers disabled, so its FSBL does not turn on
their clocks. `app/boards/trenz/te0715/board.c` does this before the CAN driver
starts:

1. hold the enabled controllers in reset;
2. select the internal clock (not a clock from an MIO pin) and set `CAN_REF_CLK` to
   IO PLL (1000 MHz) ÷ 5 ÷ 2 = **100 MHz**;
3. enable the controllers' bus clocks;
4. release the reset.

A build-time check makes sure the devicetree's `clock-frequency` matches the 100 MHz.
For flight hardware the better place for this is the Vivado design, so that the FSBL
configures CAN like every other peripheral.

## Reboot

Zephyr does not implement a reboot for the Zynq-7000. `board.c` provides one: it sets
the `SOFT_RST` bit in the SLCR's `PSS_RST_CTRL` register, which resets the whole
processing system. The board then boots from its SD card.

## Carrier overlays

Things that depend on the TE0701 carrier rather than the module are in overlays:

| File | Adds |
|---|---|
| `app/boards/te0715.overlay` | The Pmod J1 GPIO on MIO9, for the LED/GPIO demo |
| `app/boards/te0701-can1.overlay` | Enables CAN1 at 1 Mbit/s as `zephyr,canbus` |

## Loading over JTAG

`board.cmake` selects Zephyr's `xsdb` runner, so `west flash` works. The runner runs
`support/xsdb.cfg`, which resets the system, runs `support/ps7_init.tcl` (exported
from the reference design variant `04_30_1i_1gb`) and loads the image into DDR.
