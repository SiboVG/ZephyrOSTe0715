# Test case specifications

Each test case states what it verifies, what it needs, how it is run and when it
passes. The procedures are explained in the [test guides](../tests/index.md);
`app/scripts/collect_results.sh` runs TC-01 to TC-08 in one go, and
`app/scripts/sensor_bench.py` runs TC-13 to TC-21.

Common preconditions for all test cases: the workspace built as in
[Getting started](../getting-started/index.md), and the TE0715 on the JTAG/UART cable.

---

## TC-01 Kernel test suites

| | |
|---|---|
| **Verifies** | `TE-BSP-001`, `TE-BSP-002` |
| **Preconditions** | – |
| **Procedure** | `app/scripts/hw_test.py test tests/kernel/common tests/kernel/timer/timer_api tests/kernel/sched/schedule_api tests/kernel/mem_protect/stackprot` |
| **Pass criteria** | Every suite reports `PROJECT EXECUTION SUCCESSFUL`; no failed test case; skipped cases only for features the platform lacks (nested IRQ offload, SMP, mapped stacks) |
| **Evidence** | `tests_kernel_*.log`, `zephyr-suites.txt` |

## TC-02 Console UART driver

| | |
|---|---|
| **Verifies** | `TE-UART-001` |
| **Preconditions** | – |
| **Procedure** | `app/scripts/hw_test.py test tests/drivers/uart/uart_basic_api` (keyboard prompts answered by the script) |
| **Pass criteria** | 7 of 7 test cases pass; 0 garbled characters in the console output |
| **Evidence** | `tests_drivers_uart_uart_basic_api.log`, `zephyr-suites.txt` |

## TC-03 CAN driver in loopback

| | |
|---|---|
| **Verifies** | `TE-CAN-001` |
| **Preconditions** | For the upstream run: the `zephyr-can-main` worktree (branch `xlnx-can`) and CMake ≥ 3.28 |
| **Procedure** | `app/scripts/hw_test.py test --timeout 150 -x-DEXTRA_DTC_OVERLAY_FILE=app/boards/te0701-can1.overlay tests/drivers/can/api tests/drivers/can/timing`, once on the workspace Zephyr and once with `--zephyr-base zephyr-can-main` |
| **Pass criteria** | Both suites report `PROJECT EXECUTION SUCCESSFUL` on both branches; skipped cases only for features not enabled or not supported (RTR, minimum bitrate, CAN FD, transceiver, power management) |
| **Evidence** | `tests_drivers_can_*.log`, `upstream-main-tests_drivers_can_*.log`, `can-suites*.txt` |

## TC-04 Transceiver wiring check

