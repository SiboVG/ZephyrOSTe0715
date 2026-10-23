# SPDX-License-Identifier: Apache-2.0
"""uboot_eth_check.py (TC-23, TE-ETH-001) against a fake U-Boot and a fake host.

Expected values come from U-Boot's documented output and the Marvell 88E151x data
sheet, not from the script: the PHY identifier registers 2 and 3 read 0x0141 and
0x0DD0 | revision; U-Boot's `mii info` prints OUI = ID >> 10 = 0x5043 and
model = (ID >> 4) & 0x3F = 0x1D. Copper Specific Status Register 1 (page 0,
register 17): bits 15:14 speed (00 10, 01 100, 10 1000 Mbit/s, 11 reserved),
bit 13 full duplex, bit 11 speed and duplex resolved, bit 10 link (real time).
"""

import hashlib
import io
import re
import shutil
import sys

import pytest

import uboot_eth_check as eth
from uboot_eth_check import Settings

HOST_IF = 'enx00e04c680001'

MII_88E1512_AT_0 = 'PHY 0x00: OUI = 0x5043, Model = 0x1D, Rev = 0x01, 1000baseT, FDX\n'
STATUS_1000_FD = 0xAC00  # 10 1 0 1 1 00...: 1000 Mbit/s, full duplex, resolved, link
STATUS_100_FD = 0x6C00   # 01 1 0 1 1: 100 Mbit/s, full duplex, resolved, link
STATUS_1000_HD = 0x8C00  # 10 0 0 1 1: 1000 Mbit/s, half duplex, resolved, link


class FakeUBoot:
    """Answers U-Boot commands as U-Boot 2022.01 prints them; records every command."""

    def __init__(self, ethaddr=None, mii=MII_88E1512_AT_0, registers=None, alive=None):
        self.ethaddr = ethaddr
        self.mii = mii
        self.registers = {(0, 0x16): 0x0000, (0, 0x11): STATUS_1000_FD} \
            if registers is None else registers
        self.alive = alive  # per ping: True/False; None: all answered
        self.commands = []
        self.pings = 0

    def run(self, cmd, timeout=30):
        self.commands.append(cmd)
        words = cmd.split()
        if cmd == 'printenv ethaddr':
            if self.ethaddr is None:
                return f'{cmd}\n## Error: "ethaddr" not defined\nZynq> '
            return f'{cmd}\nethaddr={self.ethaddr}\nZynq> '
        if words[:2] == ['mii', 'info']:
            return f'{cmd}\n{self.mii}Zynq> '
        if words[:2] == ['mii', 'read']:
            if self.mii.startswith('Unknown command'):
                return f'{cmd}\n{self.mii}Zynq> '
            key = (int(words[2], 0), int(words[3], 0))
            if key not in self.registers:
                return f'{cmd}\nError reading from the PHY addr=0x{key[0]:02x} reg=0x{key[1]:02x}\nZynq> '
            return f'{cmd}\n{self.registers[key]:04X}\nZynq> '
        if words[0] == 'ping':
            answered = True if self.alive is None else self.alive[self.pings]
            self.pings += 1
            result = (f'host {words[1]} is alive' if answered else
                      f'ARP Retry count exceeded; starting again\nping failed; host {words[1]} is not alive')
            return f'{cmd}\nUsing ethernet@e000b000 device\n{result}\nZynq> '
        return f'{cmd}\nZynq> '


def ip_json(*interfaces):
    """`ip -j -4 addr show` output, as parsed JSON: (name, [(address, prefix), ...])."""
    return [{'ifname': name, 'operstate': 'UP',
             'addr_info': [{'family': 'inet', 'local': a, 'prefixlen': p} for a, p in addrs]}
            for name, addrs in interfaces]


LAB_HOST = ip_json(('lo', [('127.0.0.1', 8)]), ('enp1s0', [('10.33.179.55', 24)]),
                   (HOST_IF, [('192.168.70.1', 24)]))


