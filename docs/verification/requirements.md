# Requirements and verification

This matrix records what the TE0715 bring-up is required to do and how each
requirement is verified. It follows the conventions of fprime-csp-libparam's
[requirements and verification](https://github.com/SiboVG/fprime-csp-libparam/blob/main/docs/requirements-and-verification.md)
record.

**Status values**

| Status | Meaning |
|---|---|
| Verified on hardware | The test case passed in a retained as-run record (logs and checksums in `docs/verification/evidence/`) |
| Observed during bring-up | Demonstrated on hardware during development and recorded in these docs, but not part of a retained as-run package |
| Pending hardware execution | The procedure exists; it has not been run yet |
| Not met | The test case failed in a retained as-run record |
| To do | Required, but no procedure exists yet; planned for later |

All hardware verification uses one asset set: TE0715-05-71I33-L on a TE0701, TI
SN65HVD233 transceiver on a TCAN-SOIC8-EVM, Kvaser USBcan Light 2xHS (see
[Hardware setup](../tests/hardware-setup.md)). No requirement is flight-qualified.

## Board and drivers

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| `TE-BSP-001` | Zephyr shall boot on the TE0715 and pass the kernel test suites for timing, scheduling and stack protection. | Board `te0715` | [TC-01](test-cases.md#tc-01-kernel-test-suites) | Verified on hardware |
| `TE-BSP-002` | The system timer shall run at the rate Zephyr assumes (333.33 MHz). | `CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC` | TC-01 (`timer_api`); TC-05 heartbeat period measured by the host | Verified on hardware |
| `TE-BSP-003` | `sys_reboot()` shall reset the processing system, after which the board boots from its SD card. | `board.c` (`PSS_RST_CTRL`) | [TC-08](test-cases.md#tc-08-standalone-sd-card-boot) | Verified on hardware with images at address 0; TC-08 to be rerun with the `0x100000` boot script (`TE-BSP-004`) |
| `TE-BSP-004` | Zephyr's system RAM on the TE0715 (`zephyr,sram`) shall contain only DDR that every bus master can reach: it shall start at `0x100000`, above the first 512 KiB of DDR that only the CPUs reach (UG585, table 4-1), and every image shall be loaded and started at that address. Rationale: Zephyr drivers place DMA memory in system RAM and assume every master reaches it (zephyrproject-rtos/zephyr#123456); `0x100000` is the DDR base of Xilinx's own BSPs and of `qemu_cortex_a9`. | `te0715.dts` (`sram0`), `boot/boot.cmd`, `uboot_load.py` | `app/tests/scripts/test_memory_map.py`; [TC-26](test-cases.md#tc-26-system-ram-above-the-cpu-only-ddr) | Verified on hardware ([as-run 2026-10-25](as-run-memory-map-2026-10-25.md)) |
| `TE-UART-001` | The console UART driver shall pass `uart_basic_api` without corrupting any transmitted character. | `uart_xlnx_ps` fixes (PR #119996) | [TC-02](test-cases.md#tc-02-console-uart-driver) | Verified on hardware |
| `TE-UART-002` | A baud-rate change with `uart_configure()` shall take effect immediately. | `uart_xlnx_ps` fix 1 | Runtime 115200 → 57600 → 115200 switch | Observed during bring-up |
| `TE-CAN-001` | The Zynq PS CAN driver shall pass Zephyr's CAN API and timing test suites on Zephyr v4.4.2 and on upstream `main`. | `can_xlnx` | [TC-03](test-cases.md#tc-03-can-driver-in-loopback) | Verified on hardware |
| `TE-CAN-002` | The CAN1 signals on Pmod J1 shall drive an external 3.3 V transceiver. | Pinctrl, `board.c` clocks | [TC-04](test-cases.md#tc-04-transceiver-wiring-check) | Observed during bring-up |
| `TE-CAN-003` | The TE0715 shall exchange frames with an independent CAN controller at 1 Mbit/s without loss or corruption. | `can_xlnx`, `apps/can_bringup` | [TC-05](test-cases.md#tc-05-can-echo) | Verified on hardware |
| `TE-CAN-004` | The driver shall recover automatically from bus-off. | `can_xlnx` bus-off handling | Unwired run: bus-off, recovery, error-active cycle | Observed during bring-up |
| `TE-CAN-005` | When no node acknowledges its frames, CSP sends on the TE0715 shall fail within a bounded time, and the rest of the software shall keep running. | libcsp patch `0002` (`can_zephyr.c`) | [TC-12](test-cases.md#tc-12-no-node-acknowledges) | Verified on hardware |

## CSP, libparam and F Prime

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| `TE-CSP-001` | The F Prime `CspLibparam` component shall run on the TE0715 in the server role and pass the unmodified Linux CspBench client test (ping, read, write with read-back, restore) 5 times. | `apps/fprime_csp_bench`, `ZephyrCanTransport` | [TC-06](test-cases.md#tc-06-f-prime-server-against-the-linux-client) | Verified on hardware |
| `TE-CSP-002` | The TE0715 shall act as a CSP/libparam client from its serial shell: ping, read, confirmed write with read-back. | `shell_cmds.c` | [TC-07](test-cases.md#tc-07-serial-shell-client-tools) | Verified on hardware |
| `TE-CSP-003` | A write from the shell shall be refused unless explicitly confirmed. | `param set ... --confirm` | TC-07 | Verified on hardware |
| `TE-CSP-004` | A value typed for a remote parameter shall be sent exactly or not at all: a value that does not fit its type, a negative value for an unsigned type, inf, nan and non-numbers shall be refused. | `bench_value.c` | Unit test `app/tests/bench` (CI, native_sim); TC-07 (`u8 300` on the board) | Verified on hardware and in CI |
| `TE-PAR-001` | The TE0715 shall expose its LED D4 as the libparam parameter `led_d4` (ID 201, `uint8`), so that another node can switch it and read its state. | `shell_cmds.c` | [TC-06](test-cases.md#tc-06-f-prime-server-against-the-linux-client) (LED part), TC-10; LED seen switching by the operator | Verified on hardware |
| `TE-PAR-002` | csh shall be able to load the TE0715's parameters (`list download`) and read and write them by name. | libparam list service (`vmem_server_loop`) | [TC-10](test-cases.md#tc-10-csh-against-the-te0715) | Verified on hardware |
| `TE-BOOT-001` | The TE0715 shall boot the FlatSat image from its SD card without JTAG and pass TC-06 and TC-07. | `boot/boot.cmd`, `sd_install.py` | [TC-08](test-cases.md#tc-08-standalone-sd-card-boot) | Verified on hardware with images at address 0; TC-08 to be rerun with the `0x100000` boot script (`TE-BSP-004`) |
| `TE-BOOT-002` | The CSP node and prefix shall be settable in a file on the SD card and apply at every boot. A file that is not exactly understood shall be refused as a whole, and a JTAG-loaded image shall not use settings left over from an earlier SD boot. | `te0715.txt`, `boot.cmd`, `bench_config.c` | [TC-11](test-cases.md#tc-11-node-from-te0715txt); unit tests `app/tests/bench`, `app/tests/scripts` | Verified on hardware |
| `TE-CSP-005` | The CSP router task shall run above the F Prime tasks that use CSP. | `CONFIG_APP_CSP_ROUTER_PRIORITY`, fprime-csp-libparam `StackConfig::routerPriority` | `kernel thread list` in the TC-06 transcript: `CspRouter` priority 54, `cspLibparam` 57 | Verified on hardware |

## Ethernet

The TE0715 is to carry CSP over Ethernet as well as CAN (CSP over UDP, fprime-csp-libparam
`FCL-UDP-*`). The first requirement covers only the hardware path. It is checked from
U-Boot, whose Zynq Ethernet driver is known to work, so that a Zephyr networking problem
cannot be confused with a wiring, PHY or clocking problem. The Zephyr and CSP
requirements follow once this one passes.

100 Mbit/s full duplex is CubeSpec's baseline Ethernet speed, on the bench and on the
FlatSat (project decision, 2026-10-23). The link is required at that speed; 1000 Mbit/s
may be run for information.

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| `TE-ETH-001` | The TE0715's Ethernet path (PS GEM0 on MIO16–27, MDIO on MIO52/53, the module's Ethernet PHY and the TE0701's RJ45 jack) shall exchange frames in both directions with a directly connected host at 100 Mbit/s full duplex, without receive errors at the host. | `ps7_init.tcl` (MIO and GEM0 clock of the reference design); U-Boot's Zynq GEM driver, driven by `uboot_eth_check.py` | [TC-23](test-cases.md#tc-23-ethernet-link-from-u-boot) | Verified on hardware ([as-run 2026-10-23](as-run-ethernet-2026-10-23.md)) |
| `TE-ETH-002` | Zephyr on the TE0715 shall bring up the Ethernet port at 100 Mbit/s full duplex with a static IPv4 address, answer ICMP echo requests from a directly connected host for every payload up to the 1500-byte MTU, including frames that span the driver's 512-byte receive and transmit buffers, and reach the host with its own echo requests, without loss and without receive errors at the host. | Board `te0715.dts` (`gem0`), Zephyr's Xilinx GEM driver, `apps/eth_bringup`; `zephyr_eth_check.py` | [TC-24](test-cases.md#tc-24-zephyr-ethernet-bring-up) | Verified on hardware ([as-run 2026-10-23](as-run-zephyr-ethernet-2026-10-23.md)) |
| `TE-ETH-003` | The F Prime `CspLibparam` server on the TE0715 shall carry CSP over UDP on its Ethernet port and, over the direct link at 100 Mbit/s, pass the unmodified Linux CspBench client test (ping, read, write with read-back, restore) 5 times, switch `led_d4` (201) on and off the same way, and answer pings from libcsp's own UDP interface (`csp_if_udp`, as csh's `csp add udp`). | `apps/fprime_csp_bench` with `CONFIG_APP_CSP_UDP`, fprime-csp-libparam `UdpTransport` | [TC-25](test-cases.md#tc-25-csp-and-libparam-over-ethernet) | Verified on hardware ([as-run 2026-10-23](as-run-csp-ethernet-2026-10-23.md)) |
| `TE-ETH-004` | The TE0715 shall act as a CSP/libparam client over UDP from its serial shell: ping, read, and confirmed write with read-back, the same as over CAN (`TE-CSP-002`, `TE-CSP-003`). | `shell_cmds.c` over `UdpTransport` | [TC-25](test-cases.md#tc-25-csp-and-libparam-over-ethernet) | Verified on hardware ([as-run 2026-10-23](as-run-csp-ethernet-2026-10-23.md)) |

## SPI sensors

These requirements use the sensor benches' own assets: an INA229 board (the one of
fprime-ina229's FT232H bench) or an ADXL355 board wired to Pmod J1, with the reference
instruments named in the as-run record. See [SPI sensor benches](../tests/spi-sensors.md).

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| `TE-SPI-001` | The PS SPI1 controller shall exchange data with a device on Pmod J1 without error at every SCLK from 558 kHz to 8.93 MHz, in the device's SPI mode. | `zynq7000-spi.dtsi`, `board.c` (SPI clocks, pin configuration), `te0701-spi1.overlay`, Zephyr's `cdns,spi` driver with patch `0001-spi-cdns-map-the-register-block` | [TC-13](test-cases.md#tc-13-spi1-link-to-the-ina229), [TC-17](test-cases.md#tc-17-spi1-link-to-the-adxl355) step 2 | Verified on hardware with the ADXL355 ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)); INA229 (TC-13) pending |
| `TE-SPI-002` | The chip select on MIO13 shall be asserted over each whole transfer and released between transfers. | SPI1's own SS0 on MIO13 (pin configuration `spi1_0_ss0`); the driver's manual slave select | TC-13, TC-17 steps 1, 2, by function | Verified on hardware with the ADXL355 ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)); INA229 (TC-13) pending |
| `TE-SPI-003` | SCLK shall idle and data shall change on the edges of the selected SPI mode. | `cdns,spi`; `TeBench::BenchSpi` | TC-13, TC-17 steps 1, 2, by function | Verified on hardware with the ADXL355 ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)); INA229 (TC-13) pending |
| `TE-INA-001` | fprime-ina229's manager shall initialize and read a real INA229 through the F Prime SPI port, with all seven channels valid in continuous mode and consistent current and power. | `apps/fprime_ina229_bench` | [TC-14](test-cases.md#tc-14-ina229-through-the-f-prime-manager) | Pending hardware execution |
| `TE-INA-002` | The manager's commands shall work through the command dispatcher with the library's responses; a rejected argument shall not count as a device error, and the alert configuration shall leave MEMSTAT unchanged. | `ShellCommander`, library | TC-14 | Pending hardware execution |
| `TE-INA-003` | INA229 readings shall agree with reference instruments within the data sheet's accuracy, the shunt tolerance and the instruments' uncertainty, for both current directions. | library | [TC-15](test-cases.md#tc-15-ina229-readings-against-reference-instruments) | Pending hardware execution |
| `TE-INA-004` | With MISO disconnected or the INA229 unpowered, no reading shall be reported valid; readings shall recover when the fault is removed (after reinitialization for a supply loss). | library | [TC-16](test-cases.md#tc-16-ina229-faults) | Pending hardware execution |
| `TE-ADXL-001` | fprime-adxl355's manager shall initialize a real ADXL355 on its internal clock and return fresh samples, a temperature and a self-test response within the data sheet's limits. | `apps/fprime_adxl355_bench` | [TC-18](test-cases.md#tc-18-adxl355-through-the-f-prime-manager) | Verified on hardware ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)) |
| `TE-ADXL-002` | The manager's and the application's commands shall work through the command dispatcher; invalid arguments shall be refused. | `ShellCommander`, library | TC-18 | Verified on hardware ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)) |
| `TE-ADXL-003` | The synchronized application, triggered from one timing thread, shall deliver complete frames when triggered no faster than the output data rate, mark samples that are not new as stale rather than valid, and finish one sensor's acquisition within the 250 µs period at 4 kHz. | library, timing thread in `bench_cmds.cpp` | [TC-19](test-cases.md#tc-19-adxl355-synchronized-application) | Verified on hardware at SCLK 8.93 MHz ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md): longest 4 kHz acquisition 171 µs in run 5, 49 µs in run 6 with fprime-adxl355 `67bdcb0`, which moves fault events off the acquisition path); at 1.116 MHz a fault edge took 265 µs before that change (run 3) |
| `TE-ADXL-004` | On the silicon, STATUS bits 7:5 shall read 0 and a STATUS read shall clear DATA_RDY; without its external clock, a synchronized configuration shall give no fresh sample. | library | TC-18 steps 5, 8; TC-22 step 4 (on the external clock) | Verified on hardware ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)); in the synchronized mode: Verified on hardware ([as-run 2026-10-02](as-run-adxl355-pl-2026-10-02.md)) |
| `TE-ADXL-005` | Each axis shall read ±1 g along gravity with the data sheet's sensitivity and 0 g offset limits. | library (typical sensitivities) | [TC-20](test-cases.md#tc-20-adxl355-six-orientations) | Verified on hardware ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)) |
| `TE-ADXL-006` | With MISO or CS disconnected, no sample or frame shall be reported valid; samples and frames shall recover when the link is restored. | library | [TC-21](test-cases.md#tc-21-adxl355-faults) | Verified on hardware ([as-run 2026-09-29](as-run-adxl355-2026-09-29.md)) |
| `TE-ADXL-007` | With the ADXL355 on an external 1.024 MHz clock and synchronization pulse, the synchronized application, triggered by the PL's sync interrupt, shall deliver complete frames at 4 kHz, timestamped with their sync instants, with the sensor's sample timing following the pulse; the start-up sequence of the ACC board design notes (initialize with the external clock and synchronization set, start the clock, start the pulses, enable after one filter group delay) shall give no corrupted first samples. | library (`INITIALIZE_ALL`, fprime-adxl355 ADXL-INT-003 and ADXL-INT-008 in the synchronized mode), cubespec-pl `acc` and `timebase`, `pl.cpp` | [TC-22](test-cases.md#tc-22-adxl355-on-the-pls-external-clock-and-synchronization-pulse) steps 1 to 8 | Verified on hardware ([as-run 2026-10-02](as-run-adxl355-pl-2026-10-02.md)) |
| `TE-ADXL-008` | When the external clock stops, no sample shall be reported valid beyond fprime-adxl355's `FROZEN_REPEAT_LIMIT` (8) repeats: the library shall report `FROZEN_DATA`, or `STALE_DATA` if the clock stopped with the last sample already read. Samples shall be valid again once the clock and pulses return, without reinitialization. When the pulses stop, PL-triggered acquisition shall stop and its waits time out. | library (ADXL-DEV-013), `pl.cpp`, `bench_cmds.cpp` | TC-22 steps 9 to 12 | Verified on hardware ([as-run 2026-10-02](as-run-adxl355-pl-2026-10-02.md)) |

`TE-SPI-002` and `TE-SPI-003` are verified by function, without a waveform capture.
Every soak transfer is one multi-byte read of registers with known contents. If the chip
select were released within a transfer, the sensor would stop answering and the rest of
the bytes would read as the pull-up's all ones; if it were held across two transfers,
the second command byte would be taken as data and the values would not match. With the
wrong clock polarity or phase, the sensor would sample the command a bit off and the
identity and soak values would be wrong. None of this occurred in 100000 checked
transfers in each ADXL355 run (20000 at each of five SCLKs). A waveform would also show
the timing margins and the signal quality on the jumper leads; they depend on the wiring
and are left to the flight hardware.

These cases also cover part of the libraries' open hardware items: fprime-ina229's
INA-HIL-001 (readback on a real INA229, here with the Zephyr driver; its waveform part
stays open), INA-HIL-002 (one operating point per run), INA-HIL-003 and INA-HIL-004
(continuous acquisition, accumulator reset, MEMSTAT on silicon), INA-HIL-005 (MISO and
supply faults) and INA-HIL-006 (read duration); and fprime-adxl355's acceptance-plan
steps 1, 2, 6, 8 and 9 for one sensor on its internal clock. The libraries' records
decide what each run closes.

## FlatSat

| ID | Requirement | Verification | Status |
|---|---|---|---|
| `TE-FS-001` | The TE0715 shall join the FlatSat CAN bus without causing bus errors. | [TC-09](test-cases.md#tc-09-flatsat) steps 5, 10 | Verified on hardware ([FlatSat run](as-run-flatsat-2026-09-24.md), after a power cycle) |
| `TE-FS-002` | FlatSat nodes and the TE0715 shall reach each other with CSP ping. | TC-09 steps 6, 8 | Verified on hardware ([FlatSat run](as-run-flatsat-2026-09-24.md)) |
| `TE-FS-003` | csh on the FlatSat shall read and write the TE0715's parameters, including switching LED D4. | TC-09 steps 4, 6, 7 | Verified on hardware ([FlatSat run](as-run-flatsat-2026-09-24.md)) |
| `TE-FS-004` | The TE0715 shall read approved FlatSat parameters. | TC-09 steps 8, 9 | Verified on hardware ([FlatSat run](as-run-flatsat-2026-09-24.md)) |
