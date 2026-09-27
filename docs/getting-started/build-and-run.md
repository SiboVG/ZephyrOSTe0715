# Building and running

Activate the environment first; all commands run from the workspace root unless
stated otherwise.

```bash
cd ZephyrOSTe0715
source .venv/bin/activate
```

## Zephyr applications

The three plain Zephyr applications build with `west build` for the board `te0715`:

```bash
west build -b te0715 app                                            # LED/GPIO demo
west build -b te0715 app/apps/can_bringup -d build/can_bringup      # CAN test
west build -b te0715 app/apps/csp_node    -d build/csp_node         # libcsp node
```

To load an application into the board's memory over JTAG and start it:

```bash
PATH=/tools/Xilinx/Vitis/2022.1/bin:$PATH west flash -d build/can_bringup
```

`west flash` resets the board, initialises the processor with the reference
design's `ps7_init.tcl` (clocks, DDR, pins), copies the image into DDR and starts
it. Nothing is written to flash or to the SD card: after a power cycle the board
boots from its SD card again.

For quick work, `hw_test.py` does build, load and console capture in one step:

```bash
app/scripts/hw_test.py run app/apps/can_bringup --seconds 10
```

## The F Prime application

`app/apps/fprime_csp_bench` is an F Prime project. Here F Prime's build tool
(`fprime-util`) is in charge and pulls in Zephyr, rather than the other way round.

```bash
cd app/apps/fprime_csp_bench
fprime-util generate        # once, or after changing CMake files
fprime-util build -j16
```

The results are in `build-fprime-automatic-zephyr/zephyr/`:

| File | Use |
|---|---|
| `zephyr.elf` | Load over JTAG: `xsdb ../../boards/trenz/te0715/support/xsdb.cfg build-fprime-automatic-zephyr/zephyr/zephyr.elf` |
| `zephyr.bin` | Install on the SD card: see [Booting](../guide/boot.md) |

!!! note "Sibling repositories"
    The F Prime application builds the `CspLibparam` component from
    `../CspLibparamFprimeTest` and the library from `../fprime-csp-libparam`,
    relative to the workspace. Both must be on their Zephyr branches.

The two sensor benches build the same way, in `app/apps/fprime_ina229_bench` and
`app/apps/fprime_adxl355_bench`, with `../fprime-ina229` or `../fprime-adxl355` next
to the workspace; see [SPI sensor benches](../tests/spi-sensors.md#building).

## Upstream `main` builds

The worktrees `zephyr-main/` and `zephyr-can-main/` hold the Zephyr branches for
the upstream pull requests. To build against one of them, point `ZEPHYR_BASE` at it
and use the system CMake: upstream Zephyr needs CMake 3.28, while F Prime's
requirements install CMake 3.26 into `.venv`.

```bash
PATH=/usr/bin:$PATH app/scripts/hw_test.py test tests/drivers/can/api \
    --zephyr-base $PWD/zephyr-can-main --build-root $PWD/build/hw-main \
    -x-DEXTRA_DTC_OVERLAY_FILE=$PWD/app/boards/te0701-can1.overlay
```

Next: [Connecting to the board](../guide/connect.md).