def host_state(carrier: bool = True, speed: int | None = 1000, duplex: str | None = 'full',
               rx_packets: int = 100, errors: dict | None = None):
    counters = {'rx_packets': rx_packets, 'tx_packets': 50, 'rx_errors': 0,
                'rx_crc_errors': 0, 'rx_frame_errors': 0}
    counters.update(errors or {})
    return eth.HostState(carrier=carrier, speed=speed, duplex=duplex, counters=counters)


def failed(criteria):
    return [c.name for c in criteria if not c.passed]


# --- Settings: refused before anything touches the board or the network ---------

def test_default_settings_are_valid():
    assert eth.settings_problems(Settings(host_if=HOST_IF)) == []


@pytest.mark.parametrize('change', [
    dict(board_ip='192.168.70.1'),                 # the host's own address
    dict(board_ip='192.168.71.2'),                 # another subnet
    dict(board_ip='192.168.70.0'),                 # network address of /24
    dict(board_ip='192.168.70.255'),               # broadcast address of /24
    dict(host_ip='192.168.70.255'),
    dict(board_ip='192.168.70.300'),               # not an address
    dict(prefix=31), dict(prefix=7),               # no room for two hosts / not a lab subnet
    dict(mac='00:0a:35:00:1e:53'),                 # globally administered (Xilinx OUI)
    dict(mac='03:00:00:07:15:01'),                 # multicast bit set
    dict(mac='02:00:00:07:15'),                    # malformed
    dict(count=0), dict(count=101),
    dict(expect_speed=2500),
])
def test_unusable_settings_are_refused(change):
    assert eth.settings_problems(Settings(host_if=HOST_IF, **change)) != []


def test_boundary_settings_are_accepted():
    assert eth.settings_problems(Settings(host_if=HOST_IF, host_ip='10.200.0.1', board_ip='10.200.0.2',
                                          prefix=30, count=1)) == []
    assert eth.settings_problems(Settings(host_if=HOST_IF, count=100, prefix=8,
                                          host_ip='10.0.0.1', board_ip='10.255.255.254')) == []


# --- Host preflight: the test runs on the intended, isolated port -----------------

def test_host_with_the_address_on_the_test_port_passes():
    assert eth.host_address_problems(LAB_HOST, Settings(host_if=HOST_IF)) == []


def test_missing_test_port_is_reported():
    host = ip_json(('enp1s0', [('10.33.179.55', 24)]))
    assert eth.host_address_problems(host, Settings(host_if=HOST_IF)) != []


def test_test_port_without_the_host_address_is_reported():
    host = ip_json(('enp1s0', [('10.33.179.55', 24)]), (HOST_IF, []))
    assert eth.host_address_problems(host, Settings(host_if=HOST_IF)) != []


def test_test_subnet_on_another_interface_is_reported():
    # Replies to the board could leave through the lab LAN instead of the test port
    host = ip_json(('enp1s0', [('192.168.70.10', 24)]), (HOST_IF, [('192.168.70.1', 24)]))
    assert eth.host_address_problems(host, Settings(host_if=HOST_IF)) != []


def test_board_address_in_use_on_the_host_is_reported():
    host = ip_json((HOST_IF, [('192.168.70.1', 24), ('192.168.70.2', 24)]))
    assert eth.host_address_problems(host, Settings(host_if=HOST_IF)) != []


def test_host_address_with_another_prefix_is_reported():
    host = ip_json((HOST_IF, [('192.168.70.1', 16)]))
    assert eth.host_address_problems(host, Settings(host_if=HOST_IF)) != []


# --- U-Boot output parsing (U-Boot's formats, the 88E151x register map) -----------

def test_mii_info_identifies_the_88e151x():
    (phy,) = eth.parse_mii_info(MII_88E1512_AT_0)
    assert (phy.addr, phy.oui, phy.model, phy.rev) == (0, 0x5043, 0x1D, 1)
    assert phy.is_88e151x


