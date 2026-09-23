# Getting started

## Directory layout

The F Prime application expects this repository's west workspace next to the two
CubeSpec F Prime repositories:

```text
Sandbox/
├── ZephyrOSTe0715/            west workspace (topdir)
│   ├── app/                   this repository (manifest repository, Zephyr module)
│   ├── zephyr/                SiboVG/zephyr, branch te0715-can-v4.4.2
│   ├── modules/lib/libcsp     Space Inventor libcsp csh/2.10
│   ├── modules/lib/libparam   Space Inventor libparam csh/2.10
│   ├── modules/fprime/        F Prime and fprime-zephyr
│   └── .venv/                 Python environment (west, Zephyr and F Prime tools)
├── fprime-csp-libparam/       branch zephyr-can-transport
└── CspLibparamFprimeTest/     branch zephyr-transport
```

## Set up the workspace

```bash
mkdir ZephyrOSTe0715 && cd ZephyrOSTe0715
git clone <this repository> app
uv venv .venv && source .venv/bin/activate      # or: python3 -m venv .venv
uv pip install west
west init -l app
west update
west patch clean && west patch apply
uv pip install -r modules/fprime/fprime/requirements.txt -r zephyr/scripts/requirements.txt
west sdk install -t arm-zephyr-eabi              # Zephyr SDK 1.0.1
```

!!! warning "Patches after every `west update`"
    `west update` resets libcsp, libparam and fprime-zephyr to their pinned
    revisions, which removes the patches from `zephyr/patches.yml`. Run
    `west patch clean && west patch apply` again afterwards; `west patch apply` on
    its own fails if a patch is already applied.

!!! note "`uv` environment"
    The environment has no `pip` module; install packages with
    `uv pip install --python .venv/bin/python ...`.

Loading images over JTAG needs AMD `xsdb` (Vitis 2022.1 under `/tools/Xilinx`); see
[Hardware setup](hardware-setup.md) for the cable permissions.

## Build and run the Zephyr applications

```bash
source .venv/bin/activate
west build -b te0715 app                             # LED/GPIO demo
west build -b te0715 app/apps/can_bringup -d build/can_bringup
PATH=/tools/Xilinx/Vitis/2022.1/bin:$PATH west flash # loads into DDR over JTAG
```

`app/scripts/hw_test.py run <app>` builds, loads and shows the console in one step;
see [Tests](tests/index.md).

## Build the F Prime application

`apps/fprime_csp_bench` is an F Prime project: F Prime's CMake drives the build and
includes Zephyr (fprime-zephyr).

```bash
cd app/apps/fprime_csp_bench
fprime-util generate
fprime-util build -j16
# image: build-fprime-automatic-zephyr/zephyr/zephyr.elf and zephyr.bin
```

Load it over JTAG with the board's xsdb script, or install it on the SD card (see
[SD card boot](sd-card-boot.md)):

```bash
xsdb ../../boards/trenz/te0715/support/xsdb.cfg \
    build-fprime-automatic-zephyr/zephyr/zephyr.elf
```

## Build the Linux CspBench (host peer)

The host side of the CAN tests is the Linux acceptance bench, built as described in
its README:

```bash
sudo apt install -y build-essential cmake ninja-build git pkg-config python3-venv \
    iproute2 can-utils libsocketcan-dev libbsd-dev
cd CspLibparamFprimeTest
./scripts/bootstrap_dependencies.sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PATH="$PWD/.venv/bin:$PATH" fprime-util generate -DPYTHON="$PWD/.venv/bin/python"
PATH="$PWD/.venv/bin:$PATH" fprime-util build
# build-artifacts/Linux/Deployments_CspBench/bin/CspBench
```

## CMake versions

F Prime's `requirements.txt` pins CMake 3.26.0 into the virtual environment, which
shadows the system CMake. Zephyr v4.4.2 accepts it; upstream Zephyr `main` needs
CMake 3.28 or newer. For builds against `main` (the `xlnx-can` and `xuartps-fixes`
branches), put the system CMake first: `PATH=/usr/bin:$PATH`.

## Build these docs

```bash
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve          # http://127.0.0.1:8000
.venv-docs/bin/mkdocs build --strict # the check to run before committing
```
