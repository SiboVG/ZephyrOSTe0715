#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serial console for the TE0715 with a timestamped log (macOS, Linux, Windows).

Interactive: type shell commands (e.g. `csp ping 6016`) and press Enter; everything
the board prints is shown and written to the log. Ctrl-C quits.

Scripted: `--run commands.txt` sends each line of the file (blank lines and lines
starting with # are skipped), waits `--delay` seconds after each, and exits. A line
`sleep <seconds>` just waits.

  pip install pyserial
  python3 flatsat_console.py                         # auto-detects the Digilent UART
  python3 flatsat_console.py --run flatsat_checks.txt
  python3 flatsat_console.py --port /dev/cu.usbserial-25163300AA8CB

The log goes to flatsat-<date>-<time>.log in the current directory unless --log is
given. Only one program can use the serial port at a time.
"""

import argparse
import datetime
import glob
import re
import sys
import threading
import time

import serial

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
# The cable's FT2232H: interface A is JTAG, interface B (Linux: if01) is the UART
PORT_PATTERNS = [
    '/dev/cu.usbserial-*B',                            # macOS
    '/dev/serial/by-id/usb-Digilent_*-if01-port0',     # Linux
]


def find_port():
    for pattern in PORT_PATTERNS:
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    sys.exit('no Digilent UART found; pass --port (macOS: ls /dev/cu.usbserial-*; Linux: ls /dev/serial/by-id/)')


class Logger:
    def __init__(self, path):
        self.file = open(path, 'a', encoding='utf-8')
        self.partial = ''
        self.lock = threading.Lock()

    def write(self, text, prefix=''):
        with self.lock:
            self.partial += ANSI.sub('', text).replace('\r', '')
            *lines, self.partial = self.partial.split('\n')
            for line in lines:
                stamp = datetime.datetime.now().isoformat(timespec='milliseconds')
                self.file.write(f'{stamp} {prefix}{line}\n')
            self.file.flush()

    def note(self, text):
        stamp = datetime.datetime.now().isoformat(timespec='milliseconds')
        with self.lock:
            self.file.write(f'{stamp} >>> {text}\n')
            self.file.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', help='serial device (default: auto-detect)')
    parser.add_argument('--log', help='log file (default: flatsat-<date>-<time>.log)')
    parser.add_argument('--run', help='send the commands in this file, then exit')
    parser.add_argument('--delay', type=float, default=3.0,
                        help='seconds to wait after each scripted command (default 3)')
    args = parser.parse_args()

    port = args.port or find_port()
    log_path = args.log or datetime.datetime.now().strftime('flatsat-%Y%m%d-%H%M%S.log')
    log = Logger(log_path)
    ser = serial.Serial(port, 115200, timeout=0.05)
    print(f'[console] {port} at 115200 8N1, logging to {log_path}', file=sys.stderr)
    log.note(f'console opened on {port}')

    stop = threading.Event()

    def reader():
        while not stop.is_set():
            data = ser.read(4096)
            if data:
                text = data.decode(errors='replace')
                sys.stdout.write(text)
                sys.stdout.flush()
                log.write(text)

    threading.Thread(target=reader, daemon=True).start()

    def send(line):
        log.note(f'sent: {line}')
        ser.write(line.encode() + b'\r')

    try:
        if args.run:
            with open(args.run, encoding='utf-8') as f:
                commands = [line.strip() for line in f]
            for line in commands:
                if not line or line.startswith('#'):
                    continue
                if line.startswith('sleep '):
                    time.sleep(float(line.split()[1]))
                    continue
                send(line)
                time.sleep(args.delay)
        else:
            for line in sys.stdin:
                send(line.rstrip('\n'))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        time.sleep(0.2)
        log.note('console closed')
        print(f'\n[console] log saved to {log_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
