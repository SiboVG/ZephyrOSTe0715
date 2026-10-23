#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the TE0715's Ethernet path from U-Boot, before any Zephyr networking (TC-23).

U-Boot's Zynq GEM driver is known to work, so a pass shows that the wiring, the PHY
and the processor's Ethernet set-up are sound, and a later Zephyr problem is a
software problem. The script:

1. checks the host side: the test port carries the host address, and no other host
   interface is in the test subnet;
2. resets the board over JTAG, reboots it from the image's shell (--reboot) or waits
   for a reset by hand (--wait-reset), and stops U-Boot;
3. sets the board's address in U-Boot's environment (in RAM only; never saveenv),
   and a locally administered MAC address if U-Boot has none;
4. lists the PHYs on the MDIO bus (`mii info`), pings the host from U-Boot, and
   reads the PHY's negotiated speed and duplex;
5. compares the host port's counters before and after, and writes an evidence
   package: console.log, summary.txt, SHA256SUMS.

  app/scripts/uboot_eth_check.py --host-if enx00e04c680001 --expect-speed 1000

The board is left at the U-Boot prompt: reset or power-cycle it afterwards. Nothing
is written to the SD card. Needs pyserial; the JTAG reset needs AMD xsdb. Without it,
--reboot uses the running image's shell (`kernel reboot cold`), and --wait-reset waits
for the reset button or power-on. See docs/tests/ethernet.md.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

from hw_test import find_port, find_xsdb
from sd_install import UBoot

# Marvell 88E151x as U-Boot's `mii info` prints it: OUI = ID >> 10, model = (ID >> 4) & 0x3F
# for PHY ID 0x01410DD0 | revision (88E1510/1512/1514/1518 data sheet, registers 2 and 3)
MARVELL_OUI = 0x5043
MODEL_88E151X = 0x1D

PAGE_REGISTER = 0x16    # Page Address, all pages
COPPER_STATUS_1 = 0x11  # Copper Specific Status Register 1, page 0
STATUS_LINK = 1 << 10
STATUS_RESOLVED = 1 << 11
STATUS_FULL_DUPLEX = 1 << 13
STATUS_SPEED_SHIFT = 14
SPEEDS = {0: 10, 1: 100, 2: 1000}  # code 3 is reserved

# Host receive counters that must not increase during a run
ERROR_COUNTERS = ('rx_errors', 'rx_crc_errors', 'rx_frame_errors')
COUNTERS = ('rx_packets', 'tx_packets') + ERROR_COUNTERS

SYSFS_NET = '/sys/class/net'
PING_TIMEOUT_S = 30  # covers autonegotiation and ARP retries on the first ping


@dataclass
class Settings:
    host_if: str
    host_ip: str = '192.168.70.1'
    board_ip: str = '192.168.70.2'
    prefix: int = 24
    mac: str = '02:00:00:07:15:01'
    count: int = 10
    expect_speed: int | None = None


@dataclass
class Phy:
    addr: int
    oui: int
    model: int
    rev: int

    @property
    def is_88e151x(self):
        return self.oui == MARVELL_OUI and self.model == MODEL_88E151X


@dataclass
class CopperStatus:
    link: bool
    resolved: bool
    speed: int | None  # Mbit/s; None until resolved, or for the reserved code
    full_duplex: bool


@dataclass
class BoardResult:
    ethaddr: str
    ethaddr_source: str
    phys: list
    status: CopperStatus | None
    status_note: str
    pings: list


@dataclass
class HostState:
    carrier: bool
    speed: int | None
    duplex: str | None
    counters: dict = field(default_factory=dict)


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str


# --- Settings and host preflight -----------------------------------------------------

def _address(text):
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        return None


def settings_problems(s):
    """Reasons the settings cannot give a valid test; empty if they can."""
    problems = []
    if not 8 <= s.prefix <= 30:
        problems.append(f'prefix /{s.prefix}: use /8 to /30')
        return problems
    host, board = _address(s.host_ip), _address(s.board_ip)
    if host is None or board is None:
        return problems + [f'not an IPv4 address: {s.host_ip if host is None else s.board_ip}']
    net = ipaddress.IPv4Network(f'{host}/{s.prefix}', strict=False)
    for name, addr in (('host', host), ('board', board)):
        if addr not in net:
            problems.append(f'{name} address {addr} is not in {net}')
        elif addr in (net.network_address, net.broadcast_address):
            problems.append(f'{name} address {addr} is the network or broadcast address of {net}')
    if host == board:
        problems.append('host and board addresses are the same')
    if not re.fullmatch(r'[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}', s.mac):
        problems.append(f'MAC address {s.mac} is not six hex bytes')
    elif int(s.mac[:2], 16) & 0x03 != 0x02:
        problems.append(f'MAC address {s.mac} must be locally administered unicast (first byte x2, x6, xA or xE)')
    if not 1 <= s.count <= 100:
        problems.append(f'ping count {s.count}: use 1 to 100')
    if s.expect_speed not in (None, 10, 100, 1000):
        problems.append(f'expected speed {s.expect_speed}: use 10, 100 or 1000')
    return problems