def test_mii_info_lists_every_phy_and_tells_other_models_apart():
    text = ('PHY 0x01: OUI = 0x5043, Model = 0x1D, Rev = 0x02, 1000baseT, FDX\n'
            'PHY 0x1F: OUI = 0x5043, Model = 0x0C, Rev = 0x02, 100baseT, HDX\n')  # 88E1111
    phys = eth.parse_mii_info(text)
    assert [(p.addr, p.is_88e151x) for p in phys] == [(1, True), (31, False)]


@pytest.mark.parametrize('text', ['', "Unknown command 'mii' - try 'help'\n",
                                  'Error reading PHY at address 0\n'])
def test_mii_info_without_a_phy_lists_none(text):
    assert eth.parse_mii_info(text) == []


def test_mii_read_value():
    assert eth.parse_mii_read('mii read 0x0 0x11\nAC00\nZynq> ') == 0xAC00
    assert eth.parse_mii_read('mii read 0x0 0x11\nError reading from the PHY\nZynq> ') is None
    assert eth.parse_mii_read('') is None


@pytest.mark.parametrize('word, link, resolved, speed, full', [
    (STATUS_1000_FD, True, True, 1000, True),
    (STATUS_100_FD, True, True, 100, True),
    (0x2C00, True, True, 10, True),              # 00 1 0 1 1
    (STATUS_1000_HD, True, True, 1000, False),
    (0x0000, False, False, None, False),         # nothing negotiated
    (0xAC00 & ~0x0800, True, False, None, True), # speed bits not valid until resolved
    (0xEC00, True, True, None, True),            # 11: reserved speed code
])
def test_copper_status_decoding(word, link, resolved, speed, full):
    status = eth.decode_copper_status(word)
    assert (status.link, status.resolved, status.speed, status.full_duplex) == \
        (link, resolved, speed, full)


# --- The U-Boot sequence ----------------------------------------------------------

def test_board_check_nominal():
    ub = FakeUBoot()
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.pings == [True] * 10
    assert board.ethaddr == '02:00:00:07:15:01' and board.ethaddr_source == 'set for this check'
    assert [(p.addr, p.is_88e151x) for p in board.phys] == [(0, True)]
    assert board.status.speed == 1000 and board.status.full_duplex


def test_board_network_settings_are_the_requested_ones():
    ub = FakeUBoot()
    eth.board_check(ub, Settings(host_if=HOST_IF, host_ip='10.200.0.1', board_ip='10.200.0.2', prefix=30))
    assert {'setenv ipaddr 10.200.0.2', 'setenv netmask 255.255.255.252',
            'setenv serverip 10.200.0.1'} <= set(ub.commands)
    assert all(c == 'ping 10.200.0.1' for c in ub.commands if c.startswith('ping'))


def test_a_mac_address_from_the_environment_is_kept():
    ub = FakeUBoot(ethaddr='00:0a:35:00:1e:53')
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.ethaddr == '00:0a:35:00:1e:53' and board.ethaddr_source == 'environment'
    assert not any(c.startswith('setenv ethaddr') for c in ub.commands)


def test_lost_pings_are_counted_individually():
    ub = FakeUBoot(alive=[False] + [True] * 8 + [False])
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.pings.count(True) == 8 and len(board.pings) == 10


def test_the_phy_is_read_where_mii_info_found_it():
    # U-Boot's banner probes address 0; the PHY may answer at another address
    ub = FakeUBoot(mii='PHY 0x01: OUI = 0x5043, Model = 0x1D, Rev = 0x01, 1000baseT, FDX\n',
                   registers={(1, 0x16): 0, (1, 0x11): STATUS_100_FD})
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.status.speed == 100


def test_link_status_is_read_after_the_pings():
    # The first ping brings the link up: a status read before it would show no link
    ub = FakeUBoot()
    eth.board_check(ub, Settings(host_if=HOST_IF))
    last_ping = max(i for i, c in enumerate(ub.commands) if c.startswith('ping'))
    status_read = max(i for i, c in enumerate(ub.commands) if c.startswith('mii read') and c.endswith('0x11'))
    assert status_read > last_ping


