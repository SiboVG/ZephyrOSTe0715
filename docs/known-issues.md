# Known issues and limitations

## Functional

| Issue | Impact | Possible fix |
|---|---|---|
| While no node acknowledges, the one frame that the CAN controller is retransmitting is sent as soon as a node appears, possibly long after its CSP packet was dropped | The receiver gets a fragment of an old packet, which CSP's reassembly discards | None needed; a CAN API to abort a pending frame would avoid it |
| The TE0715 image needs the `router-task-config` branch of fprime-csp-libparam ([PR #2](https://github.com/SiboVG/fprime-csp-libparam/pull/2)) and `router-priority` of CspLibparamFprimeTest ([PR #3](https://github.com/SiboVG/CspLibparamFprimeTest/pull/3)) | With both repos on `main`, the F Prime image does not build (`Config::routerPriority` unknown) | Merge both pull requests |
| `can_xlnx` does not support listen-only or one-shot modes | CSP does not need them | Listen-only needs a controller revision with snoop mode |
| `led_d4` is not persistent and has no F Prime telemetry | After a reset the LED is off; F Prime does not see the value | Add it to the F Prime component if it becomes a real parameter |
| No csh release pins exactly the libcsp revision used here | All csh 2.10.x releases use libcsp 9721ca4; the TE0715 uses libcsp `csh/2.10` 5a95e5c. The protocol is the same (CSP v2, libparam protocol 2) | – |

## Fixed

| Was | Fix |
|---|---|
| A CSP send blocked forever when no node acknowledged (libcsp called `can_send()` without a callback; also so on libcsp `develop`) | libcsp patch `0002`: a completion callback, so a send fails after at most 100 ms; test case TC-12 |
| The CSP router ran at the lowest Zephyr priority | Router priority in fprime-csp-libparam's `StackConfig`, set to F Prime 45 (Zephyr 54) on the TE0715 |
| The CSP node was not stored | `te0715.txt` on the SD card ([Configuration](guide/configuration.md#the-csp-node-te0715txt-on-the-sd-card)); test case TC-11 |
| `param set` truncated out-of-range values | `bench_value.c`; TE-CSP-004 |
| An SD boot could hang or crash depending on what was left in RAM (3 of 4 boots right after another image had run). U-Boot started Zephyr with its MMU and caches on | `boot.cmd` turns them off before `go` (`icache off; dcache off`), as for a JTAG load: 6 of 6 boots passed |

## Board and build

| Issue | Notes |
|---|---|
| The CAN clock is set up by `board.c`, not the FSBL | The reference design has CAN disabled. For flight, enable CAN1 in the Vivado design so the FSBL configures it |
| MIO7/MIO9 pin muxing comes from the FSBL / `ps7_init` | The Zynq GPIO driver does not apply pinctrl; UART0 and CAN1 do |
| Pmod J1 power pins | Trenz documentation and the Pmod standard disagree; measure (see [Hardware setup](tests/hardware-setup.md#1-connect-the-transceiver-to-pmod-j1)) |
| MIO12/13 are also connected to the TE0701 CPLD | Documented as unused for AMD modules; confirmed in practice by the CAN tests |
| The SPI clocks are set up by `board.c`, not the FSBL | As for CAN: the reference design has SPI disabled. For flight, enable the SPI controller in the Vivado design |
| MIO10/11 (SPI1 MOSI/MISO) also reach the TE0701 CPLD, which has an I2C slave there | Not yet shown harmless for SPI traffic; the soak steps and a logic-analyzer capture (TC-13, TC-17) check it |
| A Pmod module plugged into Pmod J1 lands on MIO0, MIO9 and the console UART | Wire SPI sensors by hand ([SPI sensor benches](tests/spi-sensors.md#wiring-on-pmod-j1)) |
| Zephyr's `cdns,spi` driver on the Zynq-7000: the controller has no FIFO-clear bits | The driver writes TXCLR/RXCLR (Config bits 19/20), which this controller does not have (Xilinx `xspips_hw.h`). A transfer that ends in an RX overflow could leave bytes in the FIFO for the next one; the libraries' checks would reject that data |
| Zephyr's `cdns,spi` driver reads the last received byte as soon as the TX FIFO drains | Linux's driver waits 10 µs there in master mode (Xilinx AR 65885); Xilinx's standalone driver no longer does. A lost last byte would show in the soak steps, most likely at 558 kHz |
| The INA229 loses its configuration with its supply | After a supply interruption it is back in its reset state (SHUNT_CAL 0); TC-16 records what fprime-ina229 reports until it is reinitialized |
| The Zynq-7000 SPI master does not transfer while its SS0 input is low | With SS0 not on a pin, the input comes from the PL and is low in the reference design; a GPIO chip select on MIO13 stalled every transfer. The benches use SS0 on MIO13 as the chip select. A GPIO chip select needs SS0 on a pin (idle) or tied high through EMIO |
| Zephyr's `cdns,spi` driver never configures `cs-gpios` chip selects | The pins stay inputs, so a device on a GPIO chip select is never selected. Fixed in upstream PR [#120741](https://github.com/zephyrproject-rtos/zephyr/pull/120741) (open; tested on this board with an ADXL355 on MIO9). The benches use SPI1's own SS0 and do not need it |
| Zephyr v4.4.2's `cdns,spi` faults at boot on the TE0715 | The driver used the register address without mapping it (MMU on); patch `0001-spi-cdns-map-the-register-block` backports the upstream fix |
| Console printing is slow (about 13 ms per line at 115200 baud) | The benches print events and telemetry from their own threads at the shell's priority, with time slicing off, so no line is cut and the ADXL355 frame timing thread never waits for the console |
| Zephyr headers before F Prime headers break the build | Zephyr defines a macro `EMPTY` (see [F Prime on Zephyr](architecture/fprime.md#the-sensor-benches)) |
| The sensor benches are not built in CI | CI does not fetch F Prime; it builds the LED demo with the SPI1 overlay, which covers the board support |
| Only the TE0715-05-71I33-L (xc7z030) was tested | Other TE0715 variants need `SOC_XC7Z0xx` and possibly their own `ps7_init.tcl` |
| F Prime pins CMake 3.26 in the shared venv | Upstream Zephyr `main` needs 3.28: use `PATH=/usr/bin:$PATH` for `main` builds |
| csh 2.10.5 does not link with Ubuntu 24.04's meson 1.3.2 | Use a current meson from PyPI (see [csh against the board](tests/csp-libparam.md#5-csh-against-the-board)) |
| csh's `list add` needs `-a 1 -m c` for the TE0715's parameters | Without them csh hides the parameters or cannot read them; `list download` is not affected |
| `west patch apply` is not idempotent | Run `west patch clean && west patch apply` |

## Pre-existing test failures elsewhere

Two Python tests of CspLibparamFprimeTest fail on its `main` branch and are unrelated
to this work: `test_flatsat_docs_describe_environment_contract_and_legacy_precedence`
and `test_flatsat_guide_documents_environment_and_read_only_pdu_profile` (FlatSat
documentation checks).
