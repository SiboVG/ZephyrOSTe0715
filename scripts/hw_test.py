#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build Zephyr apps/tests for the TE0715, load them over JTAG and check the UART.

Needs the Digilent JTAG/UART cable (TE0701) and AMD xsdb. Nothing is written to
QSPI flash or the SD card: every image is loaded into DDR.

Examples (run from anywhere inside the west workspace):

  # run ztest suites and report PASS/FAIL per suite (exit code 1 on failure)
  scripts/hw_test.py test tests/kernel/common tests/drivers/uart/uart_basic_api

  # run an application and show its console output for 10 s
  scripts/hw_test.py run app --seconds 10

  # run an application until its output matches a regex
  scripts/hw_test.py run app --until "Hello from Trenz"

Relative test paths are looked up in $ZEPHYR_BASE (or <workspace>/zephyr) first,
then relative to the current directory.
"""

import argparse
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import serial

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(APP_DIR)
XSDB_CFG = os.path.join(APP_DIR, 'boards', 'trenz', 'te0715', 'support', 'xsdb.cfg')
BOARD = 'te0715'
BANNER = '*** Booting Zephyr'
# Prompt printed by ztest cases with "harness: keyboard"
KEYBOARD_PROMPT = 'Please send characters'


def find_xsdb(explicit):
    if explicit:
        return explicit
    found = shutil.which('xsdb')
    if found:
        return found
    candidates = sorted(glob.glob('/tools/Xilinx/Vitis/*/bin/xsdb'))
    if candidates:
        return candidates[-1]
    sys.exit('xsdb not found: put it on PATH or pass --xsdb')


def find_port(explicit):
    if explicit:
        return explicit
    # Interface 1 of the Digilent FT2232H is the UART, interface 0 is JTAG
    ports = sorted(glob.glob('/dev/serial/by-id/usb-Digilent_*-if01-port0'))
    if not ports:
        sys.exit('Digilent UART not found: is the JTAG/UART cable connected? '
                 'Pass --port otherwise')
    return ports[0]


def resolve_source(path, zephyr_base):
    for base in (zephyr_base, os.getcwd()):
        candidate = os.path.join(base, path)
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
    sys.exit(f'source directory not found: {path}')


def build(source, build_dir, zephyr_base, extra_args):
    env = dict(os.environ, ZEPHYR_BASE=zephyr_base)
    cmd = ['west', 'build', '-p', 'auto', '-b', BOARD, '-d', build_dir, source,
           '--', f'-DBOARD_ROOT={APP_DIR}'] + extra_args
    result = subprocess.run(cmd, cwd=WORKSPACE, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-4000:], result.stderr[-4000:], sep='\n')
        return False
    return True


class Console:
    """Collects everything the board prints on the UART in a background thread."""

    def __init__(self, port, log_path):
        self.serial = serial.Serial(port, 115200, timeout=0.1)
        self.serial.reset_input_buffer()
        self.log = open(log_path, 'wb')
        self.chunks = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while not self.stop.is_set():
            data = self.serial.read(4096)
            if data:
                self.log.write(data)
                self.log.flush()
                self.chunks.append(data)

    def text(self):
        """Output since the last Zephyr boot banner (earlier boot stages dropped)."""
        text = b''.join(self.chunks).decode(errors='replace')
        idx = text.rfind(BANNER)
        return text[idx:] if idx >= 0 else ''

    def write(self, data):
        self.serial.write(data)

    def close(self):
        self.stop.set()
        self.thread.join()
        self.serial.close()
        self.log.close()


def waiting_for_keyboard(text):
    """True if a keyboard-harness prompt has not been followed by a test result yet."""
    prompt = text.rfind(KEYBOARD_PROMPT)
    return prompt >= 0 and not re.search(r' (PASS|FAIL|SKIP) - ', text[prompt:])


def load(xsdb, elf):
    result = subprocess.run(['timeout', '120', xsdb, XSDB_CFG, elf],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-3000:], result.stderr[-3000:], sep='\n')
        return False
    return True


def run_image(args, source, name, done):
    """Build, load and watch the console until done(text) returns a result."""
    if args.extra_args:
        # keep variants (e.g. different CONF_FILE) in separate build directories
        name += '-' + hashlib.sha1(' '.join(args.extra_args).encode()).hexdigest()[:8]
    build_dir = os.path.join(args.build_root, name)
    if not build(source, build_dir, args.zephyr_base, args.extra_args):
        return 'BUILD FAILED', ''
    console = Console(args.port, os.path.join(build_dir, 'console.log'))
    try:
        if not load(args.xsdb, os.path.join(build_dir, 'zephyr', 'zephyr.elf')):
            return 'LOAD FAILED', console.text()
        start = time.time()
        while time.time() - start < args.timeout:
            text = console.text()
            result = done(text, time.time() - start)
            if result:
                return result, text
            if waiting_for_keyboard(text):
                console.write(b'a\r')  # ztest keyboard cases wait for a line ending
            time.sleep(0.5)
        return 'TIMEOUT', console.text()
    finally:
        console.close()


def cmd_test(args):
    failed = 0
    for test in args.paths:
        source = resolve_source(test, args.zephyr_base)
        name = os.path.relpath(source, args.zephyr_base).replace(os.sep, '_')

        def verdict(text, _elapsed):
            m = re.search(r'PROJECT EXECUTION (SUCCESSFUL|FAILED)', text)
            return m and m.group(1)

        result, text = run_image(args, source, name, verdict)
        for line in text.splitlines():
            if re.match(r'\s*(SUITE (PASS|FAIL|SKIP)|- FAIL -)', line):
                print('   ', line.strip())
        garbled = sum(1 for c in text if c == '�' or (ord(c) < 32 and c not in '\t\r\n'))
        note = f', {garbled} garbled characters' if garbled else ''
        print(f'{result:<12} {test}{note}')
        failed += result != 'SUCCESSFUL' or garbled != 0
    return 1 if failed else 0


def cmd_run(args):
    source = resolve_source(args.paths[0], args.zephyr_base)
    name = os.path.basename(source.rstrip(os.sep))
    until = re.compile(args.until) if args.until else None

    def finished(text, elapsed):
        if until and until.search(text):
            return 'MATCHED'
        if not until and elapsed >= args.seconds:
            return 'DONE'
        return None

    if not until:
        args.timeout = args.seconds + 1
    result, text = run_image(args, source, name, finished)
    print(text)
    print(f'--- {result}')
    return 0 if result in ('MATCHED', 'DONE') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['test', 'run'])
    parser.add_argument('paths', nargs='+', help='test or application directories')
    parser.add_argument('--timeout', type=float, default=120,
                        help='seconds to wait for a verdict / match (default 120)')
    parser.add_argument('--seconds', type=float, default=10,
                        help='run: how long to capture output (default 10)')
    parser.add_argument('--until', help='run: stop once the output matches this regex')
    parser.add_argument('--port', help='UART device (default: Digilent cable interface 1)')
    parser.add_argument('--xsdb', help='path to xsdb (default: PATH, then /tools/Xilinx)')
    parser.add_argument('--zephyr-base', default=os.environ.get(
        'ZEPHYR_BASE', os.path.join(WORKSPACE, 'zephyr')))
    parser.add_argument('--build-root', default=os.path.join(WORKSPACE, 'build', 'hw'),
                        help='where build directories and console logs go')
    parser.add_argument('-x', dest='extra_args', action='append', default=[],
                        help='extra CMake argument for every image, e.g. -x-DCONF_FILE=prj_poll.conf')
    args = parser.parse_args()
    args.zephyr_base = os.path.abspath(args.zephyr_base)
    args.xsdb = find_xsdb(args.xsdb)
    args.port = find_port(args.port)
    return cmd_test(args) if args.command == 'test' else cmd_run(args)


if __name__ == '__main__':
    sys.exit(main())