def host_address_problems(ip_json, s):
    """Problems with the host's addresses, from `ip -j -4 addr show` (parsed)."""
    net = ipaddress.IPv4Network(f'{s.host_ip}/{s.prefix}', strict=False)
    board = ipaddress.IPv4Address(s.board_ip)
    names = [i.get('ifname') for i in ip_json]
    if s.host_if not in names:
        return [f'host interface {s.host_if} not found (have: {", ".join(names)})']
    problems = []
    host_prefixes = []
    for iface in ip_json:
        for info in iface.get('addr_info', []):  # IPv4 only (ip -4)
            addr = ipaddress.IPv4Address(info['local'])
            iface_net = ipaddress.IPv4Network(f'{addr}/{info["prefixlen"]}', strict=False)
            if addr == board:
                problems.append(f'the board address {board} is in use on the host ({iface["ifname"]})')
            if iface['ifname'] == s.host_if and str(addr) == s.host_ip:
                host_prefixes.append(info['prefixlen'])
            elif iface['ifname'] != s.host_if and iface_net.overlaps(net):
                problems.append(f'{iface["ifname"]} ({addr}/{info["prefixlen"]}) overlaps the test '
                                f'subnet {net}: replies could leave through it')
    if s.prefix not in host_prefixes:
        found = ', '.join(f'/{p}' for p in host_prefixes) or 'not assigned'
        problems.append(f'{s.host_if} does not have {s.host_ip}/{s.prefix} ({found})')
    return problems


def read_host(ifname, sysfs=SYSFS_NET):
    """Link state and counters of a host port from sysfs."""
    def read(rel):
        try:
            with open(os.path.join(sysfs, ifname, rel)) as f:
                return f.read().strip()
        except OSError:  # e.g. EINVAL for speed while the link is down
            return None

    speed = read('speed')
    speed = int(speed) if speed and speed.lstrip('-').isdigit() and int(speed) > 0 else None
    duplex = read('duplex')
    counters = {}
    for name in COUNTERS:
        value = read(f'statistics/{name}')
        if value is not None and value.isdigit():
            counters[name] = int(value)
    return HostState(carrier=read('carrier') == '1', speed=speed,
                     duplex=duplex if duplex in ('full', 'half') else None, counters=counters)


