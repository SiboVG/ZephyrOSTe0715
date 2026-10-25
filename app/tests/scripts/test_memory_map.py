# SPDX-License-Identifier: Apache-2.0
"""TE-BSP-004: system RAM only in DDR that every bus master reaches, and images loaded there.

UG585 (Zynq-7000 TRM), table 4-1: DDR below 0x80000 is reachable by the CPUs only,
not by the AXI_HP ports or the other bus masters (the GEMs, the DMA controller).
Zephyr places DMA memory in system RAM, so `zephyr,sram` must not include it.
"""

import os
import re

import pytest

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DTS = os.path.join(APP, 'boards', 'trenz', 'te0715', 'te0715.dts')
BOOT_CMD = os.path.join(APP, 'boot', 'boot.cmd')

CPU_ONLY_DDR_END = 0x80000      # UG585 table 4-1: 0x0 to 0x7ffff, CPUs only
DDR_BASE = 0x100000             # Xilinx BSPs and qemu_cortex_a9 start DDR here
DDR_END = 0x40000000            # 1 GiB DDR3 on the TE0715-05-71I33-L


def read(path):
    with open(path) as f:
        return f.read()


def sram_region():
    """(base, size) of the node chosen as zephyr,sram in the board's devicetree."""
    dts = read(DTS)
    label = re.search(r'zephyr,sram\s*=\s*&(\w+);', dts).group(1)
    node = re.search(label + r':\s*memory@([0-9a-fA-F]+)\s*\{(.*?)\};', dts, re.S)
    reg = re.search(r'reg\s*=\s*<\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*>', node.group(2))
    base, size = int(reg.group(1), 16), int(reg.group(2), 16)
    assert int(node.group(1), 16) == base, 'unit address and reg disagree'
    return base, size


def test_sram_excludes_the_cpu_only_ddr():
    base, _ = sram_region()
    assert base >= CPU_ONLY_DDR_END


def test_sram_starts_at_the_ddr_base_and_ends_with_the_ddr():
    base, size = sram_region()
    assert base == DDR_BASE
    assert base + size == DDR_END


@pytest.mark.parametrize('command', ['fatload mmc 0 {addr:#x} zephyr.bin', 'go {addr:#x}'])
def test_sd_boot_loads_and_starts_the_image_at_the_sram_base(command):
    base, _ = sram_region()
    lines = [line.strip() for line in read(BOOT_CMD).splitlines() if not line.lstrip().startswith('#')]
    assert command.format(addr=base) in lines


def test_sd_boot_loads_nothing_else_below_the_sram_base():
    base, _ = sram_region()
    for line in read(BOOT_CMD).splitlines():
        found = re.match(r'\s*(?:fatload mmc 0|go)\s+(0x[0-9a-fA-F]+)', line)
        if found:
            assert int(found.group(1), 16) >= base, line


def test_console_loader_uses_the_sram_base():
    import uboot_load
    base, _ = sram_region()
    assert uboot_load.LOAD_ADDR == base
