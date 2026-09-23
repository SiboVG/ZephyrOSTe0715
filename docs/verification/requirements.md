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

All hardware verification uses one asset set: TE0715-05-71I33-L on a TE0701, TI
SN65HVD233 transceiver on a TCAN-SOIC8-EVM, Kvaser USBcan Light 2xHS (see
[Hardware setup](../tests/hardware-setup.md)). No requirement is flight-qualified.

## Board and drivers

| ID | Requirement | Implementation | Verification | Status |
|---|---|---|---|---|
| `TE-BSP-001` | Zephyr shall boot on the TE0715 and pass the kernel test suites for timing, scheduling and stack protection. | Board `te0715` | [TC-01](test-cases.md#tc-01-kernel-test-suites) | Verified on hardware |
| `TE-BSP-002` | The system timer shall run at the rate Zephyr assumes (333.33 MHz). | `CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC` | TC-01 (`timer_api`); TC-05 heartbeat period measured by the host | Verified on hardware |
| `TE-BSP-003` | `sys_reboot()` shall reset the processing system, after which the board boots from its SD card. | `board.c` (`PSS_RST_CTRL`) | [TC-08](test-cases.md#tc-08-standalone-sd-card-boot) | Verified on hardware |
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
| `TE-BOOT-001` | The TE0715 shall boot the FlatSat image from its SD card without JTAG and pass TC-06 and TC-07. | `boot/boot.cmd`, `sd_install.py` | [TC-08](test-cases.md#tc-08-standalone-sd-card-boot) | Verified on hardware |
| `TE-BOOT-002` | The CSP node and prefix shall be settable in a file on the SD card and apply at every boot. A file that is not exactly understood shall be refused as a whole, and a JTAG-loaded image shall not use settings left over from an earlier SD boot. | `te0715.txt`, `boot.cmd`, `bench_config.c` | [TC-11](test-cases.md#tc-11-node-from-te0715txt); unit tests `app/tests/bench`, `app/tests/scripts` | Verified on hardware |
| `TE-CSP-005` | The CSP router task shall run above the F Prime tasks that use CSP. | `CONFIG_APP_CSP_ROUTER_PRIORITY`, fprime-csp-libparam `StackConfig::routerPriority` | `kernel thread list` in the TC-06 transcript: `CspRouter` priority 54, `cspLibparam` 57 | Verified on hardware |

## FlatSat

| ID | Requirement | Verification | Status |
|---|---|---|---|
| `TE-FS-001` | The TE0715 shall join the FlatSat CAN bus without causing bus errors. | [TC-09](test-cases.md#tc-09-flatsat) steps 5, 10 | **Pending hardware execution** |
| `TE-FS-002` | FlatSat nodes and the TE0715 shall reach each other with CSP ping. | TC-09 steps 6, 8 | **Pending hardware execution** |
| `TE-FS-003` | csh on the FlatSat shall read and write the TE0715's parameters, including switching LED D4. | TC-09 steps 4, 6, 7 | **Pending hardware execution** |
| `TE-FS-004` | The TE0715 shall read approved FlatSat parameters. | TC-09 step 8 | **Pending hardware execution** |