def test_without_mii_the_pings_still_run_and_the_status_is_not_claimed():
    ub = FakeUBoot(mii="Unknown command 'mii' - try 'help'\n")
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.phys == [] and board.status is None and board.status_note
    assert board.pings == [True] * 10


def test_status_on_another_register_page_is_not_decoded():
    ub = FakeUBoot(registers={(0, 0x16): 0x0002, (0, 0x11): STATUS_1000_FD})
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert board.status is None and 'page' in board.status_note


@pytest.mark.parametrize('ub', [FakeUBoot(), FakeUBoot(ethaddr='00:0a:35:00:1e:53'),
                                FakeUBoot(mii="Unknown command 'mii' - try 'help'\n"),
                                FakeUBoot(alive=[False] * 10)])
def test_the_check_changes_nothing_persistent(ub):
    # Only reads and RAM-only environment changes: no saveenv, no card, flash,
    # memory or PHY writes, no boot
    eth.board_check(ub, Settings(host_if=HOST_IF))
    allowed = re.compile(r'printenv ethaddr|setenv (ethaddr|ipaddr|netmask|serverip) \S+|'
                         r'mii info|mii read 0x[0-9a-f]+ 0x[0-9a-f]+|ping \S+')
    assert all(allowed.fullmatch(c) for c in ub.commands), ub.commands


# --- Pass criteria of TC-23 -------------------------------------------------------

def board_result(pings: list | None = None, status: int | None = STATUS_1000_FD):
    return eth.BoardResult(
        ethaddr='02:00:00:07:15:01', ethaddr_source='set for this check',
        phys=eth.parse_mii_info(MII_88E1512_AT_0),
        status=None if status is None else eth.decode_copper_status(status),
        status_note='' if status is not None else 'mii not available',
        pings=[True] * 10 if pings is None else pings)


def evaluate(board=None, before=None, after=None, expect_speed: int | None = 1000):
    return eth.evaluate(Settings(host_if=HOST_IF, expect_speed=expect_speed),
                        board or board_result(), before or host_state(rx_packets=100),
                        after or host_state(rx_packets=130))


def test_healthy_run_passes():
    criteria = evaluate()
    assert failed(criteria) == [] and criteria


def test_one_lost_ping_fails():
    assert failed(evaluate(board=board_result(pings=[True] * 9 + [False])))


@pytest.mark.parametrize('counter', ['rx_errors', 'rx_crc_errors', 'rx_frame_errors'])
def test_host_receive_errors_fail(counter):
    assert failed(evaluate(after=host_state(rx_packets=130, errors={counter: 1})))


def test_errors_already_counted_before_the_run_do_not_fail():
    before = host_state(rx_packets=100, errors={'rx_crc_errors': 7})
    after = host_state(rx_packets=130, errors={'rx_crc_errors': 7})
    assert failed(evaluate(before=before, after=after)) == []


def test_traffic_not_seen_on_the_test_port_fails():
    # Pings answered, but fewer packets than pings arrived on the port: they went elsewhere
    assert failed(evaluate(after=host_state(rx_packets=109)))


def test_exactly_one_packet_per_ping_is_enough():
    assert failed(evaluate(after=host_state(rx_packets=110))) == []


def test_no_carrier_after_the_pings_fails():
    assert failed(evaluate(after=host_state(carrier=False, speed=None, duplex=None, rx_packets=130)))


def test_host_speed_other_than_expected_fails():
    assert failed(evaluate(expect_speed=100))


def test_100_mbit_run_passes_when_both_sides_agree():
    criteria = evaluate(board=board_result(status=STATUS_100_FD),
                        after=host_state(speed=100, rx_packets=130), expect_speed=100)
    assert failed(criteria) == []


