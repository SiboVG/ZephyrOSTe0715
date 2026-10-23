# SPDX-License-Identifier: Apache-2.0
"""zephyr_eth_check.py (TC-24, TE-ETH-002) against a fake board shell and a fake host ping.

Expected formats come from the tools, not from the script: iputils `ping` ends with
"N packets transmitted, M received, ..."; Zephyr's `net ping` prints one
"B bytes from SRC to DST: icmp_seq=K ttl=T time=X ms" line per reply and stops at
icmp_seq == count or with "Ping timeout"; `net iface` prints
"Status    : oper=..., admin=..., carrier=ON|OFF" and each IPv4 address as
"\t<addr>/<netmask> <type> <state>". Ethernet frame = ICMP payload + 8 + 20 + 14 bytes.
"""

import re

import pytest

import zephyr_eth_check as zec
from uboot_eth_check import HostState
from zephyr_eth_check import Settings

HOST_IF = 'enxa0cec8ebc610'
SIZES = (56, 469, 470, 471, 981, 982, 983, 1472)

IFACE_OK = ('\nInterface eth0 (0x1234) (Ethernet) [1]\n===================================\n'
            'Link addr : 02:00:00:07:15:01\nMTU       : 1500\nFlags     : AUTO_START,IPv4\n'
            'Device    : ethernet@e000b000 (0x5678)\n'
            'Status    : oper=UP, admin=UP, carrier=ON\n'
            'IPv4 unicast addresses (max 1):\n\t192.168.70.2/255.255.255.0 manual preferred infinite\n')


def iputils_output(sent, received, size=56):
    return (f'PING 192.168.70.2 ({size}) {size}({size + 28}) bytes of data.\n'
            f'--- 192.168.70.2 ping statistics ---\n'
            f'{sent} packets transmitted, {received} received, '
            f'{100 * (sent - received) // sent}% packet loss, time 9902ms\n'
            'rtt min/avg/max/mdev = 0.301/0.402/0.611/0.050 ms\n')


def zephyr_ping_output(seqs, host='192.168.70.1', size=4, timeout=False):
    lines = [f'PING {host}']
    lines += [f'{size + 4} bytes from {host} to 192.168.70.2: icmp_seq={k} ttl=64 time=0 ms' for k in seqs]
    if timeout:
        lines.append('Ping timeout')
    return '\n'.join(lines) + '\nuart:~$ '


class FakeShell:
    """sensor_bench.Console's run(): answers the board commands; records them."""

    def __init__(self, iface=IFACE_OK, board_seqs=None):
        self.iface = iface
        self.board_seqs = board_seqs or {}  # payload size -> icmp_seq list answered
        self.commands = []
        self.closed = False

    def close(self):
        self.closed = True

    def run(self, line, pattern, timeout=15):
        self.commands.append(line)
        if line == 'net iface':
            out = IFACE_OK if self.iface is None else self.iface
        elif line.startswith('net ping'):
            words = line.split()
            count = int(words[words.index('-c') + 1])
            size = int(words[words.index('-s') + 1])
            seqs = self.board_seqs.get(size, range(1, count + 1))
            out = zephyr_ping_output(seqs, size=size, timeout=count not in seqs)
        elif line == 'net stats':
            out = 'Interface 0x1234 (Ethernet) [1]\nIPv4 recv 1 sent 1 drop 0 forwarded 0\nuart:~$ '
        else:
            out = f'{line}: command not found\nuart:~$ '
        found = re.search(f'(?:{pattern})(?=\n)', out, re.M)
        return (found.group(0) if found else None), out


class FakePing:
    def __init__(self, received=None):
        self.received = received or {}  # payload size -> replies received (of count)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        count = int(argv[argv.index('-c') + 1])
        size = int(argv[argv.index('-s') + 1])
        return iputils_output(count, self.received.get(size, count), size)


def host_state(speed: int | None = 100, duplex: str | None = 'full', carrier: bool = True,
               rx_packets: int = 1000, errors: dict | None = None):
    counters = {'rx_packets': rx_packets, 'tx_packets': 900, 'rx_errors': 0,
                'rx_crc_errors': 0, 'rx_frame_errors': 0}
    counters.update(errors or {})
    return HostState(carrier=carrier, speed=speed, duplex=duplex, counters=counters)


def failed(criteria):
    return [c.name for c in criteria if not c.passed]


# --- Settings -----------------------------------------------------------------------

def test_default_settings_follow_tc24():
    s = Settings(host_if=HOST_IF)
    assert zec.settings_problems(s) == []
    assert s.sizes == SIZES and s.count == 100
    assert s.board_sizes == (4, 1472) and s.board_count == 10 and s.expect_speed == 100


@pytest.mark.parametrize('change', [
    dict(board_ip='192.168.70.1'), dict(board_ip='10.1.1.1'), dict(prefix=31),
    dict(sizes=(1473,)),        # beyond the 1500-byte MTU with the don't-fragment flag
    dict(sizes=(-1,)), dict(sizes=()),
    dict(board_sizes=(1473,)), dict(count=0), dict(board_count=0),
])
def test_unusable_settings_are_refused(change):
    assert zec.settings_problems(Settings(host_if=HOST_IF, **change)) != []


