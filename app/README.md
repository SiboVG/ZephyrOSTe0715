# TE0715 Zephyr, CAN and F Prime bring-up

Zephyr board support for the Trenz TE0715-05-71I33-L (Zynq-7030) on a TE0701
carrier, a CAN bus on the carrier's Pmod J1 (new Zynq PS CAN driver), libcsp and
libparam (`csh/2.10`) as Zephyr modules, and the CubeSpec F Prime CSP/libparam
bench server running on Zephyr. Includes the hardware test tools and the FlatSat
procedure.

**Documentation: <https://sibovg.github.io/ZephyrOSTe0715/>, built from `../docs/`
at the repository root (MkDocs, `../mkdocs.yml`).** It covers setup, the user guide (serial shell commands), the
architecture, the test procedures including the FlatSat test, and the verification
records with the raw test logs.

## Quick start

```sh
# workspace: the repository root; app/ is the west manifest and a Zephyr module
git clone git@github.com:SiboVG/ZephyrOSTe0715.git && cd ZephyrOSTe0715
west init -l app && west update
west patch clean && west patch apply      # after every west update
west sdk install -t arm-zephyr-eabi       # Zephyr SDK 1.0.1

# build and load over JTAG (xsdb from Vitis 2022.1 on PATH)
west build -b te0715 app/apps/can_bringup
west flash

# F Prime FlatSat image
cd app/apps/fprime_csp_bench && fprime-util generate && fprime-util build
```

## Contents

| Path | Contents |
|---|---|
| `west.yml` | Zephyr (SiboVG fork, v4.4.2 + UART fixes + CAN driver), libcsp, libparam, F Prime, fprime-zephyr |
| `boards/trenz/te0715/` | Board: devicetree, pinctrl, CAN clock setup, JTAG loading (`west flash`) |
| `boards/*.overlay` | TE0701 carrier: Pmod GPIO, CAN1 |
| `src/`, `apps/` | LED/GPIO demo, CAN bring-up, libcsp node, F Prime bench server (FlatSat image) |
| `zephyr/` | Module glue: libparam build (`CONFIG_LIBPARAM`), `patches.yml` + patches |
| `boot/` | U-Boot script for booting Zephyr from the SD card |
| `scripts/` | Hardware tests, SD card installer, FlatSat console |

## Tests

```sh
app/scripts/collect_results.sh path/to/CspBench can0   # all hardware tests, logs to ../docs/verification/evidence/
```

Individual tools: `hw_test.py` (ztest suites and apps), `can_echo_test.py` (CAN echo
over SocketCAN), `fprime_e2e.py` (F Prime server and shell against the Linux
CspBench), `sd_install.py` (SD card boot), `flatsat_console.py` (logging console for
macOS/Linux). See `../docs/tests/`.

## Documentation

From the workspace root (`..`):

```sh
python3 -m venv .venv-docs && .venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve            # http://127.0.0.1:8000
```

## Related repositories

- [SiboVG/zephyr](https://github.com/SiboVG/zephyr): branches `te0715-can-v4.4.2`
  (pinned), `xuartps-fixes` (UART PR #119996), `xlnx-can` (CAN driver on upstream
  `main`, PR #120163)
- [SiboVG/fprime-csp-libparam](https://github.com/SiboVG/fprime-csp-libparam):
  `main`
- [SiboVG/CspLibparamFprimeTest](https://github.com/SiboVG/CspLibparamFprimeTest):
  `main` (the Linux CspBench used as the test peer)
