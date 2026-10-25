# Dependencies and patches

## Pinned revisions

`app/west.yml` pins every dependency to an exact commit, so the workspace can be
rebuilt identically.

| Project | Revision | Reason for this revision |
|---|---|---|
| zephyr | SiboVG `te0715-can-v4.4.2` (`70b56a2`) | Zephyr v4.4.2 with the UART fixes and the CAN driver |
| libcsp | `csh/2.10` (`5a95e5c`) | The matched pair used by fprime-csp-libparam and the FlatSat |
| libparam | `csh/2.10` (`d78da56`) | idem |
| fprime | `35d4c0e` (v4.2.0-267) | The F Prime revision fprime-csp-libparam is tested with |
| fprime-zephyr | `6e2a411` | The last revision that works with that F Prime: later ones need nasa/fprime#5615 |
| cmsis, cmsis_6 | from Zephyr's manifest | The only Zephyr modules this Cortex-A9 build needs |

Zephyr SDK 1.0.1 (the version Zephyr v4.4.2 requires) provides the compiler.

## Patches

Changes that are not upstream yet are kept as patch files in `app/zephyr/patches/`
and listed in `app/zephyr/patches.yml`; `west patch apply` applies them.

| Project | Patch | Problem it solves | Upstream |
|---|---|---|---|
| libcsp | `0001-zephyr-include-time.h-from-the-C-library` | Zephyr 4.x removed `<zephyr/posix/time.h>`; the build failed | could be offered |
| libparam | `0001-vmem-client-do-not-shadow-abort` | A variable named `abort` clashed with the C library's `abort()` | could be offered |
| fprime-zephyr | `0001-lora-enum-command-handler-signature` | The LoRa driver did not compile with the pinned F Prime | already upstream (`b76db2b`) |
| fprime-zephyr | `0002-os-task-default-stack-size` | A task started with the default stack size failed (the size was passed as `SIZE_MAX`); the CSP router could not start | could be offered |
| fprime-zephyr | `0003-os-task-map-fprime-priorities` | All F Prime tasks ran at the same, lowest priority | could be offered; changes behaviour for existing users |
| zephyr | `0001-spi-cdns-map-the-register-block` | The `cdns,spi` driver used its devicetree register address without mapping it: on the TE0715 (MMU on) the first register write took a translation fault at `0xe0007000` and Zephyr halted at boot | backport of upstream `1b7a2b68e0e0` (PR #115179); drop when the fork moves past it |
| zephyr | `0002-eth-xlnx-gem-map-the-clock-control-register` | The Xilinx GEM Ethernet driver accessed its clock control register (SLCR `GEM0_CLK_CTRL`, `0xf8000140`) through the physical address, which the SoC's MMU table does not map: a translation fault at boot | fixed upstream in `fd9cd01ef774` (the switch to the separate MDIO and PHY drivers), too large to backport; drop when the fork moves past it |

Zephyr patch `0003-eth-xlnx-gem-dma-memory-in-ocm-on-zynq-7000` was removed on
2026-10-25. It put the GEM's DMA memory in the OCM because the board's system RAM
started at DDR address 0, below which the GEM cannot reach; the system RAM now starts
at `0x100000` instead (`TE-BSP-004`, [known issues](../known-issues.md)).

### Pending Zephyr upgrade

Patch `0002-eth-xlnx-gem-map-the-clock-control-register` can be dropped once the
Zephyr fork is based on a release that contains `fd9cd01ef774`. As of 2026-10-24 no
release does: it is only on `main`, and v4.4.2 is the latest release. That upgrade is
more than a rebase:

- `fd9cd01ef774` moves the GEM's PHY handling into separate MDIO and PHY drivers, so
  `te0715.dts` needs MDIO and PHY nodes. Zephyr has no driver for the board's Marvell
  88E151x PHY, only the generic `ethernet-phy` (`phy_mii`), which still has to bring
  the link up at 100 Mbit/s full duplex.
- The fork's CAN driver and UART fixes (PRs #120163 and #119996) are rebased onto the
  release, or dropped where merged.
- TC-01 to TC-26 are rerun and the upgrade gets a regression note in the SVR.

## Other integration changes

| Where | Change |
|---|---|
| `app/zephyr/CMakeLists.txt` | Builds libparam (`CONFIG_LIBPARAM`) with the same sources and settings as the Linux build of fprime-csp-libparam; enables the C library's BSD functions (`strlcpy`); marks the headers as system headers |
| fprime-csp-libparam `main` (merged from `zephyr-can-transport`, PR #1) | New `FprimeCsp_ZephyrCan` module; the host thread library is only linked on POSIX systems |
| CspLibparamFprimeTest `main` (merged from `zephyr-transport`, PR #2) | Transport chosen at compile time; include paths relative to the component, so another project can build it |
| `app/zephyr/module.yml` | `dts_root: .`, for the `xlnx,zynq-spi-r1p6` binding in `app/dts/bindings/` |
| `app/fprime-bench/` | F Prime library of the sensor benches (command sender, telemetry printer, SPI settings) |
| fprime-ina229, fprime-adxl355 | Checkouts next to the workspace, used unchanged by the sensor benches. Both are built and tested against the same F Prime revision as this workspace (`35d4c0e`) |