def test_boundary_sizes_are_accepted():
    assert zec.settings_problems(Settings(host_if=HOST_IF, sizes=(0, 1472), board_sizes=(0, 1472))) == []


# --- Commands and parsing -------------------------------------------------------------

def test_host_ping_goes_to_the_board_through_the_test_port_unfragmented():
    argv = zec.host_ping_argv(Settings(host_if=HOST_IF), 982)
    assert argv[0] == 'ping' and argv[-1] == '192.168.70.2'
    assert argv[argv.index('-I') + 1] == HOST_IF
    assert argv[argv.index('-M') + 1] == 'do'  # don't fragment: one frame per request
    assert argv[argv.index('-s') + 1] == '982' and argv[argv.index('-c') + 1] == '100'


@pytest.mark.parametrize('text, expected', [
    (iputils_output(100, 100), (100, 100)),
    (iputils_output(100, 97), (100, 97)),
    ('--- x ---\n100 packets transmitted, 98 received, +2 errors, 2% packet loss, time 9s\n', (100, 98)),
    ('ping: local error: message too long, mtu=1500\n', None),
    ('', None),
])
def test_host_ping_summary(text, expected):
    assert zec.parse_host_ping(text) == expected


def test_board_ping_counts_each_reply_from_the_host_once():
    text = zephyr_ping_output([1, 2, 2, 3])
    text += '\n8 bytes from 192.168.70.9 to 192.168.70.2: icmp_seq=4 ttl=64 time=0 ms\n'
    assert zec.board_ping_replies(text, '192.168.70.1') == 3


def test_board_ping_without_replies():
    assert zec.board_ping_replies(zephyr_ping_output([], timeout=True), '192.168.70.1') == 0


@pytest.mark.parametrize('text, carrier, address', [
    (IFACE_OK, True, True),
    (IFACE_OK.replace('carrier=ON', 'carrier=OFF'), False, True),
    (IFACE_OK.replace('192.168.70.2/', '192.168.70.3/'), True, False),
    ('net: command not found\n', False, False),
])
def test_interface_state(text, carrier, address):
    state = zec.parse_iface(text, '192.168.70.2')
    assert (state.carrier, state.address) == (carrier, address)


# --- The check sequence --------------------------------------------------------------

def test_check_runs_every_size_both_ways():
    shell, ping = FakeShell(), FakePing()
    result = zec.run_check(shell, ping, Settings(host_if=HOST_IF))
    assert sorted(result.host) == sorted(SIZES)
    assert all(result.host[n] == (100, 100) for n in SIZES)
    assert result.board == {4: 10, 1472: 10}
    assert result.iface.carrier and result.iface.address
    assert 'IPv4 recv' in result.stats
    sent_sizes = sorted(int(a[a.index('-s') + 1]) for a in ping.calls)
    assert sent_sizes == sorted(SIZES)


def test_board_pings_use_the_requested_size_and_count():
    shell = FakeShell()
    zec.run_check(shell, FakePing(), Settings(host_if=HOST_IF))
    pings = [c for c in shell.commands if c.startswith('net ping')]
    assert len(pings) == 2
    for cmd, size in zip(pings, (4, 1472)):
        words = cmd.split()
        assert words[-1] == '192.168.70.1'
        assert words[words.index('-c') + 1] == '10' and words[words.index('-s') + 1] == str(size)


def test_losses_are_counted_per_size():
    result = zec.run_check(FakeShell(board_seqs={1472: [1, 2, 3, 5, 6, 7, 8, 9, 10]}),
                           FakePing(received={470: 99}), Settings(host_if=HOST_IF))
    assert result.host[470] == (100, 99) and result.host[469] == (100, 100)
    assert result.board == {4: 10, 1472: 9}


# --- Pass criteria of TC-24 ----------------------------------------------------------

def result_with(**change):
    result = zec.run_check(FakeShell(), FakePing(), Settings(host_if=HOST_IF))
    for key, value in change.items():
        setattr(result, key, value)
    return result


def evaluate(result=None, before=None, after=None):
    return zec.evaluate(Settings(host_if=HOST_IF), result or result_with(),
                        before or host_state(), after or host_state(rx_packets=3000))


def test_healthy_run_passes():
    criteria = evaluate()
    assert failed(criteria) == [] and criteria


def test_one_lost_reply_at_one_size_fails():
    result = result_with()
    result.host[1472] = (100, 99)
    assert failed(evaluate(result))


def test_a_size_without_a_ping_summary_fails():
    result = result_with()
    result.host[982] = None
    assert failed(evaluate(result))


def test_a_lost_board_ping_fails():
    result = result_with()
    result.board[4] = 9
    assert failed(evaluate(result))


@pytest.mark.parametrize('iface', [zec.IfaceState(carrier=False, address=True),
                                   zec.IfaceState(carrier=True, address=False)])
