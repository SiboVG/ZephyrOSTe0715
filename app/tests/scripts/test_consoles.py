# SPDX-License-Identifier: Apache-2.0
"""Console helpers of hw_test.py, flatsat_console.py and csh_check.py."""

import re

import csh_check
import flatsat_console
import hw_test


def console_with(*chunks):
    console = object.__new__(hw_test.Console)  # no serial port
    console.chunks = [c.encode() for c in chunks]
    return console


def test_console_text_starts_at_the_last_boot_banner():
    c = console_with('old run\n*** Booting Zephyr OS build v4\nfirst\n',
                     '*** Booting Zephyr OS build v4\nsecond boot\n')
    assert c.text().startswith('*** Booting Zephyr')
    assert 'second boot' in c.text() and 'first' not in c.text()


def test_console_text_before_any_banner_is_kept():
    # a crash during device initialization happens before the banner
    assert console_with('E: fault\n').text() == 'E: fault\n'


def test_keyboard_prompt_waits_until_a_result_follows():
    prompt = 'Please send characters to serial console\n'
    assert hw_test.waiting_for_keyboard('START - test_read\n' + prompt)
    assert not hw_test.waiting_for_keyboard(prompt + ' PASS - test_read in 1.2 seconds\n')
    assert not hw_test.waiting_for_keyboard('no prompt here\n')
    # an earlier, answered prompt does not count
    text = prompt + ' PASS - a in 1 s\n' + 'START - b\n' + prompt
    assert hw_test.waiting_for_keyboard(text)


def test_flatsat_logger_timestamps_complete_lines(tmp_path):
    path = tmp_path / 'log.txt'
    log = flatsat_console.Logger(str(path))
    log.write('\x1b[1;32muart:~$ \x1b[mbench in')
    log.write('fo\r\nnode 6061/8 (started)\r\npart')
    log.note('sent: bench info')
    lines = path.read_text().splitlines()
    stamp = r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3} '
    assert re.fullmatch(stamp + r'uart:~\$ bench info', lines[0])
    assert re.fullmatch(stamp + r'node 6061/8 \(started\)', lines[1])
    assert re.fullmatch(stamp + r'>>> sent: bench info', lines[2])
    assert len(lines) == 3, 'an incomplete line stays buffered'


def test_flatsat_port_prefers_the_uart_interface(monkeypatch):
    found = {'/dev/cu.usbserial-*B': ['/dev/cu.usbserial-25163300AA8CB'],
             '/dev/serial/by-id/usb-Digilent_*-if01-port0': []}
    monkeypatch.setattr(flatsat_console.glob, 'glob', lambda p: found.get(p, []))
    assert flatsat_console.find_port() == '/dev/cu.usbserial-25163300AA8CB'
    assert all(p.endswith(('B', 'if01-port0')) for p in flatsat_console.PORT_PATTERNS), \
        'interface A of the cable is JTAG, not the console'


def test_csh_transcript_keeps_the_text_after_the_last_prompt():
    raw = ('\x1b[33m  Init file: /tmp/x.csh\r\n  File /tmp/x not found\r\n'
           ' host \x1b[0m g host ge host get led_d4 @ 20:53:02\r\n'
           ' 201:6061  led_d4               = 0\r\n')
    assert csh_check.clean_transcript(raw, 'host').splitlines() == [
        ' get led_d4 @ 20:53:02', ' 201:6061  led_d4               = 0']