| | |
|---|---|
| **Verifies** | `TE-CAN-002` |
| **Preconditions** | Transceiver connected as in [Hardware setup](../tests/hardware-setup.md); no other node active on the bus (Kvaser down) |
| **Procedure** | `app/scripts/hw_test.py run app/apps/can_bringup --seconds 6` |
| **Pass criteria** | The transmit error counter reaches 128 (error-passive) and stays there with only ACK errors; no bus-off |
| **Evidence** | Console output quoted in [CAN bus](../tests/can-bus.md#1-check-the-wiring-without-a-peer) |

## TC-05 CAN echo

| | |
|---|---|
| **Verifies** | `TE-CAN-003`, `TE-BSP-002` |
| **Preconditions** | TC-04 passed; Kvaser `can0` up at 1 Mbit/s and on the same bus |
| **Procedure** | Load `apps/can_bringup`; on the host `app/scripts/can_echo_test.py can0 --count 1000` |
| **Pass criteria** | 1000 of 1000 echoes received with identical payload within 100 ms each; heartbeat period 1 s ± 10 %; board error-active; script prints `PASS` |
| **Evidence** | `can-bringup.txt`, `can-echo.txt` |

## TC-06 F Prime server against the Linux client

| | |
|---|---|
| **Verifies** | `TE-CSP-001`, `TE-PAR-001` |
| **Preconditions** | TC-05 passed; Linux CspBench built (CspLibparamFprimeTest `main`); `apps/fprime_csp_bench` loaded, started on node 6061/8 |
| **Procedure** | 1. `CspBench --role client --can can0 --node 100 --peer 6061 --write-test --write-value 0xA5A55A5A`. 2. `CspBench --role client --can can0 --node 100 --peer 6061 --param-id 201 --param-type u8 --write-test --write-value 1 --successes 2 --attempts 3` |
| **Pass criteria** | 1. `[CSP_BENCH_RESULT] PASS attempts=5 successes=5`. 2. `PASS` with 2 successes, and the board logs `led_d4 = 1: LED D4 on` and `led_d4 = 0: LED D4 off` for each cycle |
| **Evidence** | `fprime-e2e-jtag.txt`, `fprime-e2e-jtag-transcript.log` |

## TC-07 Serial shell client tools

| | |
|---|---|
| **Verifies** | `TE-CSP-002`, `TE-CSP-003` |
| **Preconditions** | TC-06 set-up; a Linux `CspBench --role server --can can0 --node 102` running |
| **Procedure** | On the board's shell: `csp ping 102`; `csp ping 102 32 1000 --nocrc`; `param get 102 200 u32`; `param set 102 200 u32 0xCAFEBABE`; the same with `--confirm`; `param set 102 200 u8 300 --confirm`; `param get 102 200 u32`; `param set 102 200 u32 0x12345678 --confirm`; `csp ping 4242 32 500`; `can show can@e0009000` |
| **Pass criteria** | Ping replied; `--nocrc` ping not answered (the peer requires CRC32); value 0x12345678 read; unconfirmed write refused; out-of-range value refused; confirmed write read back as 0xcafebabe; restore read back; ping to the absent node times out; CAN error counters 0 |
| **Evidence** | `fprime-e2e-*.txt`, `fprime-e2e-*-transcript.log` |

## TC-08 Standalone SD card boot

| | |
|---|---|
| **Verifies** | `TE-BOOT-001`, `TE-BSP-003` |
| **Preconditions** | The FlatSat image installed with `sd_install.py`; nothing loaded over JTAG |
| **Procedure** | Reset the board; wait for the start window to expire; repeat TC-06 and TC-07; then `kernel reboot cold` |
| **Pass criteria** | Server ready on node 6061 without any input; all checks of TC-06 and TC-07 pass; after the reboot the board comes back through U-Boot to `CSP_BENCH_READY` |
| **Evidence** | `fprime-e2e-sd-boot.txt`, `fprime-e2e-sd-boot-transcript.log` |

## TC-09 FlatSat

| | |
|---|---|
| **Verifies** | `TE-FS-001` to `TE-FS-004` |
| **Preconditions** | Configuration agreed with the FlatSat owner; FlatSat image on the SD card; Mac or Linux laptop with `flatsat_console.py` |
| **Procedure** | [FlatSat test](../tests/flatsat.md), steps 1 to 10 |
| **Pass criteria** | No bus errors caused (steps 5, 10); pings answered both ways; csh lists, reads and writes the TE0715 parameters and the LED follows `led_d4`; approved FlatSat parameters read; any approved write read back and restored |
| **Evidence** | Console log from `flatsat_console.py`, csh session log, the completed [FlatSat as-run record](flatsat-record-template.md); run on 2026-09-24, see [its record](as-run-flatsat-2026-09-24.md) |

## TC-10 csh against the TE0715

| | |
|---|---|
| **Verifies** | `TE-PAR-002` |
| **Preconditions** | TC-06 set-up; csh 2.10.5 built on the host with the Kvaser `can0` as its CAN interface |
| **Procedure** | `app/scripts/csh_check.py` with `app/scripts/csh_tc10.csh`: `ping 6061`, `node 6061`, `list download`, `list`, get and set of both parameters by name (with restore), `list forget 6061`, the manual `list add -a 1 -m c` commands, get and set again |
| **Pass criteria** | Ping replied; `list download` receives `bench_integer` (200) and `led_d4` (201); values read as 305419896 and 0; each `set` read back; the board logs the LED switching on and off for each `set led_d4`; the manually added parameters give the same results |
| **Evidence** | `tc10-transcript.log` (csh and board console), `tc10-commands.csh`, `environment.txt` |

## TC-11 Node from te0715.txt

| | |
|---|---|
| **Verifies** | `TE-BOOT-002` |
| **Preconditions** | TC-08 set-up; the FlatSat image and the current `boot.scr` on the SD card |
| **Procedure** | Run by `collect_results.sh`: 1. `sd_install.py config --node 6062`; `fprime_e2e.py --sd-boot --node 6062 --source te0715.txt`. 2. Load the image over JTAG (TC-06), which runs right after step 1 without clearing RAM. 3. `sd_install.py config --defaults`; `fprime_e2e.py --sd-boot --source te0715.txt` (TC-08) |
| **Pass criteria** | 1. The banner reads `node 6062/8 (te0715.txt)` and every TC-06/TC-07 check passes against node 6062, also after `kernel reboot cold`. 2. The banner reads `node 6061/8 (default)`. 3. Node 6061 with a settings-free file. A refused file is covered by the unit tests |
| **Evidence** | `sd-config-*.txt`, `fprime-e2e-sd-config*.txt`, `fprime-e2e-jtag*.txt`, `fprime-e2e-sd-boot*.txt` |

## TC-12 No node acknowledges

| | |
|---|---|
| **Verifies** | `TE-CAN-005` |
| **Preconditions** | Kvaser interface down (`sudo ip link set can0 down`), so nothing on the bus acknowledges |
| **Procedure** | 1. `can_noack_test.py --elf build/noack-before/zephyr/zephyr.elf` (`apps/csp_node` without the libcsp patch) and the same with `build/noack-after` (with the patch): watch its once-a-second pings for 20 s. 2. `can_noack_test.py --fprime --elf <FlatSat image>`: `csp ping`, `param get`, `bench info` and `can show` on the shell |
| **Pass criteria** | 1. Without the patch the pings stop (the sender hangs): this reproduces the defect. With the patch they continue with "no reply". 2. Each `csp ping` reports no reply and `param get` fails, within their timeouts; the shell keeps answering; the controller is error-passive, not bus-off |
| **Evidence** | Console transcripts from `can_noack_test.py --log` |

## TC-13 SPI1 link to the INA229

| | |
|---|---|
| **Verifies** | `TE-SPI-001`, `TE-SPI-002`, `TE-SPI-003` |
| **Preconditions** | INA229 wired to Pmod J1 as in [SPI sensor benches](../tests/spi-sensors.md), CAN transceiver disconnected; `apps/fprime_ina229_bench` loaded, `[INA229_BENCH_READY]` printed |
| **Procedure** | 1. `ina id`. 2. For each SCLK of the clock table in mode 1, and 1.116 MHz in mode 2: `ina spi <hz> <mode>`, `ina soak 20000`. 3. Logic-analyzer capture of `ina id` at 1.116 MHz, mode 1 |
| **Pass criteria** | 1. `result=PASS` (MANUFACTURER_ID 0x5449, die 0x229, command-byte MISO byte 0). 2. Every soak `result=PASS`: no wrong value, no non-zero command byte, no driver error. 3. SCLK idle low; CS low from before the first to after the last clock edge of each transfer and high between transfers; MOSI changes on rising edges; 24 clocks per transfer |
| **Evidence** | `sensor_bench.py ina229` package: `results.txt`, `transcript.log`; the capture file |

## TC-14 INA229 through the F Prime manager

| | |
|---|---|
| **Verifies** | `TE-INA-001`, `TE-INA-002` |
| **Preconditions** | TC-13 passed; shunt and load connected, load current steady |
| **Procedure** | As in [INA229 bench, TC-14](../tests/ina229.md#tc-14-the-f-prime-manager): initialize, 20 readings, `report` and `snapshot` commands, a zero-shunt `init` command, the alert configuration and DIAG_ALRT read back, `reset-acc`, `ina timing 200`, `ina stream start 100 20` |
| **Pass criteria** | Initialization OK; 20 readings OK with valid mask 0x7f, die temperature 5 to 50 °C, current = shunt voltage / shunt resistance within 1 %, power = bus voltage × current within 0.5 %; commands answered OK with telemetry; the zero-shunt command answered VALIDATION_ERROR without a change of `Errors`; ALATCH set with MEMSTAT still 1; 200 timed reads without failure; 20 streamed rows without failure |
| **Evidence** | `sensor_bench.py ina229` package |

## TC-15 INA229 readings against reference instruments

| | |
|---|---|
| **Verifies** | `TE-INA-003` |
| **Preconditions** | TC-14 passed; calibrated voltmeter across VBUS and GND, current reference (calibrated ammeter in series, or a known load), thermometer next to the INA229; their uncertainty known |
| **Procedure** | `sensor_bench.py ina229 --interactive`: 50 readings with a steady load, the reference values typed in; then the load current reversed and 20 readings |
| **Pass criteria** | Bus voltage within 0.05 % + 2.5 mV + reference uncertainty; current within 0.05 % + shunt tolerance + reference uncertainty + 1 µV / shunt resistance, for both directions; die temperature within 2 °C of the thermometer |
| **Evidence** | `sensor_bench.py` package; instrument models, serial numbers and calibration dates in the as-run record |

## TC-16 INA229 faults

| | |
|---|---|
| **Verifies** | `TE-INA-004` |
| **Preconditions** | TC-14 passed |
| **Procedure** | `sensor_bench.py ina229 --interactive`: MISO disconnected, reconnected; the INA229 supply removed, restored without reinitialization, then `ina init` |
| **Pass criteria** | With MISO disconnected, `ina id` fails and no reading is OK; after reconnection readings are OK again. With the supply removed no reading is OK; after `ina init` readings are OK. What the manager reports after the supply returns, before `ina init`, is recorded (INFO) |
| **Evidence** | `sensor_bench.py` package |

## TC-17 SPI1 link to the ADXL355

| | |
|---|---|
| **Verifies** | `TE-SPI-001`, `TE-SPI-002`, `TE-SPI-003` |
| **Preconditions** | ADXL355 wired to Pmod J1 as in [SPI sensor benches](../tests/spi-sensors.md), CAN transceiver disconnected; `apps/fprime_adxl355_bench` loaded, `[ADXL355_BENCH_READY]` printed |
| **Procedure** | 1. `adxl id`. 2. For each SCLK of the clock table in mode 0: `adxl spi <hz> 0`, `adxl soak 20000`. 3. Logic-analyzer capture of `adxl id` at 1.116 MHz |
| **Pass criteria** | 1. `result=PASS` (0xAD, 0x1D, 0xED). 2. Every soak `result=PASS`. 3. SCLK idle low; CS low over each whole transfer and high between transfers; MOSI changes on falling edges; 40 clocks for the 5-byte identity read |
| **Evidence** | `sensor_bench.py adxl355` package; the capture file |

## TC-18 ADXL355 through the F Prime manager

| | |
|---|---|
| **Verifies** | `TE-ADXL-001`, `TE-ADXL-002`, `TE-ADXL-004` |
| **Preconditions** | TC-17 passed; the sensor at rest; no 1.024 MHz clock connected |
| **Procedure** | As in [ADXL355 bench, TC-18](../tests/adxl355.md#tc-18-the-f-prime-manager): initialize at ±2 g and 125 Hz, temperature, 200 samples, self test, `adxl drdy 20`, `adxl timing 200`, `snapshot` and `app-report` commands, an invalid range, `init-synced` without an external clock and one read |
| **Pass criteria** | Initialization OK; temperature 5 to 50 °C; 200 fresh samples, magnitude of the mean 0.79 to 1.21 g; self test X, Y 0.1 to 0.6 g and Z 0.5 to 3.0 g; STATUS bits 7:5 read 0 and DATA_RDY cleared by a STATUS read; 200 timed reads without failure; commands answered OK with telemetry, sensor count 1; the invalid range refused; no sample fresh without the external clock |
| **Evidence** | `sensor_bench.py adxl355` package |

## TC-19 ADXL355 synchronized application

| | |
|---|---|
| **Verifies** | `TE-ADXL-003` |
| **Preconditions** | TC-18 passed; the sensor at rest |
| **Procedure** | As in [ADXL355 bench, TC-19](../tests/adxl355.md#tc-19-the-synchronized-application): at 1 kHz output data rate, triggered at 500 Hz (2500 frames) and 2 kHz (4000 frames); at 4 kHz, triggered at 2 kHz (10000 frames); at SCLK 8.93 MHz, at 4 kHz triggered at 4 kHz and at 2 kHz triggered at 4 kHz (20000 frames each) |
| **Pass criteria** | 500 Hz: 2500 complete frames, none stale, no sequence gap, no missed tick. 2 kHz at 1 kHz ODR: 35 % to 65 % stale, none implausible or with another error, no missed tick. 2 kHz at 4 kHz ODR: 10000 complete frames. 4 kHz at 4 kHz ODR: longest acquisition below 250 µs, no missed tick or sequence gap, none implausible or with another error; the share of stale frames (the timer and the sensor's oscillator drift against each other) is recorded. 4 kHz at 2 kHz ODR: 35 % to 65 % stale, with the same limits |
| **Evidence** | `sensor_bench.py adxl355` package |

## TC-20 ADXL355 six orientations

| | |
|---|---|
| **Verifies** | `TE-ADXL-005` |
| **Preconditions** | TC-18 passed; a block with square faces for the sensor board |
| **Procedure** | `sensor_bench.py adxl355 --interactive`: +Z, −Z, +X, −X, +Y and −Y up in turn, 200 samples each |
| **Pass criteria** | The axis along gravity 0.83 to 1.17 g with the right sign, the others below 0.2 g; from each pair, 0 g offset within ±75 mg and sensitivity within 0.92 to 1.08 of nominal |
| **Evidence** | `sensor_bench.py` package |

## TC-21 ADXL355 faults

| | |
|---|---|
| **Verifies** | `TE-ADXL-006` |
| **Preconditions** | TC-18 passed |
| **Procedure** | `sensor_bench.py adxl355 --interactive`: MISO disconnected (identity, reads, a 50-frame stream), reconnected (stream); CS disconnected (reads), reconnected (reads) |
| **Pass criteria** | With MISO disconnected, `adxl id` fails, no sample is valid and all frames are partial; after reconnection all frames complete. With CS disconnected no sample is valid; after reconnection samples are valid again |
| **Evidence** | `sensor_bench.py` package |
