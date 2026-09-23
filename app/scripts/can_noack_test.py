#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TC-12: the board keeps working when no node acknowledges its CAN frames.

With nothing else on the bus (the Kvaser interface down, FlatSat nodes off), a CAN
controller retransmits its frame forever. libcsp must not block on it: CSP sends
fail after a bounded time and everything else keeps running.

  sudo ip link set can0 down      # the only other node on the bench
  app/scripts/can_noack_test.py --elf build/noack-after/zephyr/zephyr.elf
  app/scripts/can_noack_test.py --elf path/to/fprime/zephyr.elf --fprime
  sudo ip link set can0 up type can bitrate 1000000

Without --fprime the image is apps/csp_node, which pings node 100 once a second
and prints a PING line per attempt: the lines must keep coming. With --fprime it
is the FlatSat image: its shell must keep answering, and `csp ping` must report
"no reply" instead of hanging.
"""

import argparse
import re
import subprocess
import sys
import time

from fprime_e2e import Console
from hw_test import XSDB_CFG, find_port, find_xsdb


def can_is_down(interface):
    try:
        with open(f'/sys/class/net/{interface}/operstate') as f:
            return f.read().strip() == 'down'
    except OSError:
        return True  # no interface: nothing on this host acknowledges


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--elf', required=True, help='image to load over JTAG')
    parser.add_argument('--fprime', action='store_true', help='the image is the FlatSat image')
    parser.add_argument('--seconds', type=int, default=20, help='how long to watch (csp_node)')
    parser.add_argument('--can', default='can0', help='host CAN interface that must be down')
    parser.add_argument('--log', help='transcript file')
    parser.add_argument('--port', help='UART device')
    args = parser.parse_args()

    if not can_is_down(args.can):
        sys.exit(f'{args.can} is up and acknowledges frames: sudo ip link set {args.can} down')

    console = Console(find_port(args.port))
    subprocess.run(['timeout', '120', find_xsdb(None), XSDB_CFG, args.elf], capture_output=True)
    checks = []

    def check(name, ok):
        checks.append(ok)
        print(f'{"PASS" if ok else "FAIL"}  {name}')

    if args.fprime:
        check('start window announced', console.wait_for('within 10 s', 40))
        console.command('bench start', 1)
        check('server ready', console.wait_for('CSP_BENCH_READY', 30))
        for attempt in range(3):
            out = console.command('csp ping 102 32 500', 3)
            check(f'csp ping {attempt + 1}: "no reply", not a hang', 'no reply' in out)
        out = console.command('param get 102 200 u32', 4)
        check('param get fails instead of hanging', 'failed' in out)
        check('shell still answers', 'node 6061/8' in console.command('bench info', 2))
        can = console.command('can show can@e0009000', 2)
        check('controller error-passive, not bus-off (nobody acknowledges)',
              'error-passive' in can)
    else:
        console.wait_for('pinging', 30)
        mark = len(console.text())
        time.sleep(args.seconds)
        pings = re.findall(r'PING \d+: [^\n]*', console.text()[mark:])
        for line in pings[-3:]:
            print('   ', line.strip())
        check(f'{len(pings)} ping attempts in {args.seconds} s (a blocked sender makes none)',
              len(pings) >= args.seconds // 4)
    console.stop.set()
    if args.log:
        with open(args.log, 'w') as f:
            f.write(console.text())
    print(f'{sum(checks)}/{len(checks)} checks passed')
    return 0 if all(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
