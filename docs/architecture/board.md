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
| Memory | 1 GiB DDR3 at address 0 | Zephyr's system RAM starts at `0x100000`: DDR below `0x80000` is reachable by the CPUs only, not by the GEMs or other bus masters (UG585, table 4-1; `TE-BSP-004`). Images are linked, loaded and started at `0x100000`; Zephyr copies its vector table to address 0 |
| Console | UART0 on MIO14 (RX) and MIO15 (TX), 3.3 V, 115200 8N1 | |
| LED | D4 (green, on the module) on MIO7, alias `led0` | MIO7 is output-only |
| CAN1 | MIO12 (TX), MIO13 (RX), 3.3 V | Enabled by the carrier overlay |
| SPI1 | MIO10 (MOSI), MIO11 (MISO), MIO12 (SCLK), chip select MIO13 (GPIO), 3.3 V | Enabled by the carrier overlay; shares MIO12/13 with CAN1 |
| Ethernet | GEM0 on MIO16–27 (RGMII), MDIO on MIO52/53; Marvell 88E151x PHY at MDIO address 0; TE0701 RJ45 | Enabled in `te0715.dts` at 100 Mbit/s with the driver managing the PHY; built only into images with networking, which must set `local-mac-address`. Its DMA memory is in system RAM, which the GEM reaches (`TE-BSP-004`) |

## Pin configuration

The Zynq routes its peripherals to the MIO pins through a multiplexer in its System
Level Control Registers (SLCR). The FSBL or `ps7_init.tcl` sets it up for the
reference design; the board's devicetree re-applies the settings that matter for
Zephyr through Zephyr's pinctrl driver, so they do not depend on the boot loader:

- UART0 on MIO14/15 (pull-ups as in the reference design);
- CAN1 on MIO12/13 (pull-up on RX). In the reference design these pins are GPIO;
- SPI1 on MIO10 to MIO12 and its slave select SS0 on MIO13 (pull-ups, as in the
  reference design). The SPI driver does not apply pinctrl either, so `board.c` applies
  this state (see below).

The other GPIO pins (MIO7, MIO9) are left as the boot loader configures them, because
the Zynq GPIO driver does not apply pinctrl.

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

## SPI controllers

Zephyr's `zynq7000.dtsi` has no SPI nodes yet, so `zynq7000-spi.dtsi` adds both PS
SPI controllers: SPI0 at `0xE0006000` (GIC SPI 26) and SPI1 at `0xE0007000` (GIC SPI 49),
as in Linux's `zynq-7000.dtsi`, with 128-entry, 8-bit FIFOs. They use Zephyr's
`cdns,spi` driver (the controller is Cadence IP), under the compatible
`xlnx,zynq-spi-r1p6` whose binding (`app/dts/bindings/spi/`) adds the pin
configuration properties that `cdns,spi` lacks.

The reference design leaves the SPI controllers disabled as well, so `board.c` sets
them up when one is enabled in the devicetree:

1. hold the enabled controllers in reset (`SPI_RST_CTRL`);
2. set `SPI_REF_CLK` to IO PLL (1000 MHz) ÷ 7 = **142.86 MHz** (`SPI_CLK_CTRL`, shared by
   both controllers), faster than CPU_1x (111 MHz);
3. enable the controllers' bus clocks (`APER_CLK_CTRL` bits 14 and 15);
4. release the reset;
5. apply SPI1's pin configuration.

The controller divides SPI_REF_CLK by 4 to 256, so SCLK can be 8.93, 4.46, 2.23, 1.12
or 0.56 MHz within the sensors' 10 MHz limit. A build-time check ties the devicetree's
`clock-frequency` to the divider.

The chip select is the controller's own SS0 on MIO13, not a GPIO. In master mode the
controller does not start a transfer while its SS0 input is low. When SS0 is not on a
pin, that input comes from the PL, where it is low in the reference design: with a
GPIO chip select on MIO13 every transfer stalled with its bytes in the TX FIFO (found
on the bench, 2026-09-29; see [Known issues](../known-issues.md)). A GPIO chip select
needs SS0 on a pin (idle, high) or tied high through EMIO in the Vivado design.

Zephyr v4.4.2's `cdns,spi` driver also used the register address without mapping it,
which faults on the Cortex-A9 with its MMU on; patch `0001-spi-cdns-map-the-register-block`
backports the upstream fix (see [Dependencies and patches](dependencies.md)).

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
| `app/boards/te0701-spi1.overlay` | Enables SPI1 with its chip select on MIO13, for the [SPI sensor benches](../tests/spi-sensors.md) |

## Loading over JTAG

`board.cmake` selects Zephyr's `xsdb` runner, so `west flash` works. The runner runs
`support/xsdb.cfg`, which resets the system, runs `support/ps7_init.tcl` (exported
from the reference design variant `04_30_1i_1gb`) and loads the image into DDR.