def test_board_and_host_disagreeing_on_speed_fails():
    assert failed(evaluate(board=board_result(status=STATUS_100_FD)))


@pytest.mark.parametrize('board_status, host_duplex', [(STATUS_1000_HD, 'full'), (STATUS_1000_FD, 'half')])
def test_half_duplex_on_either_side_fails(board_status, host_duplex):
    assert failed(evaluate(board=board_result(status=board_status),
                           after=host_state(duplex=host_duplex, rx_packets=130)))


def test_without_a_phy_reading_the_host_side_decides():
    assert failed(evaluate(board=board_result(status=None))) == []


def test_without_an_expected_speed_any_full_duplex_speed_passes():
    criteria = evaluate(board=board_result(status=STATUS_100_FD),
                        after=host_state(speed=100, rx_packets=130), expect_speed=None)
    assert failed(criteria) == []


# --- Host state and evidence ------------------------------------------------------

def make_sysfs(root, name, files):
    for rel, value in files.items():
        path = root / name / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{value}\n')


def test_host_state_is_read_from_sysfs(tmp_path):
    make_sysfs(tmp_path, HOST_IF, {'carrier': 1, 'speed': 1000, 'duplex': 'full',
                                   'statistics/rx_packets': 42, 'statistics/rx_crc_errors': 3})
    state = eth.read_host(HOST_IF, sysfs=str(tmp_path))
    assert (state.carrier, state.speed, state.duplex) == (True, 1000, 'full')
    assert state.counters['rx_packets'] == 42 and state.counters['rx_crc_errors'] == 3


def test_host_state_of_a_port_without_link(tmp_path):
    # Linux reports speed -1 and duplex unknown without link (or refuses the read)
    make_sysfs(tmp_path, HOST_IF, {'carrier': 0, 'speed': -1, 'duplex': 'unknown'})
    state = eth.read_host(HOST_IF, sysfs=str(tmp_path))
    assert (state.carrier, state.speed, state.duplex) == (False, None, None)


def test_missing_counters_fail_rather_than_pass(tmp_path):
    make_sysfs(tmp_path, HOST_IF, {'carrier': 1, 'speed': 1000, 'duplex': 'full'})
    state = eth.read_host(HOST_IF, sysfs=str(tmp_path))
    assert failed(eth.evaluate(Settings(host_if=HOST_IF), board_result(), state, state))


def test_package_checksums_match_the_files(tmp_path):
    (tmp_path / 'console.log').write_text('U-Boot 2022.01\n')
    eth.write_package(str(tmp_path), 'TC-23 summary\nPASS\n')
    sums = (tmp_path / 'SHA256SUMS').read_text().splitlines()
    listed = {line.split('  ')[1]: line.split('  ')[0] for line in sums}
    assert set(listed) == {'console.log', 'summary.txt'}
    for name, digest in listed.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest


# --- PHY status only where it can be read (TC-23 pass criteria) -----------------------

@pytest.mark.parametrize('registers', [{}, {(0, 0x16): 0}])  # page, then status, unreadable
def test_an_unreadable_phy_register_gives_no_status(registers):
    board = eth.board_check(FakeUBoot(registers=registers), Settings(host_if=HOST_IF))
    assert board.status is None and 'not readable' in board.status_note


def test_another_phy_model_is_listed_but_not_decoded():
    # The 88E1111 has a different register map: its status is not read as an 88E151x's
    ub = FakeUBoot(mii='PHY 0x00: OUI = 0x5043, Model = 0x0C, Rev = 0x02, 1000baseT, FDX\n')
    board = eth.board_check(ub, Settings(host_if=HOST_IF))
    assert [(p.addr, p.model) for p in board.phys] == [(0, 0x0C)]
    assert board.status is None and '88E151x' in board.status_note
    assert not any(c.startswith('mii read') for c in ub.commands)


# --- Evidence (TC-23: summary.txt records PHY, MAC and every criterion) ---------------

