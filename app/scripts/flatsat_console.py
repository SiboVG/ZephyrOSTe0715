#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serial console for the TE0715 with a timestamped log (macOS, Linux, Windows).

Interactive: type shell commands (e.g. `csp ping 6016`) and press Enter; everything
the board prints is shown and written to the log. Ctrl-C (or Ctrl-D) quits. On macOS
and Linux the input line has a history: Up/Down recall earlier commands (also from
previous sessions, kept in ~/.flatsat_console_history), Left/Right edit the line, and
Ctrl-R searches. The board's output is printed above the line being typed.

Scripted: `--run commands.txt` sends each line of the file (blank lines and lines
starting with # are skipped), waits `--delay` seconds after each, and exits. A line
`sleep <seconds>` just waits.

  pip install pyserial
  python3 flatsat_console.py                         # auto-detects the Digilent UART
  python3 flatsat_console.py --run flatsat_checks.txt
  python3 flatsat_console.py --port /dev/cu.usbserial-25163300AA8CB

The cable's serial chip is powered by the board, so the port only appears once the
board is on. If it is not there yet, the console waits for it (Ctrl-C gives up), so it
can be started before powering the board and catch the boot.

The log goes to flatsat-<date>-<time>.log in the current directory unless --log is
given. Only one program can use the serial port at a time.
"""

import argparse
import datetime
import glob
import os
import re
import sys
import threading
import time

import serial

try:
    import readline
except ImportError:     # Windows: plain line input without history
    readline = None

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
PROMPT = 'uart:~$ '
BOARD_PROMPT = re.compile(r'uart:~\$ ?')
HISTORY = os.path.expanduser('~/.flatsat_console_history')
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
    return None


def wait_and_open(port_arg):
    """Open the port, waiting for it to appear while the board is powered off."""
    waiting = False
    last_error = None
    while True:
        port = port_arg or find_port()
        if port and os.path.exists(port):
            try:
                return port, serial.Serial(port, 115200, timeout=0.05)
            except serial.SerialException as e:
                # Normal for a moment after the port appears; if it persists (for
                # example no permission on Linux), the message says why
                if str(e) != last_error:
                    print(f'[console] {e}', file=sys.stderr)
                    last_error = str(e)
        if not waiting:
            name = port_arg or 'the Digilent UART'
            print(f'[console] waiting for {name}; power on the board (Ctrl-C quits)',
                  file=sys.stderr)
            waiting = True
        time.sleep(0.1)


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


class Screen:
    """Board output above a local input line with history (readline).

    Only complete lines of board output are printed, each time followed by the input
    line again. The board's prompt at the end of its output is not printed, since
    the input line shows it; the board then echoes the command after its prompt, so
    the typed line is removed once it is sent to avoid showing it twice. A partial
    line that is not the prompt is printed after a short pause.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.tail = ''
        self.tail_time = 0.0
        self.reading = False

    def _show(self, text):
        line = PROMPT + readline.get_line_buffer() if self.reading else ''
        sys.stdout.write('\r\x1b[K' + text + line)
        sys.stdout.flush()

    def output(self, text):
        with self.lock:
            head, newline, self.tail = (self.tail + text).rpartition('\n')
            self.tail_time = time.monotonic()
            if newline:
                self._show(head + newline)

    def idle(self):
        """Called when no data arrived: print a partial line that has stalled."""
        with self.lock:
            if (self.tail and time.monotonic() - self.tail_time > 0.2
                    and not BOARD_PROMPT.fullmatch(ANSI.sub('', self.tail).strip('\r'))):
                self._show(self.tail + '\n')
                self.tail = ''

    def input(self):
        with self.lock:
            self.reading = True
        try:
            line = input(PROMPT)
        finally:
            with self.lock:
                self.reading = False
        with self.lock:
            sys.stdout.write('\x1b[1A\r\x1b[K')     # the board echoes the line
            sys.stdout.flush()
        return line


def load_history():
    try:
        readline.read_history_file(HISTORY)
    except OSError:
        pass
    readline.set_history_length(1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', help='serial device (default: auto-detect)')
    parser.add_argument('--log', help='log file (default: flatsat-<date>-<time>.log)')
    parser.add_argument('--run', help='send the commands in this file, then exit')
    parser.add_argument('--delay', type=float, default=3.0,
                        help='seconds to wait after each scripted command (default 3)')
    args = parser.parse_args()

    try:
        port, ser = wait_and_open(args.port)
    except KeyboardInterrupt:
        sys.exit('\n[console] no port found; pass --port '
                 '(macOS: ls /dev/cu.usbserial-*; Linux: ls /dev/serial/by-id/)')
    log_path = args.log or datetime.datetime.now().strftime('flatsat-%Y%m%d-%H%M%S.log')
    log = Logger(log_path)
    print(f'[console] {port} at 115200 8N1, logging to {log_path}', file=sys.stderr)
    log.note(f'console opened on {port}')

    stop = threading.Event()
    screen = (Screen() if readline and not args.run and sys.stdin.isatty()
              and sys.stdout.isatty() else None)

    def reader():
        while not stop.is_set():
            data = ser.read(4096)
            if data:
                text = data.decode(errors='replace')
                if screen:
                    screen.output(text)
                else:
                    sys.stdout.write(text)
                    sys.stdout.flush()
                log.write(text)
            elif screen:
                screen.idle()

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
        elif screen:
            load_history()
            while True:
                send(screen.input())
        else:
            for line in sys.stdin:
                send(line.rstrip('\n'))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
        time.sleep(0.2)
        if screen:
            try:
                readline.write_history_file(HISTORY)
            except OSError:
                pass
        log.note('console closed')
        print(f'\n[console] log saved to {log_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