def test_board_interface_not_up_with_its_address_fails(iface):
    assert failed(evaluate(result_with(iface=iface)))


@pytest.mark.parametrize('after', [
    host_state(speed=1000, rx_packets=3000),        # not the 100 Mbit/s baseline
    host_state(duplex='half', rx_packets=3000),
    host_state(carrier=False, speed=None, duplex=None, rx_packets=3000),
])
def test_host_link_other_than_100_full_fails(after):
    assert failed(evaluate(after=after))


@pytest.mark.parametrize('counter', ['rx_errors', 'rx_crc_errors', 'rx_frame_errors'])
def test_host_receive_errors_fail(counter):
    assert failed(evaluate(after=host_state(rx_packets=3000, errors={counter: 1})))


def test_missing_host_counters_fail():
    after = HostState(carrier=True, speed=100, duplex='full', counters={})
    assert failed(evaluate(after=after))


# --- The script around the check ----------------------------------------------------

LAB_HOST = [{'ifname': 'enp1s0', 'addr_info': [{'local': '10.33.179.55', 'prefixlen': 24}]},
            {'ifname': HOST_IF, 'addr_info': [{'local': '192.168.70.1', 'prefixlen': 24}]}]


def run_main(monkeypatch, tmp_path, argv, shell=None, ping=None, host=LAB_HOST):
    opened = []

    def open_shell(port, log_path):
        opened.append(port)
        with open(log_path, 'w') as log:
            log.write('uart:~$ net iface\n' + IFACE_OK)
        return shell or FakeShell()

    states = iter([host_state(), host_state(rx_packets=3000)])
    monkeypatch.setattr(zec, 'open_shell', open_shell)
    monkeypatch.setattr(zec, 'host_ping', ping or FakePing())
    monkeypatch.setattr(zec, 'host_addresses', lambda: host)
    monkeypatch.setattr(zec, 'read_host', lambda ifname: next(states))
    monkeypatch.setattr('sys.argv', ['zephyr_eth_check.py', '--out', str(tmp_path / 'pkg'),
                                     '--port', '/dev/ttyUSB1'] + argv)
    with pytest.raises(SystemExit) as exit_info:
        zec.main()
    return exit_info.value.code, opened


@pytest.mark.parametrize('argv', [['--host-if', HOST_IF, '--board-ip', '192.168.70.1'],
                                  ['--host-if', 'enp1s0']])
def test_nothing_touches_the_board_when_the_set_up_is_wrong(monkeypatch, tmp_path, argv):
    code, opened = run_main(monkeypatch, tmp_path, argv)
    assert code not in (0, None) and opened == []
    assert not (tmp_path / 'pkg').exists()


def test_a_complete_run_writes_a_passing_package(monkeypatch, tmp_path):
    shell = FakeShell()
    code, opened = run_main(monkeypatch, tmp_path, ['--host-if', HOST_IF], shell=shell)
    assert code == 0 and opened == ['/dev/ttyUSB1'] and shell.closed
    pkg = tmp_path / 'pkg'
    assert sorted(p.name for p in pkg.iterdir()) == ['SHA256SUMS', 'console.log', 'host-ping.txt', 'summary.txt']
    summary = (pkg / 'summary.txt').read_text()
    assert summary.splitlines()[-1] == 'PASS'
    assert '1472 bytes (frame 1514): 100 of 100' in summary
    assert 'IPv4 recv' in summary  # the board's net stats are kept
    assert (pkg / 'host-ping.txt').read_text().count('packets transmitted') == len(SIZES)


def test_a_failing_run_exits_nonzero(monkeypatch, tmp_path):
    code, _ = run_main(monkeypatch, tmp_path, ['--host-if', HOST_IF], ping=FakePing(received={56: 0}))
    assert code == 1
    assert (tmp_path / 'pkg' / 'summary.txt').read_text().splitlines()[-1] == 'FAIL'


def test_an_aborted_run_is_recorded_as_a_failure(monkeypatch, tmp_path):
    class DeadShell(FakeShell):
        def run(self, line, pattern, timeout=15):
            raise OSError('serial port disappeared')

    shell = DeadShell()
    with pytest.raises(OSError):
        run_main(monkeypatch, tmp_path, ['--host-if', HOST_IF], shell=shell)
    assert shell.closed, 'the console log is flushed also when the check stops early'
    summary = (tmp_path / 'pkg' / 'summary.txt').read_text()
    assert 'serial port disappeared' in summary and summary.splitlines()[-1] == 'FAIL'


def test_host_ping_runs_the_real_command(monkeypatch):
    seen = {}

    def fake_run(argv, capture_output, text, timeout):
        seen.update(argv=argv, timeout=timeout)
        return type('R', (), dict(stdout=iputils_output(3, 3), stderr=''))()

    monkeypatch.setattr(zec.subprocess, 'run', fake_run)
    out = zec.host_ping(['ping', '-c', '3', '-s', '56', '192.168.70.2'])
    assert zec.parse_host_ping(out) == (3, 3) and seen['argv'][0] == 'ping' and seen['timeout'] > 0
