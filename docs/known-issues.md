# Known issues and limitations

## Functional

| Issue | Impact | Possible fix |
|---|---|---|
| libcsp's Zephyr CAN interface (`can_zephyr.c`) calls `can_send()` without a callback. Its 100 ms timeout only covers getting a TX slot; Zephyr then waits `K_FOREVER` for the frame to be sent | If nothing acknowledges on the bus (disconnected, or all other nodes off), the controller retransmits forever (error-passive, never bus-off) and the sending thread, and CSP with it, blocks until a node acknowledges | libcsp patch: pass a completion callback, so `can_send()` returns once the frame is queued; the next frame then waits at most 100 ms for the slot and fails with `-EAGAIN`, which CSP reports as a failed send. Upstreamable |
| The libcsp router task runs at the lowest preemptible priority: `Stack::startRouter()` uses `TASK_PRIORITY_DEFAULT`, which fprime-zephyr maps to Zephyr priority 99 | Under load, any F Prime task, and even the shell, can delay CSP routing and with it every reply | fprime-csp-libparam: add a router priority (and stack size) to `StackConfig`, default unchanged; the TE0715 deployment sets it above `cspLibparam` |
| The CSP node is chosen at boot (10 s window) and not stored | Must be retyped after every power cycle if not the default | Zephyr has no SD card or QSPI driver for the Zynq-7000, but U-Boot can read the card: `boot.cmd` imports a text file (`te0715.txt`, `csp_node=6062`) from the FAT partition and writes the value to a reserved RAM word that the application reads. Edit the file on any computer to change the node |
| `can_xlnx` does not support listen-only or one-shot modes | CSP does not need them | Listen-only needs a controller revision with snoop mode |
| `led_d4` is not persistent and has no F Prime telemetry | After a reset the LED is off; F Prime does not see the value | Add it to the F Prime component if it becomes a real parameter |
| No csh release pins exactly the libcsp revision used here | All csh 2.10.x releases use libcsp 9721ca4; the TE0715 uses libcsp `csh/2.10` 5a95e5c. The protocol is the same (CSP v2, libparam protocol 2) | – |

## Board and build

| Issue | Notes |
|---|---|
| The CAN clock is set up by `board.c`, not the FSBL | The reference design has CAN disabled. For flight, enable CAN1 in the Vivado design so the FSBL configures it |
| MIO7/MIO9 pin muxing comes from the FSBL / `ps7_init` | The Zynq GPIO driver does not apply pinctrl; UART0 and CAN1 do |
| Pmod J1 power pins | Trenz documentation and the Pmod standard disagree; measure (see [Hardware setup](tests/hardware-setup.md#1-connect-the-transceiver-to-pmod-j1)) |
| MIO12/13 are also connected to the TE0701 CPLD | Documented as unused for AMD modules; confirmed in practice by the CAN tests |
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
