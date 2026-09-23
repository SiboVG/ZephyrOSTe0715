# Test case specifications

Each test case states what it verifies, what it needs, how it is run and when it
passes. The procedures are explained in the [test guides](../tests/index.md);
`app/scripts/collect_results.sh` runs TC-01 to TC-08 in one go.

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
| **Preconditions** | Configuration agreed with the FlatSat owner; FlatSat image on the SD card; Mac with `flatsat_console.py` |
| **Procedure** | [FlatSat test from macOS](../tests/flatsat.md), steps 1 to 10 |
| **Pass criteria** | No bus errors caused (steps 5, 10); pings answered both ways; csh lists, reads and writes the TE0715 parameters and the LED follows `led_d4`; approved FlatSat parameters read; any approved write read back and restored |
| **Evidence** | Console log from `flatsat_console.py`, csh session log, the completed [FlatSat as-run record](flatsat-record-template.md) |

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
