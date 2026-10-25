#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Load a Zephyr image into the TE0715's RAM through U-Boot on the serial console.

Reboots the running Zephyr image (`kernel reboot cold`), stops U-Boot's autoboot,
receives the image with `loadx` (XMODEM-1K) at the address boot.cmd uses (LOAD_ADDR),
checks it with U-Boot's crc32 against the local file, and starts it as boot.cmd
does (caches off, go LOAD_ADDR). Nothing is written to the SD card.

  uboot_load.py --port /dev/cu.usbserial-...1 --bin zephyr.bin --log load.log --until MARKER

For a host without AMD xsdb. Needs pyserial and xmodem (pip install pyserial xmodem).
With --wait-reset it waits for a reset by hand instead (an image without a shell).
"""

import argparse
import re
import sys
import time
import zlib

import serial
import xmodem

ANSI = re.compile(rb'\x1b\[[0-9;?]*[A-Za-z]')
# Base of zephyr,sram in te0715.dts, where every image is linked (TE-BSP-004)
LOAD_ADDR = 0x100000


class Port:
    def __init__(self, name, log):
        self.s = serial.Serial(name, 115200, timeout=0.05)
        self.s.reset_input_buffer()
        self.log = open(log, 'ab')
        self.buf = bytearray()

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            data = self.s.read(4096)
            if data:
                self.buf.extend(data)
                self.log.write(data)
                self.log.flush()

    def wait(self, pattern, timeout, since=0, poke=None):
        regex = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            if regex.search(ANSI.sub(b'', bytes(self.buf[since:]))):
                return True
            if poke is not None:
                self.s.write(poke)
            self.pump(0.1)
        return False

    def send(self, line):
        mark = len(self.buf)
        self.s.write(line.encode() + b'\r')
        return mark


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', required=True)
    parser.add_argument('--bin', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--until', help='wait for this text after starting the image')
    parser.add_argument('--wait-reset', type=int, metavar='SECONDS',
                        help='do not reboot the running image; wait this long for a reset by hand')
    args = parser.parse_args()
    image = open(args.bin, 'rb').read()
    crc = zlib.crc32(image) & 0xFFFFFFFF

    p = Port(args.port, args.log)
    p.s.write(b'\r')
    p.pump(0.3)
    if args.wait_reset:
        mark = len(p.buf)
        print(f'waiting up to {args.wait_reset} s for a reset', flush=True)
        timeout = args.wait_reset
    else:
        mark = p.send('kernel reboot cold')
        timeout = 30
    if not p.wait(rb'Hit any key to stop autoboot', timeout, mark):
        sys.exit('no U-Boot autoboot prompt')
    # Stop autoboot and wait for the prompt
    p.s.write(b' ')
    mark = len(p.buf)
    if not p.wait(rb'(Zynq|=)> ?$', 10, mark, poke=b'\r'):
        sys.exit('no U-Boot prompt')
    p.pump(0.5)

    mark = p.send(f'loadx {LOAD_ADDR:#x}')
    if not p.wait(rb'Ready for binary', 10, mark):
        sys.exit('loadx did not start')
    p.pump(0.2)
    p.s.reset_input_buffer()
    p.s.timeout = 1

    def getc(size, timeout=1):
        p.s.timeout = timeout
        data = p.s.read(size)
        return data or None

    def putc(data, timeout=1):
        return p.s.write(data)

    started = time.time()
    modem = xmodem.XMODEM(getc, putc, mode='xmodem1k')
    with open(args.bin, 'rb') as stream:
        ok = modem.send(stream, retry=16, timeout=10)
    seconds = time.time() - started
    p.s.timeout = 0.05
    p.log.write(f'\n[host] xmodem send {"ok" if ok else "FAILED"}: {len(image)} bytes in {seconds:.1f} s\n'.encode())
    if not ok:
        sys.exit('xmodem transfer failed')
    p.wait(rb'Total Size', 5, 0)
    p.pump(0.5)

    mark = p.send(f'crc32 {LOAD_ADDR:#x} 0x{len(image):x}')
    if not p.wait(rb'==> [0-9a-f]{8}', 10, mark):
        sys.exit('no crc32 result')
    p.pump(0.3)
    found = re.search(rb'==> ([0-9a-f]{8})', ANSI.sub(b'', bytes(p.buf[mark:])))
    board_crc = int(found.group(1), 16)
    p.log.write(f'\n[host] crc32 local 0x{crc:08x}, board 0x{board_crc:08x}\n'.encode())
    print(f'loaded {len(image)} bytes in {seconds:.1f} s; crc32 local 0x{crc:08x} board 0x{board_crc:08x}')
    if board_crc != crc:
        sys.exit('crc32 mismatch: not starting the image')

    for command in ('icache off', 'dcache off'):
        mark = p.send(command)
        p.wait(rb'(Zynq|=)> ?$', 5, mark)
    mark = p.send(f'go {LOAD_ADDR:#x}')
    if args.until and not p.wait(re.escape(args.until.encode()), 40, mark):
        sys.exit(f'{args.until} not seen after go')
    p.pump(0.5)
    p.log.close()
    p.s.close()
    print('started')


if __name__ == '__main__':
    main()
