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
