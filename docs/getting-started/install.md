# Installing the tools

These steps set up a fresh Ubuntu machine. On the development PC they have already
been done.

## 1. Host packages

```bash
sudo apt install -y git cmake ninja-build python3-venv device-tree-compiler \
    can-utils libsocketcan-dev libbsd-dev build-essential pkg-config
```

`can-utils`, `libsocketcan-dev` and `libbsd-dev` are only needed for the Linux
CspBench that acts as the CAN test peer.

Install [uv](https://docs.astral.sh/uv/) for the Python environment, or use plain
`python3 -m venv` and `pip` instead.

## 2. Create the workspace

```bash
git clone git@github.com:SiboVG/ZephyrOSTe0715.git
cd ZephyrOSTe0715      # the repository root is also the west workspace
uv venv .venv
source .venv/bin/activate
uv pip install west
west init -l app       # use app/west.yml as the manifest
west update            # fetch Zephyr, libcsp, libparam, F Prime, fprime-zephyr
```

`west update` takes a while the first time: F Prime alone is about 700 MB.

## 3. Apply the patches

A few projects need small changes that are not (yet) upstream. They are kept as
patch files in `app/zephyr/patches/` and applied with Zephyr's `west patch` command:

```bash
west patch clean && west patch apply
```

!!! warning "After every `west update`"
    `west update` resets the patched projects to their pinned revisions, which
    removes the patches. Run `west patch clean && west patch apply` again after each
    update. `west patch apply` on its own fails if a patch is already applied; the
    `clean` first makes it safe to repeat.

[Dependencies and patches](../architecture/dependencies.md) explains each patch.

## 4. Python requirements and the Zephyr SDK

```bash
uv pip install -r modules/fprime/fprime/requirements.txt -r zephyr/scripts/requirements.txt
west sdk install -t arm-zephyr-eabi     # Zephyr SDK 1.0.1, ARM toolchain only
```

Both requirement files go into the same environment because the F Prime build runs
Zephyr's Python scripts and F Prime's tools from one interpreter.

!!! note "`uv` environments have no `pip`"
    Install packages with `uv pip install --python .venv/bin/python ...`, not with
    `.venv/bin/pip`.

## 5. AMD xsdb and cable permissions

Loading images over JTAG uses AMD's `xsdb`, part of Vitis. The development PC has
Vitis 2022.1 in `/tools/Xilinx`; the scripts find it there automatically.

Two udev rules give the logged-in user access to the Digilent JTAG/UART cable, also
after it is unplugged and plugged back in:

```bash
# JTAG (rules shipped with Vivado)
sudo cp /tools/Xilinx/Vivado/2022.1/data/xicom/cable_drivers/lin64/install_script/install_drivers/52-xilinx-*.rules \
    /etc/udev/rules.d/
# UART console
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{manufacturer}=="Digilent", TAG+="uaccess"' \
    | sudo tee /etc/udev/rules.d/70-digilent-uart.rules
sudo udevadm control --reload && sudo udevadm trigger --action=add
```

## 6. The Linux CspBench (test peer)

The CAN tests use the Linux acceptance bench as the other node on the bus. Build it
as described in its own documentation:

```bash
cd ../CspLibparamFprimeTest
git switch zephyr-transport
./scripts/bootstrap_dependencies.sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PATH="$PWD/.venv/bin:$PATH" .venv/bin/fprime-util generate -DPYTHON="$PWD/.venv/bin/python"
PATH="$PWD/.venv/bin:$PATH" .venv/bin/fprime-util build
```

The executable is `build-artifacts/Linux/Deployments_CspBench/bin/CspBench`.

Next: [Building and running](build-and-run.md).