def host_addresses():
    result = subprocess.run(['ip', '-j', '-4', 'addr', 'show'], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


# --- U-Boot output --------------------------------------------------------------------

MII_INFO = re.compile(r'PHY 0x([0-9A-Fa-f]{2}): OUI = 0x([0-9A-Fa-f]+), Model = 0x([0-9A-Fa-f]+), '
                      r'Rev = 0x([0-9A-Fa-f]+)')


def parse_mii_info(text):
    return [Phy(*(int(g, 16) for g in m.groups())) for m in MII_INFO.finditer(text)]


def parse_mii_read(text):
    """The register value `mii read` prints on a line of its own, or None."""
    values = re.findall(r'^\s*([0-9A-Fa-f]{4})\s*$', text, re.M)
    return int(values[-1], 16) if values else None


def decode_copper_status(word):
    resolved = bool(word & STATUS_RESOLVED)
    speed = SPEEDS.get((word >> STATUS_SPEED_SHIFT) & 0x3) if resolved else None
    return CopperStatus(link=bool(word & STATUS_LINK), resolved=resolved, speed=speed,
                        full_duplex=bool(word & STATUS_FULL_DUPLEX))


def board_check(ub, s):
    """Run the check at the U-Boot prompt. Only reads and RAM-only environment changes."""
    found = re.search(r'^ethaddr=(\S+)', ub.run('printenv ethaddr'), re.M)
    if found:
        ethaddr, source = found.group(1), 'environment'
    else:
        ub.run(f'setenv ethaddr {s.mac}')
        ethaddr, source = s.mac, 'set for this check'
    net = ipaddress.IPv4Network(f'{s.host_ip}/{s.prefix}', strict=False)
    ub.run(f'setenv ipaddr {s.board_ip}')
    ub.run(f'setenv netmask {net.netmask}')
    ub.run(f'setenv serverip {s.host_ip}')

    phys = parse_mii_info(ub.run('mii info'))
    pings = [f'host {s.host_ip} is alive' in ub.run(f'ping {s.host_ip}', timeout=PING_TIMEOUT_S)
             for _ in range(s.count)]

    # The link comes up with the first ping, so the PHY is read afterwards
    status, note = None, ''
    phy = next((p for p in phys if p.is_88e151x), None)
    if phy is None:
        note = ('no PHY listed by mii info' if not phys else
                f'PHY at 0x{phys[0].addr:02x} is not a Marvell 88E151x; its status is not decoded')
    else:
        page = parse_mii_read(ub.run(f'mii read 0x{phy.addr:x} 0x{PAGE_REGISTER:x}'))
        if page is None:
            note = 'page register not readable'
        elif page & 0xFF != 0:
            note = f'PHY on register page {page & 0xFF}, not 0; status not decoded'
        else:
            word = parse_mii_read(ub.run(f'mii read 0x{phy.addr:x} 0x{COPPER_STATUS_1:x}'))
            if word is None:
                note = 'copper status register not readable'
            else:
                status = decode_copper_status(word)
    return BoardResult(ethaddr=ethaddr, ethaddr_source=source, phys=phys, status=status,
                       status_note=note, pings=pings)


# --- Pass criteria (TC-23) -----------------------------------------------------------

def evaluate(s, board, before, after):
    criteria = []
    answered = sum(board.pings)
    criteria.append(Criterion('pings answered', answered == s.count and len(board.pings) == s.count,
                              f'{answered} of {s.count}'))
    criteria.append(Criterion('host carrier after the pings', after.carrier,
                              'up' if after.carrier else 'down'))

    missing = [n for n in COUNTERS if n not in before.counters or n not in after.counters]
    if missing:
        criteria.append(Criterion('host counters readable', False, f'missing: {", ".join(missing)}'))
    else:
        received = after.counters['rx_packets'] - before.counters['rx_packets']
        criteria.append(Criterion('host received the traffic', received >= s.count,
                                  f'{received} packets received on {s.host_if}'))
        increased = {n: after.counters[n] - before.counters[n] for n in ERROR_COUNTERS
                     if after.counters[n] != before.counters[n]}
        criteria.append(Criterion('no host receive errors', not increased,
                                  ', '.join(f'{n} +{d}' for n, d in increased.items()) or 'none'))

    host_ok = after.duplex == 'full' and after.speed is not None and \
        (s.expect_speed is None or after.speed == s.expect_speed)
    detail = f'host {after.speed} Mbit/s {after.duplex} duplex'
    if s.expect_speed is not None:
        detail += f' (expected {s.expect_speed} full)'
    board_ok = True
    if board.status is not None:
        board_ok = board.status.link and board.status.full_duplex and board.status.speed == after.speed
        detail += (f'; PHY {board.status.speed} Mbit/s '
                   f'{"full" if board.status.full_duplex else "half"} duplex, '
                   f'link {"up" if board.status.link else "down"}')
    else:
        detail += f'; PHY not read ({board.status_note})'
    criteria.append(Criterion('full duplex at the expected speed', host_ok and board_ok, detail))
    return criteria


def summary_text(s, board, before, after, criteria, banner):
    lines = ['TC-23 Ethernet link from U-Boot (TE-ETH-001)',
             f'date: {time.strftime("%Y-%m-%dT%H:%M:%S%z")}',
             f'host port: {s.host_if} {s.host_ip}/{s.prefix}; board {s.board_ip}; '
             f'{s.count} pings; expected speed: {s.expect_speed or "any"}',
             f'board MAC: {board.ethaddr} ({board.ethaddr_source})']
    lines += [f'U-Boot: {line}' for line in banner]
    if board.phys:
        lines += [f'PHY 0x{p.addr:02x}: OUI 0x{p.oui:04x} model 0x{p.model:02x} rev {p.rev}'
                  f'{" (Marvell 88E151x)" if p.is_88e151x else ""}' for p in board.phys]
    else:
        lines.append('PHY: none listed by mii info')
    lines.append('pings: ' + ''.join('.' if ok else 'x' for ok in board.pings))
    for name, state in (('before', before), ('after', after)):
        counters = ' '.join(f'{k}={v}' for k, v in state.counters.items())
        lines.append(f'host {name}: carrier {int(state.carrier)} speed {state.speed} '
                     f'duplex {state.duplex} {counters}')
    lines += [f'{"PASS" if c.passed else "FAIL"}  {c.name}: {c.detail}' for c in criteria]
    lines.append('PASS' if all(c.passed for c in criteria) else 'FAIL')
    return '\n'.join(lines) + '\n'


def write_package(out_dir, summary):
    with open(os.path.join(out_dir, 'summary.txt'), 'w') as f:
        f.write(summary)
    names = sorted(n for n in os.listdir(out_dir) if n != 'SHA256SUMS')
    with open(os.path.join(out_dir, 'SHA256SUMS'), 'w') as sums:
        for name in names:
            with open(os.path.join(out_dir, name), 'rb') as f:
                sums.write(f'{hashlib.sha256(f.read()).hexdigest()}  {name}\n')


# --- Hardware -------------------------------------------------------------------------

class LoggedUBoot(UBoot):
    """sd_install.py's U-Boot console, logging everything it reads."""

    def __init__(self, port, xsdb, log):
        super().__init__(port, xsdb)
        self.log = log

    def _read_until(self, marker, timeout):
        text = super()._read_until(marker, timeout)
        self.log.write(text)
        self.log.flush()
        return text


def open_uboot(args, log):
    xsdb = None if args.wait_reset or args.reboot else find_xsdb(args.xsdb)
    ub = LoggedUBoot(find_port(args.port), xsdb, log)
    if args.reboot:
        ub.serial.reset_input_buffer()
        ub.serial.write(b'\rkernel reboot cold\r')
        ub.stop_autoboot(30)
    elif args.wait_reset:
        print(f'reset or power on the board within {args.wait_reset} s', flush=True)
        ub.serial.reset_input_buffer()
        ub.stop_autoboot(args.wait_reset)
    else:
        ub.reset()
    return ub


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    defaults = Settings(host_if='')
    parser.add_argument('--host-if', required=True, help='host Ethernet port cabled to the TE0701')
    parser.add_argument('--host-ip', default=defaults.host_ip)
    parser.add_argument('--board-ip', default=defaults.board_ip)
    parser.add_argument('--prefix', type=int, default=defaults.prefix)
    parser.add_argument('--mac', default=defaults.mac,
                        help='MAC address for the board if U-Boot has none (locally administered)')
    parser.add_argument('--count', type=int, default=defaults.count, help='pings from U-Boot')
    parser.add_argument('--expect-speed', type=int, choices=(10, 100, 1000),
                        help='required link speed in Mbit/s')
    reset = parser.add_mutually_exclusive_group()
    reset.add_argument('--reboot', action='store_true',
                       help='no JTAG reset: reboot the running image from its shell (kernel reboot cold)')
    reset.add_argument('--wait-reset', type=int, metavar='SECONDS',
                       help='no JTAG reset: wait this long for a reset or power-on by hand')
    parser.add_argument('--port', help='UART device (default: Digilent cable interface 1)')
    parser.add_argument('--xsdb', help='path to xsdb (default: PATH, then /tools/Xilinx)')
    parser.add_argument('--out', help='evidence directory (default: eth-check-<date-time>)')
    args = parser.parse_args()
    s = Settings(host_if=args.host_if, host_ip=args.host_ip, board_ip=args.board_ip, prefix=args.prefix,
                 mac=args.mac, count=args.count, expect_speed=args.expect_speed)

    problems = settings_problems(s)
    if not problems:
        problems = host_address_problems(host_addresses(), s)
    if problems:
        sys.exit('not started:\n  ' + '\n  '.join(problems))

    out = args.out or time.strftime('eth-check-%Y%m%d-%H%M%S')
    os.makedirs(out, exist_ok=False)
    before = read_host(s.host_if)
    try:
        with open(os.path.join(out, 'console.log'), 'w') as log:
            ub = open_uboot(args, log)
            board = board_check(ub, s)
            log.write('\n')
    except BaseException as stop:  # no U-Boot prompt, a lost port, Ctrl-C: keep the evidence
        reason = stop.code if isinstance(stop, SystemExit) else repr(stop)
        write_package(out, f'TC-23 Ethernet link from U-Boot (TE-ETH-001)\naborted: {reason}\nFAIL\n')
        raise
    after = read_host(s.host_if)

    with open(os.path.join(out, 'console.log')) as f:
        banner = [line.strip() for line in f if re.match(r'\s*(U-Boot 20|Net:|ZYNQ GEM|zynq_gem|eth\d)', line)]
    criteria = evaluate(s, board, before, after)
    summary = summary_text(s, board, before, after, criteria, banner)
    write_package(out, summary)
    print(summary, end='')
    print(f'evidence: {out}/; the board is at the U-Boot prompt: reset or power-cycle it')
    sys.exit(0 if all(c.passed for c in criteria) else 1)


if __name__ == '__main__':
    main()