def test_summary_records_the_identity_and_every_criterion():
    s = Settings(host_if=HOST_IF, expect_speed=1000)
    board, before, after = board_result(), host_state(rx_packets=100), host_state(rx_packets=130)
    criteria = eth.evaluate(s, board, before, after)
    text = eth.summary_text(s, board, before, after, criteria, ['U-Boot 2022.01 (Apr 04 2022)'])
    assert 'PHY 0x00: OUI 0x5043 model 0x1d rev 1 (Marvell 88E151x)' in text
    assert 'board MAC: 02:00:00:07:15:01 (set for this check)' in text
    assert 'U-Boot: U-Boot 2022.01 (Apr 04 2022)' in text
    assert all(f'PASS  {c.name}:' in text for c in criteria)
    assert text.splitlines()[-1] == 'PASS'


def test_summary_verdict_fails_with_any_failed_criterion():
    s = Settings(host_if=HOST_IF)
    board = board_result(pings=[False] * 10, status=None)
    board.phys = []  # U-Boot without `mii`: the absence is recorded, not left out
    before, after = host_state(), host_state()
    text = eth.summary_text(s, board, before, after, eth.evaluate(s, board, before, after), [])
    assert 'FAIL  pings answered: 0 of 10' in text
    assert 'PHY: none listed by mii info' in text and 'pings: xxxxxxxxxx' in text
    assert text.splitlines()[-1] == 'FAIL'


# --- The script around the check ----------------------------------------------------

def run_main(monkeypatch, tmp_path, argv, ub=None, host=LAB_HOST):
    opened = []

    def fake_open(args, log):
        opened.append(args)
        log.write('U-Boot 2022.01 (Apr 04 2022 - 07:53:54 +0000)\n'
                  'Net:   \nZYNQ GEM: e000b000, mdio bus e000b000, phyaddr 0, interface rgmii-id\n')
        return ub or FakeUBoot()

    states = iter([host_state(rx_packets=100), host_state(rx_packets=130)])
    monkeypatch.setattr(eth, 'open_uboot', fake_open)
    monkeypatch.setattr(eth, 'host_addresses', lambda: host)
    monkeypatch.setattr(eth, 'read_host', lambda ifname: next(states))
    monkeypatch.setattr('sys.argv', ['uboot_eth_check.py', '--out', str(tmp_path / 'pkg')] + argv)
    with pytest.raises(SystemExit) as exit_info:
        eth.main()
    return exit_info.value.code, opened


@pytest.mark.parametrize('argv, host', [
    (['--host-if', HOST_IF, '--board-ip', '192.168.70.1'], LAB_HOST),  # invalid settings
    (['--host-if', 'enp1s0'], LAB_HOST),                               # port without the test address
])
def test_nothing_touches_the_board_when_the_set_up_is_wrong(monkeypatch, tmp_path, argv, host):
    code, opened = run_main(monkeypatch, tmp_path, argv, host=host)
    assert code not in (0, None) and opened == []
    assert not (tmp_path / 'pkg').exists()


def test_a_complete_run_writes_a_passing_package(monkeypatch, tmp_path):
    code, opened = run_main(monkeypatch, tmp_path, ['--host-if', HOST_IF, '--expect-speed', '1000'])
    assert code == 0 and len(opened) == 1
    pkg = tmp_path / 'pkg'
    assert sorted(p.name for p in pkg.iterdir()) == ['SHA256SUMS', 'console.log', 'summary.txt']
    summary = (pkg / 'summary.txt').read_text()
    assert summary.splitlines()[-1] == 'PASS'
    assert 'U-Boot: ZYNQ GEM: e000b000, mdio bus e000b000, phyaddr 0, interface rgmii-id' in summary


def test_a_failing_run_exits_nonzero(monkeypatch, tmp_path):
    code, _ = run_main(monkeypatch, tmp_path, ['--host-if', HOST_IF],
                       ub=FakeUBoot(alive=[True] * 9 + [False]))
    assert code == 1
    assert (tmp_path / 'pkg' / 'summary.txt').read_text().splitlines()[-1] == 'FAIL'


