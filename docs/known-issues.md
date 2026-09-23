# Known issues and limitations

## Functional

| Issue | Impact | Possible fix |
|---|---|---|
| libcsp's Zephyr CAN interface uses a blocking `can_send()`, which waits indefinitely for the frame to be transmitted | If nothing acknowledges on the bus (disconnected or all other nodes off), the sending thread blocks until a node acknowledges | Send with a callback and a bounded wait in `csp_can_tx_frame()` (libcsp patch) |
| The libcsp router task runs at the lowest preemptible priority (default priority) | Under load, F Prime tasks can delay CSP routing | Let `fprime-csp-libparam`'s `StackConfig` set the router priority |
| libparam list/vmem service (port 12) not served | csh cannot download the parameter list from the TE0715 | Run libparam's `vmem_server_loop` in a thread |
| The CSP node is chosen at boot (10 s window) and not stored | Must be retyped after every power cycle if not the default | Persist it (e.g. QSPI or a file on the SD card) |
| `can_xlnx` does not support listen-only or one-shot modes | CSP does not need them | Listen-only needs a controller revision with snoop mode |

## Board and build

| Issue | Notes |
|---|---|
| The CAN clock is set up by `board.c`, not the FSBL | The reference design has CAN disabled. For flight, enable CAN1 in the Vivado design so the FSBL configures it |
| MIO7/MIO9 pin muxing comes from the FSBL / `ps7_init` | The Zynq GPIO driver does not apply pinctrl; UART0 and CAN1 do |
| Pmod J1 power pins | Trenz documentation and the Pmod standard disagree; measure (see [Hardware setup](hardware-setup.md#can-wiring)) |
| MIO12/13 are also connected to the TE0701 CPLD | Documented as unused for AMD modules; confirmed in practice by the CAN tests |
| Only the TE0715-05-71I33-L (xc7z030) was tested | Other TE0715 variants need `SOC_XC7Z0xx` and possibly their own `ps7_init.tcl` |
| F Prime pins CMake 3.26 in the shared venv | Upstream Zephyr `main` needs 3.28: use `PATH=/usr/bin:$PATH` for `main` builds |
| `west patch apply` is not idempotent | Run `west patch clean && west patch apply` |

## Pre-existing test failures elsewhere

Two Python tests of CspLibparamFprimeTest fail on its `main` branch and are unrelated
to this work: `test_flatsat_docs_describe_environment_contract_and_legacy_precedence`
and `test_flatsat_guide_documents_environment_and_read_only_pdu_profile` (FlatSat
documentation checks).
