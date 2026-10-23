#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check Zephyr's Ethernet on the TE0715 against a directly connected host (TC-24).

Run with apps/eth_bringup running on the board (its serial shell free) and the TC-23
cabling and host port. The script:

1. checks the host side, as uboot_eth_check.py does;
2. reads the board's interface (`net iface`): carrier and its IPv4 address;
3. pings the board from the host with the don't-fragment flag at each payload size
   (default: either side of one and two 512-byte driver buffers, and the largest
   frame), 100 times each;
4. pings the host from the board's shell (`net ping`), with a small and the largest
   payload;
5. compares the host port's counters before and after, keeps the board's `net stats`,
   and writes an evidence package: console.log, host-ping.txt, summary.txt, SHA256SUMS.

  app/scripts/zephyr_eth_check.py --host-if enxa0cec8ebc610

Needs pyserial and iputils ping. See docs/tests/ethernet.md.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

import uboot_eth_check
from hw_test import find_port
from sensor_bench import Console
from uboot_eth_check import Criterion, host_address_problems, host_addresses, read_host, write_package

FRAME_OVERHEAD = 8 + 20 + 14  # ICMP, IPv4 and Ethernet headers (the FCS is not counted)
MAX_PAYLOAD = 1500 - 20 - 8   # the largest unfragmented ICMP payload at the 1500-byte MTU
HOST_PING_INTERVAL_S = 0.1
BOARD_PING_INTERVAL_MS = 200


@dataclass
class Settings:
    host_if: str
    host_ip: str = '192.168.70.1'
    board_ip: str = '192.168.70.2'
    prefix: int = 24
    sizes: tuple = (56, 469, 470, 471, 981, 982, 983, 1472)
    count: int = 100
    board_sizes: tuple = (4, 1472)
    board_count: int = 10
    expect_speed: int = 100


@dataclass
class IfaceState:
    carrier: bool
    address: bool


@dataclass
class CheckResult:
    iface: IfaceState
    iface_text: str
    host: dict = field(default_factory=dict)     # payload size -> (sent, received) or None
    host_output: str = ''
    board: dict = field(default_factory=dict)    # payload size -> replies
    stats: str = ''


def settings_problems(s):
    addresses = uboot_eth_check.Settings(host_if=s.host_if, host_ip=s.host_ip,
                                         board_ip=s.board_ip, prefix=s.prefix)
    problems = uboot_eth_check.settings_problems(addresses)
    for name, sizes in (('host', s.sizes), ('board', s.board_sizes)):
        if not sizes:
            problems.append(f'no {name} ping sizes')
        bad = [n for n in sizes if not 0 <= n <= MAX_PAYLOAD]
        if bad:
            problems.append(f'{name} ping sizes {bad}: use 0 to {MAX_PAYLOAD} (one unfragmented frame)')
    for name, count in (('host', s.count), ('board', s.board_count)):
        if not 1 <= count <= 1000:
            problems.append(f'{name} ping count {count}: use 1 to 1000')
    return problems


def host_ping_argv(s, size):
    return ['ping', '-n', '-c', str(s.count), '-i', str(HOST_PING_INTERVAL_S), '-W', '1',
            '-s', str(size), '-M', 'do', '-I', s.host_if, s.board_ip]


def host_ping(argv):
    count = int(argv[argv.index('-c') + 1])
    result = subprocess.run(argv, capture_output=True, text=True,
                            timeout=count * HOST_PING_INTERVAL_S + 30)
    return result.stdout + result.stderr


def parse_host_ping(text):
    found = re.search(r'(\d+) packets transmitted, (\d+) received', text)
    return (int(found.group(1)), int(found.group(2))) if found else None


def board_ping_replies(text, host_ip):
    pattern = rf'bytes from {re.escape(host_ip)} to \S+: icmp_seq=(\d+)'
    return len(set(re.findall(pattern, text)))


def parse_iface(text, board_ip):
    return IfaceState(carrier=re.search(r'carrier=ON\b', text) is not None,
                      address=re.search(rf'^\s+{re.escape(board_ip)}/', text, re.M) is not None)


def run_check(shell, ping, s):
    _, iface_text = shell.run('net iface', r'carrier=\w+', 10)
    result = CheckResult(iface=parse_iface(iface_text, s.board_ip), iface_text=iface_text)
    outputs = []
    for size in s.sizes:
        argv = host_ping_argv(s, size)
        out = ping(argv)
        outputs.append(f'$ {" ".join(argv)}\n{out}')
        result.host[size] = parse_host_ping(out)
    result.host_output = '\n'.join(outputs)
    for size in s.board_sizes:
        cmd = f'net ping -c {s.board_count} -i {BOARD_PING_INTERVAL_MS} -s {size} {s.host_ip}'
        _, out = shell.run(cmd, rf'icmp_seq={s.board_count}\b.*|Ping timeout',
                           s.board_count * BOARD_PING_INTERVAL_MS / 1000 + 10)
        result.board[size] = board_ping_replies(out, s.host_ip)
    _, result.stats = shell.run('net stats', r'uart:~\$', 10)
    return result