class FakeConsole:
    def __init__(self, port, xsdb, log):
        self.port, self.xsdb, self.log, self.calls = port, xsdb, log, []
        self.serial = self

    def reset_input_buffer(self):
        self.calls.append('flush')

    def write(self, data):
        self.calls.append(f'write {data!r}')

    def reset(self):
        self.calls.append('jtag reset')

    def stop_autoboot(self, timeout):
        self.calls.append(f'wait {timeout}')


@pytest.mark.parametrize('wait_reset, reboot, expected', [
    (None, False, ['jtag reset']),
    (60, False, ['flush', 'wait 60']),
    # the image's shell reboots the board into U-Boot, as uboot_load.py does
    (None, True, ['flush', "write b'\\rkernel reboot cold\\r'", 'wait 30']),
])
def test_reset_by_jtag_by_hand_or_from_the_shell(monkeypatch, wait_reset, reboot, expected):
    monkeypatch.setattr(eth, 'LoggedUBoot', FakeConsole)
    monkeypatch.setattr(eth, 'find_port', lambda port: '/dev/ttyUSB1')
    xsdb_lookups = []
    monkeypatch.setattr(eth, 'find_xsdb', lambda path: xsdb_lookups.append(path) or '/opt/xsdb')
    args = type('Args', (), dict(wait_reset=wait_reset, reboot=reboot, xsdb=None, port=None))()
    ub = eth.open_uboot(args, log=None)
    assert ub.calls == expected
    assert (xsdb_lookups == []) == (wait_reset is not None or reboot), 'only the JTAG reset needs xsdb'


def test_the_console_log_keeps_what_u_boot_printed():
    class Serial:
        chunks = [b'\x1b[0mZYNQ GEM: e000b000, mdio bus e000b000\r\n', b'Hit any key to stop autoboot']

        def read(self, size):
            return self.chunks.pop(0) if self.chunks else b''

    console = object.__new__(eth.LoggedUBoot)  # no serial port, no xsdb
    console.serial, console.log = Serial(), io.StringIO()
    console._read_until(b'Hit any key', 1)
    assert 'ZYNQ GEM: e000b000, mdio bus e000b000' in console.log.getvalue()
    assert '\x1b' not in console.log.getvalue()


@pytest.mark.skipif(shutil.which('ip') is None, reason='needs iproute2 (Linux)')
def test_host_addresses_have_the_fields_the_check_reads():
    loopback = next(i for i in eth.host_addresses() if i['ifname'] == 'lo')
    assert {'local': '127.0.0.1', 'prefixlen': 8}.items() <= loopback['addr_info'][0].items()


def test_an_aborted_run_is_recorded_as_a_failure(monkeypatch, tmp_path):
    def no_prompt(args, log):
        log.write('U-Boot 2022.01\n')
        sys.exit('could not stop U-Boot autoboot')

    monkeypatch.setattr(eth, 'open_uboot', no_prompt)
    monkeypatch.setattr(eth, 'host_addresses', lambda: LAB_HOST)
    monkeypatch.setattr(eth, 'read_host', lambda ifname: host_state())
    monkeypatch.setattr('sys.argv', ['uboot_eth_check.py', '--out', str(tmp_path / 'pkg'), '--host-if', HOST_IF])
    with pytest.raises(SystemExit) as exit_info:
        eth.main()
    assert exit_info.value.code not in (0, None)
    pkg = tmp_path / 'pkg'
    summary = (pkg / 'summary.txt').read_text()
    assert 'could not stop U-Boot autoboot' in summary and summary.splitlines()[-1] == 'FAIL'
    assert {line.split('  ')[1] for line in (pkg / 'SHA256SUMS').read_text().splitlines()} == \
        {'console.log', 'summary.txt'}
