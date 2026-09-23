#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install a Zephyr image on the TE0715's SD card, or restore PetaLinux, over JTAG + UART.

The SD card keeps its FSBL + U-Boot (BOOT.BIN). U-Boot's distro boot runs boot.scr
from the FAT partition; this script replaces it with one that loads zephyr.bin to
address 0 and jumps there. The card does not have to be removed:

1. reset the board over JTAG and stop U-Boot's autoboot on the serial console;
2. keep PetaLinux's boot.scr as boot_petalinux.scr (only if no backup exists yet);
3. load zephyr.bin and the new boot.scr into DDR over JTAG (the CPU is paused
   briefly at the U-Boot prompt);
4. verify the script image with `iminfo`, and write both files with `fatwrite`.

  app/scripts/sd_install.py install path/to/zephyr.bin
  app/scripts/sd_install.py restore        # boot PetaLinux again

Needs the Digilent JTAG/UART cable and AMD xsdb (see hw_test.py).
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

import serial

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'boot'))
from mkscr import make_script_image  # noqa: E402

from hw_test import find_port, find_xsdb  # noqa: E402

BOOT_CMD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'boot', 'boot.cmd')
BIN_ADDR = 0x02000000
SCR_ADDR = 0x03000000
BACKUP = 'boot_petalinux.scr'


class UBoot:
    def __init__(self, port, xsdb):
        self.serial = serial.Serial(port, 115200, timeout=0.05)
        self.xsdb = xsdb

    def _read_until(self, marker, timeout):
        buf = b''
        start = time.time()
        while marker not in buf and time.time() - start < timeout:
            buf += self.serial.read(4096)
        return re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', buf.decode(errors='replace'))

    def xsdb_eval(self, script):
        result = subprocess.run(['timeout', '120', self.xsdb, '-eval', script],
                                capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f'xsdb failed:\n{result.stdout}\n{result.stderr}')

    def reset(self, stop=True):
        self.serial.reset_input_buffer()
        self.xsdb_eval('connect; targets -set -nocase -filter {name =~ "APU*"}; '
                       'rst -system; disconnect')
        if not stop:
            return
        if 'Hit any key' not in self._read_until(b'Hit any key', 20):
            sys.exit('U-Boot did not start: is the board set to SD boot?')
        self.serial.write(b'\n')
        if 'Zynq> ' not in self._read_until(b'Zynq> ', 5):
            sys.exit('could not stop U-Boot autoboot')

    def run(self, cmd, timeout=30):
        self.serial.reset_input_buffer()
        self.serial.write(cmd.encode() + b'\n')
        out = self._read_until(b'Zynq> ', timeout)
        print(out.strip())
        return out

    def load(self, path, addr):
        """Copy a file into DDR over JTAG while U-Boot sits at its prompt."""
        self.xsdb_eval('connect; targets -set -nocase -filter {name =~ "*A9*#0"}; stop; '
                       f'dow -data {{{path}}} {addr:#x}; con; disconnect')

    def files(self):
        return self.run('fatls mmc 0')


def install(ub, zephyr_bin):
    listing = ub.files()
    if 'boot.scr' in listing and BACKUP not in listing:
        ub.run(f'fatload mmc 0 {SCR_ADDR:#x} boot.scr')
        ub.run(f'fatwrite mmc 0 {SCR_ADDR:#x} {BACKUP} ${{filesize}}')
    elif BACKUP in listing:
        print(f'{BACKUP} already exists, keeping it')

    with open(BOOT_CMD, 'rb') as f:
        script = make_script_image(f.read(), 'TE0715 Zephyr boot')
    with tempfile.NamedTemporaryFile(suffix='.scr', delete=False) as f:
        f.write(script)
        scr_path = f.name

    ub.load(os.path.abspath(zephyr_bin), BIN_ADDR)
    ub.load(scr_path, SCR_ADDR)
    if 'Verifying Checksum ... OK' not in ub.run(f'iminfo {SCR_ADDR:#x}'):
        sys.exit('boot.scr image check failed, nothing written')

    ub.run(f'fatwrite mmc 0 {BIN_ADDR:#x} zephyr.bin {os.path.getsize(zephyr_bin):#x}')
    ub.run(f'fatwrite mmc 0 {SCR_ADDR:#x} boot.scr {len(script):#x}')
    ub.files()
    os.unlink(scr_path)


def restore(ub):
    if BACKUP not in ub.files():
        sys.exit(f'no {BACKUP} on the card, nothing to restore')
    ub.run(f'fatload mmc 0 {SCR_ADDR:#x} {BACKUP}')
    ub.run(f'fatwrite mmc 0 {SCR_ADDR:#x} boot.scr ${{filesize}}')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['install', 'restore'])
    parser.add_argument('zephyr_bin', nargs='?', help='install: the zephyr.bin to boot')
    parser.add_argument('--port', help='UART device (default: Digilent cable interface 1)')
    parser.add_argument('--xsdb', help='path to xsdb (default: PATH, then /tools/Xilinx)')
    args = parser.parse_args()
    if args.action == 'install' and not args.zephyr_bin:
        parser.error('install needs the path to zephyr.bin')

    ub = UBoot(find_port(args.port), find_xsdb(args.xsdb))
    ub.reset()
    if args.action == 'install':
        install(ub, args.zephyr_bin)
    else:
        restore(ub)
    print('done: power-cycle or reset the board to boot from the SD card')


if __name__ == '__main__':
    main()