def evaluate(s, result, before, after):
    criteria = [Criterion('board interface up with its address',
                          result.iface.carrier and result.iface.address,
                          f'carrier {"on" if result.iface.carrier else "off"}, {s.board_ip} '
                          f'{"assigned" if result.iface.address else "missing"}')]
    link_ok = after.carrier and after.speed == s.expect_speed and after.duplex == 'full'
    criteria.append(Criterion('host link at the baseline', link_ok,
                              f'carrier {"up" if after.carrier else "down"}, {after.speed} Mbit/s '
                              f'{after.duplex} duplex (expected {s.expect_speed} full)'))
    for size in s.sizes:
        got = result.host.get(size)
        ok = got is not None and got == (s.count, s.count)
        detail = 'no ping summary' if got is None else f'{got[1]} of {got[0]}'
        criteria.append(Criterion(f'host to board, {size} bytes (frame {size + FRAME_OVERHEAD})', ok, detail))
    for size in s.board_sizes:
        replies = result.board.get(size, 0)
        criteria.append(Criterion(f'board to host, {size} bytes', replies == s.board_count,
                                  f'{replies} of {s.board_count}'))
    missing = [n for n in uboot_eth_check.COUNTERS if n not in before.counters or n not in after.counters]
    if missing:
        criteria.append(Criterion('host counters readable', False, f'missing: {", ".join(missing)}'))
    else:
        increased = {n: after.counters[n] - before.counters[n] for n in uboot_eth_check.ERROR_COUNTERS
                     if after.counters[n] != before.counters[n]}
        criteria.append(Criterion('no host receive errors', not increased,
                                  ', '.join(f'{n} +{d}' for n, d in increased.items()) or 'none'))
    return criteria


def summary_text(s, result, before, after, criteria):
    lines = ['TC-24 Zephyr Ethernet bring-up (TE-ETH-002)',
             f'date: {time.strftime("%Y-%m-%dT%H:%M:%S%z")}',
             f'host port: {s.host_if} {s.host_ip}/{s.prefix}; board {s.board_ip}; '
             f'{s.count} host pings per size, {s.board_count} board pings per size',
             '--- board: net iface', result.iface_text.strip(),
             '--- board: net stats', result.stats.strip(), '---']
    for name, state in (('before', before), ('after', after)):
        counters = ' '.join(f'{k}={v}' for k, v in state.counters.items())
        lines.append(f'host {name}: carrier {int(state.carrier)} speed {state.speed} '
                     f'duplex {state.duplex} {counters}')
    lines += [f'{"PASS" if c.passed else "FAIL"}  {c.name}: {c.detail}' for c in criteria]
    lines.append('PASS' if all(c.passed for c in criteria) else 'FAIL')
    return '\n'.join(lines) + '\n'


def open_shell(port, log_path):
    """sensor_bench.py's serial console: every byte logged, commands wait for a pattern."""
    return Console(port, log_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    defaults = Settings(host_if='')
    parser.add_argument('--host-if', required=True, help='host Ethernet port cabled to the TE0701')
    parser.add_argument('--host-ip', default=defaults.host_ip)
    parser.add_argument('--board-ip', default=defaults.board_ip)
    parser.add_argument('--prefix', type=int, default=defaults.prefix)
    parser.add_argument('--port', help='UART device (default: Digilent cable interface 1)')
    parser.add_argument('--out', help='evidence directory (default: zephyr-eth-check-<date-time>)')
    args = parser.parse_args()
    s = Settings(host_if=args.host_if, host_ip=args.host_ip, board_ip=args.board_ip, prefix=args.prefix)

    problems = settings_problems(s)
    if not problems:
        problems = host_address_problems(host_addresses(), s)
    if problems:
        sys.exit('not started:\n  ' + '\n  '.join(problems))

    port = find_port(args.port)
    out = args.out or time.strftime('zephyr-eth-check-%Y%m%d-%H%M%S')
    os.makedirs(out, exist_ok=False)
    before = read_host(s.host_if)
    try:
        shell = open_shell(port, os.path.join(out, 'console.log'))
        try:
            result = run_check(shell, host_ping, s)
        finally:
            shell.close()  # flushes console.log
    except BaseException as stop:  # a lost port, Ctrl-C: keep the evidence
        reason = stop.code if isinstance(stop, SystemExit) else repr(stop)
        write_package(out, f'TC-24 Zephyr Ethernet bring-up (TE-ETH-002)\naborted: {reason}\nFAIL\n')
        raise
    after = read_host(s.host_if)

    with open(os.path.join(out, 'host-ping.txt'), 'w') as f:
        f.write(result.host_output)
    criteria = evaluate(s, result, before, after)
    summary = summary_text(s, result, before, after, criteria)
    write_package(out, summary)
    print(summary, end='')
    print(f'evidence: {out}/')
    sys.exit(0 if all(c.passed for c in criteria) else 1)


if __name__ == '__main__':
    main()
