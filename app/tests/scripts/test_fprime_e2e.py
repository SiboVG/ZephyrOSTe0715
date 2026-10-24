# SPDX-License-Identifier: Apache-2.0
"""fprime_e2e.py's command line: how the board is started and how the Linux side
reaches it (TC-06 to TC-08 over CAN, TC-25 over Ethernet)."""

import pytest

import fprime_e2e


def parse(*argv):
    return fprime_e2e.parse_args(['--bench', '/opt/CspBench', '--log', 'e2e.log', *argv])


def test_can_is_the_default_link():
    args = parse('--elf', 'zephyr.elf')
    assert fprime_e2e.link_args(args) == ['--can', 'can0']
    assert fprime_e2e.link_args(parse('--sd-boot', '--can', 'can7')) == ['--can', 'can7']


def test_udp_link_to_the_board():
    args = parse('--attach', '--udp', '192.168.70.2')
    assert fprime_e2e.link_args(args) == ['--udp', '192.168.70.2']


@pytest.mark.parametrize('argv', [
    ('--elf', 'zephyr.elf', '--can', 'can0', '--udp', '192.168.70.2'),  # one link only
    (),                                                                # a start mode is required
    ('--attach', '--elf', 'zephyr.elf'),                               # only one start mode
])
def test_ambiguous_command_lines_are_refused(argv):
    with pytest.raises(SystemExit):
        parse(*argv)


def test_only_loading_or_resetting_needs_xsdb():
    assert fprime_e2e.needs_xsdb(parse('--elf', 'zephyr.elf'))
    assert fprime_e2e.needs_xsdb(parse('--sd-boot'))
    assert not fprime_e2e.needs_xsdb(parse('--attach', '--udp', '192.168.70.2'))


def test_reference_ping_uses_the_same_link_and_nodes():
    args = parse('--attach', '--udp', '192.168.70.2', '--reference', '/opt/CspPingClient', '--node', '6062')
    assert fprime_e2e.reference_command(args) == [
        '/opt/CspPingClient', '--udp', '192.168.70.2', '--node', '100', '--peer', '6062']
    assert fprime_e2e.reference_command(parse('--attach')) is None
