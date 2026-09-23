#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""End-to-end test of the F Prime bench server on the TE0715 against the Linux CspBench.

1. Optionally load an image over JTAG (--elf), or reset the board so it boots from
   the SD card (--sd-boot), and wait for the server's [CSP_BENCH_READY] marker.
2. Run `CspBench --role client --write-test` on the host against the board.
3. Start a Linux `CspBench --role server` (node 102) and exercise the board's serial
   shell: bench info, kernel thread list, csp ping (with and without CRC32),
   param get / set --confirm / read-back / restore, and can show.

Exit code 0 only if the client test passes and every shell check gives the expected
result. The full console transcript is written to --log.

  app/scripts/fprime_e2e.py --bench path/to/CspBench --elf path/to/zephyr.elf --log e2e.log
"""

import argparse
import re
import subprocess
import sys
import threading
import time

import serial

from hw_test import XSDB_CFG, find_port, find_xsdb

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


class Console:
    def __init__(self, port):
        self.serial = serial.Serial(port, 115200, timeout=0.05)
        self.serial.reset_input_buffer()
        self.buf = bytearray()
        self.stop = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while not self.stop.is_set():
            data = self.serial.read(4096)
            if data:
                self.buf.extend(data)

    def text(self):
        return ANSI.sub('', self.buf.decode(errors='replace'))

    def wait_for(self, marker, timeout):
        start = time.time()
        while marker not in self.text() and time.time() - start < timeout:
            time.sleep(0.1)
        return marker in self.text()

    def command(self, line, settle=2.5):
        """Send a shell command and return what the board printed in response."""
        mark = len(self.buf)
        self.serial.write(line.encode() + b'\r')
        time.sleep(settle)
        return ANSI.sub('', self.buf[mark:].decode(errors='replace'))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bench', required=True, help='Linux CspBench executable')
    boot = parser.add_mutually_exclusive_group(required=True)
    boot.add_argument('--elf', help='load this zephyr.elf over JTAG')
    boot.add_argument('--sd-boot', action='store_true', help='reset and boot from the SD card')
    parser.add_argument('--can', default='can0', help='host SocketCAN interface')
    parser.add_argument('--node', type=int, default=6061, help='board CSP node')
    parser.add_argument('--log', required=True, help='transcript file')
    parser.add_argument('--port', help='UART device')
    parser.add_argument('--xsdb', help='path to xsdb')
    args = parser.parse_args()

    xsdb = find_xsdb(args.xsdb)
    console = Console(find_port(args.port))
    started = time.time()
    if args.elf:
        subprocess.run(['timeout', '120', xsdb, XSDB_CFG, args.elf], capture_output=True)
    else:
        subprocess.run(['timeout', '60', xsdb, '-eval',
                        'connect; targets -set -nocase -filter {name =~ "APU*"}; rst -system; '
                        'disconnect'], capture_output=True)

    checks = []

    def check(name, ok):
        checks.append((name, ok))
        print(f'{"PASS" if ok else "FAIL"}  {name}')

    window = console.wait_for('within 10 s', 40)
    check('start window announced', window)
    if args.elf:
        console.command(f'bench start {args.node} 8', 1)
    ready = console.wait_for('CSP_BENCH_READY', 30)
    check(f'server ready on node {args.node} ({time.time() - started:.1f} s after reset)', ready)
    if not ready:
        open(args.log, 'w').write(console.text())
        return 1

    info = console.command('bench info')
    check('bench info', f'node {args.node}/8 (started)' in info)
    console.command('kernel thread list', 3)

    client = subprocess.run(['timeout', '60', args.bench, '--role', 'client', '--can', args.can,
                             '--node', '100', '--peer', str(args.node), '--write-test',
                             '--write-value', '0xA5A55A5A'], capture_output=True, text=True)
    result = [line for line in client.stdout.splitlines() if 'CSP_BENCH_RESULT' in line]
    check(f'Linux client against node {args.node}: {result[-1] if result else "no result"}',
          client.returncode == 0 and bool(result) and 'PASS' in result[-1])

    server = subprocess.Popen(['timeout', '60', args.bench, '--role', 'server', '--can', args.can,
                               '--node', '102'], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    time.sleep(3)
    check('csp ping 102 (CRC32)', 'reply in' in console.command('csp ping 102'))
    check('csp ping 102 --nocrc is dropped by the CRC-requiring peer',
          'no reply' in console.command('csp ping 102 32 1000 --nocrc'))
    check('param get 102 200 u32 = 0x12345678',
          '0x12345678' in console.command('param get 102 200 u32'))
    check('param set without --confirm is refused',
          'repeat the command with --confirm' in console.command('param set 102 200 u32 0xCAFEBABE'))
    check('param set --confirm writes and reads back 0xCAFEBABE',
          'written and read back: 3405691582 (0xcafebabe)'
          in console.command('param set 102 200 u32 0xCAFEBABE --confirm', 3))
    check('param get reads the new value',
          '0xcafebabe' in console.command('param get 102 200 u32'))
    check('param set --confirm restores 0x12345678',
          '(0x12345678)' in console.command('param set 102 200 u32 0x12345678 --confirm', 3))
    check('csp ping to an absent node times out',
          'no reply' in console.command('csp ping 4242 32 500'))
    can = console.command('can show can@e0009000')
    check('can show: no bus errors', 'rx errors:       0' in can and 'tx errors:       0' in can)
    server.terminate()
    server_out = server.communicate()[0]
    console.stop.set()

    with open(args.log, 'w') as f:
        f.write('=== TE0715 console\n' + console.text())
        f.write('\n=== Linux CspBench client\n' + client.stdout + client.stderr)
        f.write('\n=== Linux CspBench server (node 102)\n' + server_out)
    failed = [name for name, ok in checks if not ok]
    print(f'{len(checks) - len(failed)}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
