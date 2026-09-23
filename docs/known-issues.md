# Known issues and limitations

## Functional

| Issue | Impact | Possible fix |
|---|---|---|
| libcsp's Zephyr CAN interface uses a blocking `can_send()`, which waits indefinitely for the frame to be transmitted | If nothing acknowledges on the bus (disconnected or all other nodes off), the sending thread blocks until a node acknowledges | Send with a callback and a bounded wait in `csp_can_tx_frame()` (libcsp patch) |
| The libcsp router task runs at the lowest preemptible priority (default priority) | Under load, F Prime tasks can delay CSP routing | Let `fprime-csp-libparam`'s `StackConfig` set the router priority |
| The CSP node is chosen at boot (10 s window) and not stored | Must be retyped after every power cycle if not the default | Persist it (e.g. QSPI or a file on the SD card) |
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
