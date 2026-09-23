#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a csh command file against the TE0715 and log csh and the board console (TC-10).

csh (Space Inventor's CSP shell) needs a terminal, so it is driven through a pty.
Each line of the command file is sent in turn; `sleep <ms>` lines are csh's own
sleep command. The board's console is logged at the same time, so the transcript
shows both sides, e.g. the `PARAM led_d4 = 1: LED D4 on` lines.

  app/scripts/csh_check.py --csh path/to/csh/builddir/csh --commands tc10.csh --log tc10.log

The command file must start with the CSP set-up, for example:

  csp init
  csp add can -c can0 -d 100

Needs pexpect and pyserial. Prints the transcript; exits with 1 if csh or the board
reports no parameter value at all.
"""

import argparse
import io
import os
import re
import sys
import tempfile
import threading
import time

import pexpect
import serial

from hw_test import find_port

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]|\r')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--csh', required=True, help='csh executable')
    parser.add_argument('--commands', required=True, help='file with one csh command per line')
    parser.add_argument('--log', required=True, help='transcript file')
    parser.add_argument('--port', help='UART device')
    args = parser.parse_args()

    console = serial.Serial(find_port(args.port), 115200, timeout=0.05)
    board = bytearray()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            board.extend(console.read(4096))

    threading.Thread(target=reader, daemon=True).start()
    console.write(b'bench info\r')
    time.sleep(1.5)

    commands = [line.strip() for line in open(args.commands)
                if line.strip() and not line.startswith('#') and line.strip() != 'exit']
    with tempfile.NamedTemporaryFile('w', suffix='.csh') as empty:
        # An empty init file, so csh does not run the user's own init.csh
        csh = pexpect.spawn(args.csh, ['-i', empty.name], encoding='utf-8',
                            dimensions=(50, 200))
        transcript = io.StringIO()
        csh.logfile_read = transcript

        def drain(seconds):
            end = time.time() + seconds
            while time.time() < end:
                try:
                    csh.read_nonblocking(65536, timeout=0.2)
                except pexpect.TIMEOUT:
                    pass
                except pexpect.EOF:
                    return

        drain(2)
        for command in commands:
            csh.sendline(command)
            drain(4 if command.startswith(('sleep', 'list download')) else 1.5)
        csh.sendline('exit')
        drain(1)
        csh.terminate(force=True)
    time.sleep(1)
    stop.set()

    # csh redraws its prompt (hostname) on every keystroke: keep what follows the last one
    prompt = os.uname().nodename
    lines = [line.split(prompt)[-1].rstrip()
             for line in ANSI.sub('', transcript.getvalue()).splitlines()
             if 'Init file' not in line and 'not found' not in line]
    text = (f'=== csh ({args.csh})\n' + '\n'.join(lines) +
            '\n\n=== TE0715 console\n' + ANSI.sub('', board.decode(errors='replace')))
    with open(args.log, 'w') as f:
        f.write(text)
    print(text)
    return 0 if re.search(r'^ *\d+:\d+ +\S+ += [^-]', text, re.M) else 1


if __name__ == '__main__':
    sys.exit(main())
