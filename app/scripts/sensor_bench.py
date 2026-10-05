#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hardware tests of the INA229 and ADXL355 benches on the TE0715 (SPI1 on Pmod J1).

The board runs apps/fprime_ina229_bench or apps/fprime_adxl355_bench. This script loads
the image over JTAG (--elf), resets the board so it boots from the SD card (--sd-boot),
or uses a board that already runs it (--attach), waits for the ready marker and runs
the automated checks over the serial shell. With --interactive it also runs the steps
that need the operator: reference measurements, fault injection and, for the ADXL355,
the six orientations. For the INA229, --interactive TC-16 runs the fault injection
alone and --interactive TC-15 the reference measurements alone.

adxl355-pl runs TC-22, the ADXL355 on the external clock and synchronization pulse of
the cubespec-pl bitstream: --elf and --bit load both over JTAG with the CPU in its SD
boot state (xsdb.cfg sd-state), so the timing is that of an SD boot. With --capture it
also stores every frame of steps 5, 9, 11, 12 and 13 on the board and writes them to
capture-tc22-<step>.csv (app/scripts/plot_tc22.py draws them).

Writes to --out: transcript.log (everything the board printed), results.txt (one line
per check: PASS, FAIL or INFO, the test-case step and the measured values) and
environment.txt; then SHA256SUMS. Exit code 0 only if no check failed.

  app/scripts/sensor_bench.py ina229 --elf <zephyr.elf> --shunt 0.015 --max-current 5 \\
      --out docs/verification/evidence/<date>-ina229
  app/scripts/sensor_bench.py adxl355 --elf <zephyr.elf> --interactive \\
      --out docs/verification/evidence/<date>-adxl355
  app/scripts/sensor_bench.py adxl355-pl --elf <zephyr.elf> --bit <pp_te0701.bit> \\
      --out docs/verification/evidence/<date>-adxl355-pl

Test cases: docs/verification/test-cases.md (TC-13 to TC-22).
"""

import argparse
import datetime
import hashlib
import zlib
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time

import serial

from hw_test import XSDB_CFG, find_port, find_xsdb, load

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(APP_DIR)
STANDARD_GRAVITY = 9.80665

# (request in Hz, SPI mode): every SCLK the controller can generate within the
# sensors' 10 MHz limit (SPI_REF_CLK 142.86 MHz / 256 ... / 16)
# The INA229 runs in mode 3: in modes 1 and 2 some writes are lost (docs/known-issues.md)
INA229_SPI_POINTS = [(600000, 3), (1200000, 3), (2300000, 3), (4500000, 3), (9000000, 3)]
# Raw writes to ADC_CONFIG for TC-13.3; 0x0b6a and 0xfb6b were lost in mode 1, the
# last value is the reset default. TC-14 starts with a reset, so nothing is left behind.
INA229_WRITE_PATTERNS = [0x0b6a, 0xfb6b, 0x5555, 0xaaaa, 0x0000, 0xfb68]
ADXL355_SPI_POINTS = [(600000, 0), (1200000, 0), (2300000, 0), (4500000, 0), (9000000, 0)]
DEFAULT_SPI = {'ina': (1200000, 3), 'adxl': (1200000, 0)}  # by shell command
TC19_BUDGET_SPI = (9000000, 0)  # 8.93 MHz, the fastest SCLK within the ADXL355's 10 MHz
PL_DIR = os.path.join(WORKSPACE, '..', 'cubespec-pl')
FROZEN_REPEAT_LIMIT = 8  # fprime-adxl355 Device::FROZEN_REPEAT_LIMIT


class Console:
    """Serial console of the board: every byte is logged; commands wait for a marker."""

    def __init__(self, port, log_path):
        self.serial = serial.Serial(port, 115200, timeout=0.05)
        self.serial.reset_input_buffer()
        self.log = open(log_path, 'wb')
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while not self.stop.is_set():
            data = self.serial.read(4096)
            if data:
                with self.lock:
                    self.buf.extend(data)
                self.log.write(data)
                self.log.flush()

    def mark(self):
        with self.lock:
            return len(self.buf)

    def text(self, since=0):
        with self.lock:
            data = bytes(self.buf[since:])
        return ANSI.sub('', data.decode(errors='replace')).replace('\r', '')

    def wait_for(self, pattern, timeout, since=0):
        """The first complete line after since that matches pattern, or None after timeout
        seconds. A line counts once its newline has arrived, so a result line is never
        read half-received."""
        regex = re.compile(f'(?:{pattern})(?=\n)', re.M)
        deadline = time.time() + timeout
        while True:
            found = regex.search(self.text(since))
            if found or time.time() > deadline:
                return found.group(0) if found else None
            time.sleep(0.05)

    def run(self, line, pattern, timeout=15):
        """Send a shell command; return (matching result line or None, all output)."""
        since = self.mark()
        self.serial.write(line.encode() + b'\r')
        found = self.wait_for(pattern, timeout, since)
        time.sleep(0.1)
        return found, self.text(since)

    def close(self):
        self.stop.set()
        self.thread.join()
        self.serial.close()
        self.log.close()


def fields(line):
    """key=value tokens of a result line"""
    return dict(token.split('=', 1) for token in (line or '').split() if '=' in token)


def number(values, key, default=float('nan')):
    try:
        return float(values[key])
    except (KeyError, ValueError):
        return default


class Results:
    def __init__(self, path):
        self.file = open(path, 'w')
        self.failed = 0
        self.passed = 0

    def _write(self, verdict, step, text):
        line = f'{verdict:<4}  {step:<8}  {text}'
        print(line)
        self.file.write(line + '\n')
        self.file.flush()

    def check(self, step, name, ok, detail=''):
        self._write('PASS' if ok else 'FAIL', step, f'{name}: {detail}' if detail else name)
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def info(self, step, text):
        self._write('INFO', step, text)

    def close(self):
        self._write('DONE', '', f'{self.passed} passed, {self.failed} failed')
        self.file.close()


def ask(prompt):
    """Operator step; returns the typed line (empty to accept)."""
    print()
    return input(f'>>> {prompt} ').strip()


def ask_number(prompt):
    while True:
        text = ask(prompt)
        try:
            return float(text)
        except ValueError:
            print('    a number, please')


def rows(output, prefix):
    """CSV rows (as lists) printed with the given marker"""
    found = []
    for line in output.splitlines():
        if line.startswith(prefix + ','):
            found.append(line.split(','))
    return found


# ---------------------------------------------------------------------------------
# Common: the SPI link
# ---------------------------------------------------------------------------------

def spi_link(con, res, tc, name, points, soak):
    """Identity and soak at every SCLK (TC-13, TC-17)"""
    prefix = name.upper()
    for hz, mode in points:
        line, _ = con.run(f'{name} spi {hz} {mode}', rf'{prefix}_SPI .*')
        spi = fields(line)
        line, _ = con.run(f'{name} soak {soak}', rf'{prefix}_SOAK n=.*', timeout=60 + soak / 500)
        f = fields(line)
        res.check(f'{tc}.2', f'soak {soak} transfers at SCLK {spi.get("sclk_hz", "?")} Hz, mode {mode}',
                  f.get('result') == 'PASS',
                  f'bad_value={f.get("bad_value")} spi_errors={f.get("spi_errors")} '
                  f'bad_lead={f.get("bad_lead", "n/a")} transfer_us={f.get("min_us")}/{f.get("mean_us")}/'
                  f'{f.get("max_us")}')
    hz, mode = DEFAULT_SPI[name]
    con.run(f'{name} spi {hz} {mode}', rf'{prefix}_SPI .*')


def ready(con, res, name, marker, attach):
    if not attach:
        found = con.wait_for(re.escape(marker), 40)
        res.check('boot', f'{name} bench ready ({marker})', found is not None)
        if found is None:
            return False
        time.sleep(1.0)
    line, _ = con.run(f'{name} info', rf'{name.upper()}_INFO .*')
    res.info('boot', line or 'no info line')
    return True


# ---------------------------------------------------------------------------------
# INA229
# ---------------------------------------------------------------------------------

def ina229(con, res, args):
    if not ready(con, res, 'ina', '[INA229_BENCH_READY]', args.attach):
        return

    # TC-13 SPI1 link to the INA229
    line, _ = con.run('ina id', r'INA_ID .*')
    f = fields(line)
    res.check('TC-13.1', 'identity over raw SPI (MANUFACTURER_ID 0x5449, DEVICE_ID die 0x229, lead byte 0)',
              f.get('result') == 'PASS', line or 'no answer')
    spi_link(con, res, 'TC-13', 'ina', INA229_SPI_POINTS, args.soak)
    ina229_writes(con, res)

    # TC-14 through the F Prime manager
    init = f'ina init {args.shunt} {args.max_current}'
    line, _ = con.run(init, r'INA_INIT .*', timeout=20)
    res.check('TC-14.1', f'initialize through the manager port ({init})', fields(line).get('status') == 'OK',
              line or 'no answer')

    line, out = con.run('ina read 20 0', r'INA_READ_DONE .*', timeout=60)
    f = fields(line)
    data = [r for r in rows(out, 'INA_ROW') if len(r) >= 12 and r[2] == 'OK']
    res.check('TC-14.2', '20 readings, all OK', f.get('ok') == '20' and f.get('failures') == '0', line or 'no answer')
    if data:
        valid = {r[3] for r in data}
        res.check('TC-14.3', 'all seven channels valid in mode 15 (valid mask 0x7f)', valid == {'0x7f'},
                  f'masks {sorted(valid)}')
        bus = statistics.mean(float(r[4]) for r in data)
        shunt = statistics.mean(float(r[5]) for r in data)
        temp = statistics.mean(float(r[6]) for r in data)
        current = statistics.mean(float(r[7]) for r in data)
        power = statistics.mean(float(r[8]) for r in data)
        res.check('TC-14.4', 'die temperature plausible (5 to 50 C)', 5.0 <= temp <= 50.0, f'{temp:.3f} C')
        consistent = abs(shunt / args.shunt - current) <= 0.01 * abs(current) + 2 * args.max_current / 2**19
        res.check('TC-14.5', 'current consistent with shunt voltage / shunt resistance', consistent,
                  f'shunt {shunt * 1e3:.6f} mV -> {shunt / args.shunt:.6f} A, reported {current:.6f} A')
        res.check('TC-14.6', 'power consistent with bus voltage x current (data sheet: +/-0.5 % TME)',
                  abs(power - bus * current) <= 0.005 * abs(bus * current) + 3.2 * args.max_current / 2**19 * 2,
                  f'{power:.6f} W vs {bus * current:.6f} W')
        res.info('TC-14', f'mean bus {bus:.6f} V, shunt {shunt * 1e6:.3f} uV, current {current:.6f} A, '
                          f'power {power:.6f} W, temperature {temp:.3f} C')

    line, out = con.run('ina cmd report', r'INA_CMD report .*')
    errors_before = re.findall(r'TLM sensor\.Errors = (\d+)', out)
    res.check('TC-14.7', 'REPORT command: response OK, telemetry printed',
              fields(line).get('response') == 'OK' and 'TLM sensor.Samples' in out and bool(errors_before),
              line or 'no answer')
    line, out = con.run('ina cmd snapshot', r'INA_CMD snapshot .*')
    res.check('TC-14.8', 'READ_SNAPSHOT command: response OK, Measurement telemetry',
              fields(line).get('response') == 'OK' and 'TLM sensor.Measurement' in out, line or 'no answer')
    line, _ = con.run('ina cmd init 0 5', r'INA_CMD init .*')
    res.check('TC-14.9', 'INITIALIZE with a zero shunt: VALIDATION_ERROR', fields(line).get('response') ==
              'VALIDATION_ERROR', line or 'no answer')
    line, out = con.run('ina cmd report', r'INA_CMD report .*')
    errors_after = re.findall(r'TLM sensor\.Errors = (\d+)', out)
    res.check('TC-14.10', 'a rejected argument is not counted as a device error',
              bool(errors_before) and errors_after == errors_before[-1:],
              f'Errors {errors_before[-1:] or "?"} -> {errors_after or "?"}')

    # DIAG_ALRT read-modify-write keeps MEMSTAT (INA-HIL-004)
    line, _ = con.run('ina reg 0x0b', r'INA_REG .*')
    before = int(fields(line).get('value', '0x0'), 16)
    con.run('ina cmd alert 0x8000', r'INA_CMD alert .*')
    line, _ = con.run('ina reg 0x0b', r'INA_REG .*')
    after = int(fields(line).get('value', '0x0'), 16)
    con.run('ina cmd alert 0x0000', r'INA_CMD alert .*')
    res.check('TC-14.11', 'SET_ALERT_CONFIG 0x8000 sets ALATCH and leaves MEMSTAT', (after & 0x8000) != 0 and
              (after & 1) == (before & 1) == 1, f'DIAG_ALRT 0x{before:04x} -> 0x{after:04x}')
    line, _ = con.run('ina cmd reset-acc', r'INA_CMD reset-acc .*')
    res.check('TC-14.12', 'RESET_ACCUMULATORS command: response OK', fields(line).get('response') == 'OK',
              line or 'no answer')

    line, _ = con.run('ina timing 200', r'INA_TIMING .*', timeout=90)
    f = fields(line)
    res.check('TC-14.13', '200 timed reads, none failed', f.get('ok_n') == '200' and f.get('failed_n') == '0',
              line or 'no answer')
    con.run('ina stream start 100 20', r'INA_STREAM_STARTED .*')
    done = con.wait_for(r'INA_STREAM_DONE .*', 30)
    con.run('ina stream stop', r'INA_STREAM_STOPPED .*')
    res.check('TC-14.14', 'rate-group stream: 20 rows at 10 Hz, no failures',
              fields(done).get('rows') == '20' and fields(done).get('failures') == '0', done or 'no answer')

    if args.interactive in ('all', 'TC-15'):
        ina229_reference(con, res, args)
    if args.interactive in ('all', 'TC-16'):
        ina229_faults(con, res, args)


def ina229_write_pass(con, points):
    """Raw ADC_CONFIG writes at each (hz, mode): (all stuck and intact, details)"""
    line, _ = con.run('ina reg 0x01', r'INA_REG .*')
    previous = int(fields(line).get('value', '0x0'), 16)
    bad = []
    for hz, mode in points:
        con.run(f'ina spi {hz} {mode}', r'INA_SPI .*')
        for value in INA229_WRITE_PATTERNS:
            line, _ = con.run(f'ina wreg 0x01 0x{value:04x}', r'INA_WREG .*')
            f = fields(line)
            # write_rx is the previous value when the frame reached the INA229 intact
            intact = f.get('write_rx') == f'00{previous:04x}'
            if f.get('match') != '1' or not intact:
                bad.append(f'{hz}/{mode} 0x{value:04x}: readback {f.get("readback")} write_rx {f.get("write_rx")}')
            if f.get('readback'):
                previous = int(f['readback'], 16)
    return not bad, bad


def ina229_writes(con, res):
    """TC-13.3: register writes reach the INA229 intact (reads alone do not show a wrong SPI mode)"""
    ok, bad = ina229_write_pass(con, INA229_SPI_POINTS)
    res.check('TC-13.3', f'{len(INA229_WRITE_PATTERNS)} raw ADC_CONFIG writes at every SCLK in mode 3: '
              'each read back, write frame intact', ok,
              'all intact' if ok else '; '.join(bad))
    # Record whether the mode 1 defect is still there; it is not a pass criterion
    ok, bad = ina229_write_pass(con, [(1200000, 1)])
    res.info('TC-13.3', f'mode 1 at 1.116 MHz for comparison: {"all writes intact" if ok else "; ".join(bad)}')
    hz, mode = DEFAULT_SPI['ina']
    con.run(f'ina spi {hz} {mode}', r'INA_SPI .*')


def ina229_reference(con, res, args):
    """TC-15: readings against reference instruments"""
    ask('TC-15: apply the reference load. Press Enter when it is steady.')
    line, out = con.run('ina read 50 0', r'INA_READ_DONE .*', timeout=120)
    data = [r for r in rows(out, 'INA_ROW') if len(r) >= 12 and r[2] == 'OK']
    if not data:
        res.check('TC-15', 'readings for the reference comparison', False, line or 'no answer')
        return
    bus = statistics.mean(float(r[4]) for r in data)
    current = statistics.mean(float(r[7]) for r in data)
    temp = statistics.mean(float(r[6]) for r in data)
    ref_bus = ask_number(f'TC-15: reference bus voltage (V) [INA229 {bus:.5f}]:')
    ref_current = ask_number(f'TC-15: reference current (A) [INA229 {current:.6f}]:')
    ref_temp = ask('TC-15: reference temperature near the INA229 (C), or Enter to skip:')
    unc = args.ref_uncertainty / 100.0
    # Data sheet SLYS023A 6.5: VBUS gain error 0.05 %, offset 2.5 mV; shunt gain error
    # 0.05 %, offset 1 uV; plus the shunt tolerance and the reference uncertainty
    bus_limit = 0.0005 * abs(ref_bus) + 0.0025 + unc * abs(ref_bus)
    res.check('TC-15.1', 'bus voltage within data-sheet accuracy + reference uncertainty',
              abs(bus - ref_bus) <= bus_limit, f'{bus:.5f} V vs {ref_bus:.5f} V (limit {bus_limit * 1e3:.2f} mV)')
    current_limit = (0.0005 + args.shunt_tolerance / 100.0 + unc) * abs(ref_current) + 1e-6 / args.shunt
    res.check('TC-15.2', 'current within data-sheet accuracy + shunt tolerance + reference uncertainty',
              abs(current - ref_current) <= current_limit,
              f'{current:.6f} A vs {ref_current:.6f} A (limit {current_limit * 1e3:.3f} mA)')
    if ref_temp:
        limit = 1.0 + 1.0  # data sheet +/-1 C at 25 C, plus the reference and self-heating
        res.check('TC-15.3', 'die temperature within 2 C of the reference', abs(temp - float(ref_temp)) <= limit,
                  f'{temp:.2f} C vs {ref_temp} C')
    if ask('TC-15.4: reverse the load current (or press Enter to skip, "r" when reversed):') == 'r':
        line, out = con.run('ina read 20 0', r'INA_READ_DONE .*', timeout=60)
        data = [r for r in rows(out, 'INA_ROW') if len(r) >= 12 and r[2] == 'OK']
        reversed_current = statistics.mean(float(r[7]) for r in data) if data else float('nan')
        ref = ask_number(f'TC-15.4: reference current, reversed (A) [INA229 {reversed_current:.6f}]:')
        limit = (0.0005 + args.shunt_tolerance / 100.0 + unc) * abs(ref) + 1e-6 / args.shunt
        res.check('TC-15.4', 'reversed current: sign and magnitude', abs(reversed_current - ref) <= limit,
                  f'{reversed_current:.6f} A vs {ref:.6f} A')


def ina229_faults(con, res, args):
    """TC-16: no valid reading from a faulty link, and recovery"""
    ask('TC-16.1: disconnect MISO (Pmod J1 pin 9) from the INA229. Press Enter.')
    line, _ = con.run('ina id', r'INA_ID .*')
    res.check('TC-16.1', 'identity fails with MISO disconnected', fields(line).get('result') == 'FAIL', line)
    line, out = con.run('ina read 3 0', r'INA_READ_DONE .*', timeout=60)
    ok_rows = [r for r in rows(out, 'INA_ROW') if len(r) > 2 and r[2] == 'OK']
    res.check('TC-16.1', 'no valid reading with MISO disconnected', not ok_rows and fields(line).get('ok') == '0',
              line)
    ask('TC-16.2: reconnect MISO. Press Enter.')
    line, out = con.run('ina read 3 0', r'INA_READ_DONE .*', timeout=60)
    res.check('TC-16.2', 'readings recover after reconnection', fields(line).get('ok') == '3',
              f'{line}; recovery event: {"Recovered" in out}')

    ask('TC-16.3: disconnect the INA229 supply (VS). Press Enter.')
    line, out = con.run('ina read 3 0', r'INA_READ_DONE .*', timeout=60)
    ok_rows = [r for r in rows(out, 'INA_ROW') if len(r) > 2 and r[2] == 'OK']
    res.check('TC-16.3', 'no valid reading with the sensor unpowered', not ok_rows, line)
    ask('TC-16.4: reconnect the supply (do not reinitialize). Press Enter.')
    time.sleep(0.5)
    line, out = con.run('ina read 5 0', r'INA_READ_DONE .*', timeout=60)
    data = [r for r in rows(out, 'INA_ROW') if len(r) >= 12 and r[2] == 'OK']
    # After a power loss the INA229 is back in its reset state; fprime-ina229 61ecaea
    # reports its readings as valid, with a wrong current (as-run 2026-10-04)
    res.info('TC-16.4', f'after power returns, without reinitialization: {line}; '
                        f'currents {[r[7] for r in data]}; flagged: {len(data) < 5}')
    line, _ = con.run(f'ina init {args.shunt} {args.max_current}', r'INA_INIT .*', timeout=20)
    line2, _ = con.run('ina read 3 0', r'INA_READ_DONE .*', timeout=60)
    res.check('TC-16.5', 'reinitialization restores valid readings',
              fields(line).get('status') == 'OK' and fields(line2).get('ok') == '3', f'{line}; {line2}')


# ---------------------------------------------------------------------------------
# ADXL355
# ---------------------------------------------------------------------------------

def adxl_read(con, count):
    line, _ = con.run(f'adxl read {count} 0', r'ADXL_READ_DONE .*', timeout=30 + count)
    return fields(line), line


def stream(con, rate, frames, timeout):
    """Trigger frames at rate until the timing thread reports them done; the counts"""
    started, _ = con.run(f'adxl stream start {rate} {frames}', r'ADXL_STREAM_STARTED .*|error.*')
    if started and started.startswith('ADXL_STREAM_STARTED'):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, _ = con.run('adxl stream status', r'ADXL_STREAM .*')
            if fields(status).get('streaming') == '0':
                break
            time.sleep(0.5)
    line, _ = con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    return fields(line), line


def budget_met(f):
    """A 4 kHz stream: every acquisition within the 250 us period, no trigger lost, no bad data"""
    return (number(f, 'acq_max_us', 1e9) < 250 and f.get('missed_ticks') == '0' and f.get('seq_gaps') == '0' and
            f.get('implausible') == '0' and f.get('other') == '0')


def adxl355(con, res, args):
    if not ready(con, res, 'adxl', '[ADXL355_BENCH_READY]', args.attach):
        return

    # TC-17 SPI1 link to the ADXL355
    line, _ = con.run('adxl id', r'ADXL_ID .*')
    res.check('TC-17.1', 'identity over raw SPI (0xAD, 0x1D, 0xED)', fields(line).get('result') == 'PASS', line)
    spi_link(con, res, 'TC-17', 'adxl', ADXL355_SPI_POINTS, args.soak)

    # TC-18 through the F Prime manager
    line, _ = con.run('adxl init 2 125 0', r'ADXL_INIT .*', timeout=20)
    res.check('TC-18.1', 'initialize through the manager port (+/-2 g, 125 Hz, internal clock)',
              fields(line).get('status') == 'OK', line)
    _, out = con.run('adxl temp 3', r'(?:ADXL_TEMP .*\n(?:.*\n)*?){2}ADXL_TEMP .*', timeout=10)
    temps = [number(fields(l), 'celsius') for l in out.splitlines() if l.startswith('ADXL_TEMP ')]
    res.check('TC-18.2', 'temperature plausible (5 to 50 C, uncalibrated)',
              bool(temps) and all(5.0 <= t <= 50.0 for t in temps), f'{temps}')
    f, line = adxl_read(con, 200)
    magnitude = number(f, 'magnitude_g')
    # Data sheet Table 2: sensitivity 235,520..276,480 LSB/g (+/-8 %), 0 g offset +/-75 mg
    # per axis: |a| at rest within 1 g x (1 +/- 0.08) +/- sqrt(3) x 0.075 g
    res.check('TC-18.3', '200 fresh samples; |a| at rest within 0.79..1.21 g',
              f.get('failures') == '0' and 0.79 <= magnitude <= 1.21, line)
    res.info('TC-18', f'noise at 125 Hz ODR: {f.get("std_x_mg")}/{f.get("std_y_mg")}/{f.get("std_z_mg")} mg rms')
    line, _ = con.run('adxl selftest 64', r'ADXL_SELFTEST .*', timeout=60)
    res.check('TC-18.4', 'self-test response within data sheet Table 2 (X, Y 0.1..0.6 g; Z 0.5..3.0 g)',
              fields(line).get('result') == 'PASS', line)
    line, _ = con.run('adxl drdy 20', r'ADXL_DRDY .*', timeout=30)
    res.check('TC-18.5', 'STATUS bits 7:5 read 0 and a STATUS read clears DATA_RDY',
              fields(line).get('result') == 'PASS', line)
    line, _ = con.run('adxl timing 200', r'ADXL_TIMING .*', timeout=90)
    f = fields(line)
    res.check('TC-18.6', '200 timed reads, none failed', f.get('ok_n') == '200' and f.get('failed_n') == '0', line)
    line, out = con.run('adxl cmd snapshot', r'ADXL_CMD snapshot .*')
    res.check('TC-18.7', 'READ_SNAPSHOT command: response OK, acceleration telemetry',
              fields(line).get('response') == 'OK' and 'TLM sensor.AccelerationZ' in out, line)
    line, _ = con.run('adxl cmd range 16', r'ADXL_CMD .*|error.*|usage.*|manager:.*')
    res.check('TC-18.8', 'an invalid range is refused', 'response=OK' not in (line or ''), line)
    line, out = con.run('adxl cmd app-report', r'ADXL_CMD app-report .*')
    res.check('TC-18.9', 'application REPORT: sensor count 1', fields(line).get('response') == 'OK' and
              'TLM app.SensorCount = 1' in out, line)

    # Without the 1.024 MHz external clock, a synchronized initialization gives no data
    line, _ = con.run('adxl cmd init-synced 2 1000 0', r'ADXL_CMD init-synced .*', timeout=20)
    res.info('TC-18.10', f'INITIALIZE_SYNCED without an external clock: {line}')
    f, line = adxl_read(con, 1)
    res.check('TC-18.10', 'no fresh sample without the external clock (STALE_DATA)', f.get('ok') == '0', line)

    # TC-19 SynchronizedApplication, triggered by the timing thread
    con.run('adxl init 2 1000 0', r'ADXL_INIT .*', timeout=20)
    f, line = stream(con, 500, 2500, 30)
    res.check('TC-19.1', 'ODR 1 kHz, triggered at 500 Hz: 2500 complete frames, no stale or skipped data',
              f.get('frames') == '2500' and f.get('complete') == '2500' and f.get('stale') == '0' and
              f.get('seq_gaps') == '0' and f.get('missed_ticks') == '0', line)
    f, line = stream(con, 2000, 4000, 30)
    frames = number(f, 'frames', 0)
    stale_share = number(f, 'stale', 0) / frames if frames else float('nan')
    res.check('TC-19.2', 'ODR 1 kHz, triggered at 2 kHz: about half the frames stale, none implausible, '
              'no missed tick', 0.35 <= stale_share <= 0.65 and f.get('implausible') == '0' and
              f.get('other') == '0' and f.get('missed_ticks') == '0', f'stale share {stale_share:.3f}; {line}')
    con.run('adxl init 2 4000 0', r'ADXL_INIT .*', timeout=20)
    f, line = stream(con, 2000, 10000, 30)
    res.check('TC-19.3', 'ODR 4 kHz, triggered at 2 kHz: 10000 complete frames',
              f.get('complete') == '10000' and f.get('stale') == '0' and f.get('seq_gaps') == '0', line)

    # The 250 us budget at the SCLK closest to flight (about 10 MHz)
    hz, mode = TC19_BUDGET_SPI
    line, _ = con.run(f'adxl spi {hz} {mode}', r'ADXL_SPI .*')
    sclk = fields(line).get('sclk_hz', '?')
    f, line = stream(con, 4000, 20000, 30)
    # Triggered at the output data rate, the timer and the sensor's own oscillator drift
    # against each other, so an occasional stale frame is expected; it is recorded
    res.check('TC-19.4', f'ODR 4 kHz, triggered at 4 kHz, SCLK {sclk} Hz: acquisition within the 250 us period, '
              'no trigger lost, nothing implausible', budget_met(f), line)
    frames = number(f, 'frames', 0)
    res.info('TC-19.4', f'stale frames at trigger rate = ODR (clock drift): {f.get("stale")} of {f.get("frames")} '
                        f'({(number(f, "stale", 0) / frames * 100) if frames else float("nan"):.3f} %)')
    # Every second trigger finds no new sample: the stale and recovery edges, with their
    # events and telemetry on the acquisition thread, must fit in the period as well
    con.run('adxl init 2 2000 0', r'ADXL_INIT .*', timeout=20)
    f, line = stream(con, 4000, 20000, 30)
    frames = number(f, 'frames', 0)
    stale_share = number(f, 'stale', 0) / frames if frames else float('nan')
    res.check('TC-19.5', f'ODR 2 kHz, triggered at 4 kHz, SCLK {sclk} Hz: about half the frames stale, '
              'acquisition within the 250 us period, no trigger lost, nothing implausible',
              0.35 <= stale_share <= 0.65 and budget_met(f), f'stale share {stale_share:.3f}; {line}')
    hz, mode = DEFAULT_SPI['adxl']
    con.run(f'adxl spi {hz} {mode}', r'ADXL_SPI .*')
    con.run('adxl init 2 125 0', r'ADXL_INIT .*', timeout=20)

    if args.interactive:
        adxl355_orientations(con, res)
        adxl355_faults(con, res)


ORIENTATIONS = [('+Z', 2, 1), ('-Z', 2, -1), ('+X', 0, 1), ('-X', 0, -1), ('+Y', 1, 1), ('-Y', 1, -1)]


def adxl355_orientations(con, res):
    """TC-20: each axis along gravity, both ways"""
    means = {}
    for label, axis, sign in ORIENTATIONS:
        ask(f'TC-20: rest the sensor board with its {label} axis pointing up. Press Enter.')
        time.sleep(1.0)
        f, line = adxl_read(con, 200)
        m = [number(f, 'mean_x_g'), number(f, 'mean_y_g'), number(f, 'mean_z_g')]
        means[label] = m
        others = [abs(m[i]) for i in range(3) if i != axis]
        # Data sheet Table 2: sensitivity +/-8 %, 0 g offset +/-75 mg, cross-axis 1 %;
        # plus up to about 5 degrees of placement error
        res.check('TC-20.1', f'{label} up: {label[1]} axis reads {sign:+d} g (0.83..1.17 g), others below 0.2 g',
                  f.get('failures') == '0' and 0.83 <= sign * m[axis] <= 1.17 and max(others) < 0.2,
                  f'x {m[0]:+.4f} y {m[1]:+.4f} z {m[2]:+.4f} g')
    for name, axis in (('X', 0), ('Y', 1), ('Z', 2)):
        up, down = means[f'+{name}'][axis], means[f'-{name}'][axis]
        offset = (up + down) / 2
        sensitivity = (up - down) / 2
        res.check('TC-20.2', f'{name}: 0 g offset within +/-75 mg and sensitivity within +/-8 % (Table 2)',
                  abs(offset) <= 0.075 and 0.92 <= sensitivity <= 1.08,
                  f'offset {offset * 1e3:+.2f} mg, sensitivity {sensitivity:.4f} of nominal')


def adxl355_faults(con, res):
    """TC-21: a faulty link gives no valid sample or frame, and recovers"""
    ask('TC-21.1: rest the board, then disconnect MISO (Pmod J1 pin 9) from the ADXL355. Press Enter.')
    line, _ = con.run('adxl id', r'ADXL_ID .*')
    res.check('TC-21.1', 'identity fails with MISO disconnected', fields(line).get('result') == 'FAIL', line)
    f, line = adxl_read(con, 3)
    res.check('TC-21.1', 'no valid sample with MISO disconnected', f.get('ok') == '0', line)
    f, line = stream(con, 50, 50, 10)
    res.check('TC-21.2', 'frames with MISO disconnected are partial (no valid sample)',
              f.get('complete') == '0' and number(f, 'partial', 0) > 0, line)
    ask('TC-21.3: reconnect MISO. Press Enter.')
    f, line = stream(con, 50, 50, 10)
    res.check('TC-21.3', 'frames recover after reconnection', f.get('complete') == '50', line)
    ask('TC-21.4: disconnect CS (Pmod J1 pin 7) from the ADXL355. Press Enter.')
    f, line = adxl_read(con, 3)
    res.check('TC-21.4', 'no valid sample with CS disconnected', f.get('ok') == '0', line)
    ask('TC-21.5: reconnect CS. Press Enter.')
    f, line = adxl_read(con, 3)
    res.check('TC-21.5', 'samples recover after reconnection', f.get('ok') == '3', line)


# ---------------------------------------------------------------------------------
# ADXL355 on the PL's external clock and synchronization pulse (TC-22)
# ---------------------------------------------------------------------------------

def load_pl(xsdb, elf, bit, log_path):
    """JTAG load of the image and the bitstream, CPU in the SD boot state. A download now
    and then fails with "OCM is not enabled"; it is retried."""
    with open(log_path, 'w') as log:
        for attempt in range(1, 4):
            result = subprocess.run(['timeout', '180', xsdb, XSDB_CFG, elf, bit, 'sd-state'],
                                    capture_output=True, text=True)
            log.write(f'--- attempt {attempt}: exit {result.returncode}\n{result.stdout}{result.stderr}\n')
            if result.returncode == 0:
                return attempt
    return 0


def pl_stream(con, frames, timeout, command='start-pl'):
    """Frames triggered by the PL's sync interrupt (or the timer: command='start 4000')"""
    started, _ = con.run(f'adxl stream {command} {frames}', r'ADXL_STREAM_STARTED .*|error.*')
    if started and started.startswith('ADXL_STREAM_STARTED'):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, _ = con.run('adxl stream status', r'ADXL_STREAM .*')
            if fields(status).get('streaming') == '0':
                break
            time.sleep(0.5)
    line, _ = con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    return fields(line), line


def clean_stream(f, frames):
    """Every frame complete, none stale, frozen or implausible, nothing lost, within the period"""
    return (f.get('frames') == str(frames) and f.get('complete') == str(frames) and f.get('stale') == '0' and
            f.get('frozen') == '0' and f.get('implausible') == '0' and f.get('other') == '0' and
            f.get('seq_gaps') == '0' and f.get('missed_ticks') == '0' and f.get('pl_overruns', '0') == '0' and
            number(f, 'acq_max_us', 1e9) < 250)


def magnitudes_plausible(f):
    """|a| of every valid sample within the data sheet's at-rest band (TC-18.3), and the
    spread of a sensor at rest: a corrupted sample lies far outside either"""
    low, high = number(f, 'mag_min_g'), number(f, 'mag_max_g')
    return 0.79 <= low <= high <= 1.21 and (high - low) < 0.020


def phase(con, res, step, name):
    line, _ = con.run('adxl phase 400', r'ADXL_PHASE .*', timeout=15)
    f = fields(line)
    res.check(step, name, f.get('result') == 'PASS', line)
    return (number(f, 'phase_lo_us'), number(f, 'phase_hi_us')) if f.get('result') == 'PASS' else None


def restart_timing(con, settle=1.0, pause=0.1):
    """Stop the clock and the pulses and start them again in the flight order, then wait
    more than one filter group delay"""
    con.run('pl sync off', r'PL_SYNC .*')
    con.run('pl clk off', r'PL_CLK .*')
    time.sleep(pause)
    con.run('pl clk on', r'PL_CLK .*')
    con.run('pl sync on 256 8', r'PL_SYNC .*')
    time.sleep(settle)


CAPTURE_FIELDS = 'index,stream,sequence,sync_us,sync_ticks,start_ns,end_ns,status,valid,raw_x,raw_y,raw_z,crc32'


def capture_on(con, frames):
    line, _ = con.run(f'adxl capture on {frames}', r'ADXL_CAPTURE .*|error.*|usage.*')
    return fields(line).get('armed') == '1'


def capture_dump(con, res, step, out_dir):
    """Print the stored frames, check each line's CRC and the indices, write the CSV.
    The console carries about 11 kB/s, so 20000 frames take about 2.5 minutes."""
    status, _ = con.run('adxl capture status', r'ADXL_CAPTURE .*')
    count = int(fields(status).get('count', '0'))
    since = con.mark()
    con.serial.write(b'adxl capture dump\r')
    end = con.wait_for(r'ADXL_CAPTURE_END .*', 60 + count * 0.02, since)
    text = con.text(since)
    con.run('adxl capture off', r'ADXL_CAPTURE .*')
    rows, bad = [], 0
    for line in text.splitlines():
        m = re.search(r'ADXL_CAP,(.*),([0-9a-f]{8})$', line)
        if not m:
            continue
        body = 'ADXL_CAP,' + m.group(1)
        if zlib.crc32(body.encode()) != int(m.group(2), 16):
            bad += 1
            continue
        rows.append(m.group(1) + ',' + m.group(2))
    indices = [int(r.split(',', 1)[0]) for r in rows]
    complete = indices == list(range(count))
    name = f'capture-tc22-{step.split(".")[1]}.csv'
    with open(os.path.join(out_dir, name), 'w') as f:
        f.write(CAPTURE_FIELDS + '\n')
        f.write('\n'.join(rows) + ('\n' if rows else ''))
    res.check(step, f'capture: {count} frames to {name}, every line intact and none missing',
              end is not None and bad == 0 and complete and count > 0,
              f'{len(rows)} lines with a good CRC, {bad} damaged, {count - len(rows) - bad} missing')


def adxl355_pl(con, res, args):
    if not ready(con, res, 'adxl', '[ADXL355_BENCH_READY]', args.attach):
        return

    # TC-22.1 The bitstream: identity, map, and the build it came from
    line, _ = con.run('pl info', r'PL_INFO .*')
    f = fields(line)
    res.check('TC-22.1', 'cubespec-pl identifies itself (sysctrl magic, map, slots, time base, acc)',
              f.get('result') == 'PASS', line)
    head = git(PL_DIR, 'rev-parse', '--short=8', 'HEAD')
    res.check('TC-22.1', f'bitstream built from the checked-out cubespec-pl ({head}), clean',
              f.get('git') == f'0x{head}' and f.get('dirty') == '0', f'git={f.get("git")} dirty={f.get("dirty")}')
    line, _ = con.run('adxl id', r'ADXL_ID .*')
    res.check('TC-22.1', 'ADXL355 identity over raw SPI', fields(line).get('result') == 'PASS', line)

    # TC-22.2 The PL time base runs from the PS clock's crystal
    first, _ = con.run('pl time', r'PL_TIME .*')
    time.sleep(10)
    second, _ = con.run('pl time', r'PL_TIME .*')
    a, b = fields(first), fields(second)
    try:
        pl = int(b['pl_us']) - int(a['pl_us'])
        ps = (int(b['ps_us_before']) + int(b['ps_us_after']) - int(a['ps_us_before']) - int(a['ps_us_after'])) / 2
        ppm = 1e6 * (pl - ps) / ps
    except (KeyError, ValueError, ZeroDivisionError):
        pl, ps, ppm = 0, 0, float('nan')
    res.check('TC-22.2', 'PL time base against the PS clock over 10 s within 1 ppm', abs(ppm) <= 1.0,
              f'PL {pl} us, PS {ps:.0f} us: {ppm:+.2f} ppm')

    # TC-22.3 Start-up in the order of the ACC board design notes: initialize the sensor
    # with EXT_CLK and EXT_SYNC set (INT2 and DRDY become inputs), start the clock, start
    # the pulses, enable acquisition after more than one filter group delay
    hz, mode = TC19_BUDGET_SPI
    line, _ = con.run(f'adxl spi {hz} {mode}', r'ADXL_SPI .*')
    sclk = fields(line).get('sclk_hz', '?')
    line, _ = con.run('adxl cmd app-init 2 4000 0', r'ADXL_CMD app-init response=\w+', timeout=20)
    res.check('TC-22.3', 'INITIALIZE_ALL (+/-2 g, 4 kHz, HPF off, external clock and sync) before the clock runs',
              (line or '').endswith('=OK'), line)
    clk, _ = con.run('pl clk on', r'PL_CLK .*')
    sync, _ = con.run('pl sync on 256 8', r'PL_SYNC .*')
    delay, _ = con.run('pl delay 50', r'PL_DELAY .*')
    res.check('TC-22.3', 'EXT_CLK and SYNC (256 clocks = 250 us, 8 clocks wide) running; interrupt 50 us after '
              'the sync instant', fields(clk).get('status') == '0x1' and fields(sync).get('period_us') == '250' and
              fields(delay).get('us') == '50', f'{clk}; {sync}; {delay}')
    time.sleep(0.5)

    # TC-22.4 DATA_RDY clears on a STATUS read in the flight synchronization mode
    line, _ = con.run('adxl drdy 200', r'ADXL_DRDY .*', timeout=30)
    res.check('TC-22.4', 'with EXT_CLK and SYNC: STATUS bits 7:5 read 0 and a STATUS read clears DATA_RDY',
              fields(line).get('result') == 'PASS', line)

    # TC-22.5 4 kHz frames on the PL's sync interrupt
    capturing = args.capture and capture_on(con, 20000)
    f, line = pl_stream(con, 20000, 30)
    res.check('TC-22.5', f'20000 frames on the PL sync interrupt, SCLK {sclk} Hz: all complete, none stale, '
              'frozen or implausible, no trigger lost, acquisition within the 250 us period', clean_stream(f, 20000),
              line)
    res.check('TC-22.5', '|a| of every sample within 0.79..1.21 g and spread below 20 mg (no corrupted first '
              'samples)', magnitudes_plausible(f), f'{f.get("mag_min_g")} to {f.get("mag_max_g")} g')
    if capturing:
        capture_dump(con, res, 'TC-22.5', args.out)

    # TC-22.6 Frame timestamps are sync instants of the PL time base
    con.run('adxl tlm off', r'ADXL_TLM .*')
    since = con.mark()
    con.run('adxl stream start-pl 12 1', r'ADXL_STREAM_STARTED .*')
    time.sleep(1.0)
    con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    out = con.text(since)
    times = [int(r[2]) for r in rows(out, 'ADXL_FRAME') if len(r) > 2 and r[2].isdigit()]
    steps = sorted(set(b - a for a, b in zip(times, times[1:])))
    # The console printer skips frames while it prints: steps are whole sync periods
    res.check('TC-22.6', 'printed frames: sync times on the 250 us grid of the PL time base',
              len(times) >= 10 and all(st > 0 and st % 250 == 0 for st in steps), f'{len(times)} frames, steps {steps}')

    # TC-22.7 The sensor follows the pulses: where DATA_RDY sets in the period stays the
    # same when the clock and pulses restart, although each restart moves the pulse train
    # against the sensor's own sample timing
    phases = []
    p = phase(con, res, 'TC-22.7', 'phase of DATA_RDY in the SYNC period')
    if p:
        phases.append(p)
    for k in range(3):
        restart_timing(con, pause=0.1 + 0.037 * k)
        p = phase(con, res, 'TC-22.7', f'phase after restart {k + 1} of the clock and pulses')
        if p:
            phases.append(p)
        f, line = pl_stream(con, 4000, 10)
        res.check('TC-22.7', f'after restart {k + 1}: 4000 clean frames, |a| plausible',
                  clean_stream(f, 4000) and magnitudes_plausible(f), line)
    # Unwrap next to the first measurement, then intersect the intervals
    unwrapped = []
    for lo, hi in phases:
        while lo - phases[0][0] > 125:
            lo, hi = lo - 250, hi - 250
        while phases[0][0] - lo > 125:
            lo, hi = lo + 250, hi + 250
        unwrapped.append((lo, hi))
    low = max(lo for lo, _ in unwrapped) if unwrapped else float('nan')
    high = min(hi for _, hi in unwrapped) if unwrapped else float('nan')
    res.check('TC-22.7', 'DATA_RDY phase the same before and after every restart (intervals overlap)',
              len(unwrapped) == 4 and low <= high,
              f'{[f"{lo:.3f}..{hi:.3f}" for lo, hi in unwrapped]} us; common {low:.3f}..{high:.3f} us')

    # TC-22.8 How soon after the sync instant the new sample can be read
    for us in (2, 5, 10, 20, 30):
        con.run(f'pl delay {us}', r'PL_DELAY .*')
        f, line = pl_stream(con, 4000, 10)
        res.check('TC-22.8', f'interrupt {us} us after the sync instant: 4000 clean frames', clean_stream(f, 4000),
                  line)
    con.run('pl delay 50', r'PL_DELAY .*')

    # TC-22.9 The clock stops with a sample unread: the sensor freezes with DATA_RDY set
    # (a STATUS read no longer clears it), and the library reports FROZEN_DATA after
    # FROZEN_REPEAT_LIMIT repeats; the timer keeps triggering, as a broken clock line would
    con.run('pl sync off', r'PL_SYNC .*')
    con.run('pl clk off', r'PL_CLK .*')
    time.sleep(0.1)
    line, _ = con.run('adxl drdy 50', r'ADXL_DRDY .*', timeout=30)
    f = fields(line)
    res.check('TC-22.9', 'without EXT_CLK, DATA_RDY stays set: no STATUS read clears it',
              f.get('ready_first') == '50' and f.get('cleared_second') == '0', line)
    capturing = args.capture and capture_on(con, 100)
    f, line = pl_stream(con, 100, 10, command='start 4000')
    if capturing:
        capture_dump(con, res, 'TC-22.9', args.out)
    res.check('TC-22.9', f'timer-triggered frames: the first {FROZEN_REPEAT_LIMIT} complete (the frozen sample and '
              'its repeats up to the limit), then every frame FROZEN_DATA',
              f.get('complete') == str(FROZEN_REPEAT_LIMIT) and f.get('frozen') == str(100 - FROZEN_REPEAT_LIMIT) and
              f.get('stale') == '0' and f.get('implausible') == '0' and f.get('other') == '0', line)

    # TC-22.10 The clock returns: fresh samples again, without reinitialization
    con.run('pl clk on', r'PL_CLK .*')
    con.run('pl sync on 256 8', r'PL_SYNC .*')
    time.sleep(1.0)
    line, _ = con.run('adxl drdy 200', r'ADXL_DRDY .*', timeout=30)
    res.check('TC-22.10', 'DATA_RDY clears on a STATUS read again', fields(line).get('result') == 'PASS', line)
    f, line = pl_stream(con, 4000, 10)
    res.check('TC-22.10', '4000 clean frames on the PL sync interrupt, |a| plausible',
              clean_stream(f, 4000) and magnitudes_plausible(f), line)

    # TC-22.11 The clock stops during timer-triggered acquisition: whether the sensor
    # freezes with DATA_RDY set or clear depends on where in the period the clock stops;
    # either way no frame after it is complete, only stale or frozen
    capturing = args.capture and capture_on(con, 8000)
    con.run('adxl stream start 4000 8000', r'ADXL_STREAM_STARTED .*|error.*')
    time.sleep(0.5)
    con.run('pl clk off', r'PL_CLK .*')
    deadline = time.time() + 10
    while time.time() < deadline:
        status, _ = con.run('adxl stream status', r'ADXL_STREAM .*')
        if fields(status).get('streaming') == '0':
            break
        time.sleep(0.5)
    line, _ = con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    f = fields(line)
    if capturing:
        capture_dump(con, res, 'TC-22.11', args.out)
    partial = number(f, 'partial', -1)
    res.check('TC-22.11', 'clock stopped during a timer-triggered stream: frames after it partial, each stale or '
              'frozen, none implausible', partial > 0 and partial == number(f, 'stale', 0) + number(f, 'frozen', 0)
              and f.get('implausible') == '0' and f.get('other') == '0', line)

    # TC-22.12 The pulses stop during PL-triggered acquisition: no more triggers, the
    # waits time out, and the frames before are complete
    con.run('pl clk on', r'PL_CLK .*')
    con.run('pl sync on 256 8', r'PL_SYNC .*')
    time.sleep(1.0)
    capturing = args.capture and capture_on(con, 20000)
    con.run('adxl stream start-pl 20000', r'ADXL_STREAM_STARTED .*|error.*')
    time.sleep(0.5)
    con.run('pl sync off', r'PL_SYNC .*')
    time.sleep(1.0)
    line, _ = con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    f = fields(line)
    if capturing:
        capture_dump(con, res, 'TC-22.12', args.out)
    res.check('TC-22.12', 'pulses stopped during a PL-triggered stream: triggers stop, event waits time out, '
              'every frame before complete', 0 < number(f, 'frames', 0) < 20000 and
              number(f, 'pl_timeouts', 0) >= 5 and f.get('complete') == f.get('frames') and
              f.get('implausible') == '0', line)

    # TC-22.13 Phase scan (characterization, no pass criterion): the interrupt late in
    # the period, so the read starts around the next sync instant. Before the sensor
    # sets DATA_RDY for that instant the read finds the sample of the previous one,
    # already read, and the frame is stale; after it, fresh. With --capture each
    # frame's read time is known, which places that step to a fraction of a microsecond.
    con.run('pl sync on 256 8', r'PL_SYNC .*')
    time.sleep(1.0)
    capturing = args.capture and capture_on(con, 26 * 400)
    for us in range(224, 250):
        con.run(f'pl delay {us}', r'PL_DELAY .*')
        f, line = pl_stream(con, 400, 10)
        frames = number(f, 'frames', 0)
        res.info('TC-22.13', f'interrupt {us} us after the sync instant: stale share '
                             f'{number(f, "stale", 0) / frames if frames else float("nan"):.3f}; {line}')
    con.run('pl delay 50', r'PL_DELAY .*')
    if capturing:
        capture_dump(con, res, 'TC-22.13', args.out)

    # Leave the bench as the other test cases expect it: internal clock, default SCLK
    con.run('pl sync off', r'PL_SYNC .*')
    con.run('pl clk off', r'PL_CLK .*')
    hz, mode = DEFAULT_SPI['adxl']
    con.run(f'adxl spi {hz} {mode}', r'ADXL_SPI .*')
    line, _ = con.run('adxl init 2 125 0', r'ADXL_INIT .*', timeout=20)
    res.info('end', f'internal clock restored: {line}')


# ---------------------------------------------------------------------------------

def git(path, *command):
    result = subprocess.run(['git', '-C', path, *command], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def environment(path, args):
    lib = os.path.join(WORKSPACE, '..', 'fprime-ina229' if args.sensor == 'ina229' else 'fprime-adxl355')
    lines = [
        f'date: {datetime.datetime.now().astimezone().isoformat(timespec="seconds")}',
        f'host: {platform.node()} {platform.platform()}',
        f'command: {" ".join(sys.argv)}',
        f'app: {git(APP_DIR, "describe", "--always", "--dirty", "--abbrev=12")}',
        f'{os.path.basename(lib)}: {git(lib, "describe", "--always", "--dirty", "--abbrev=12")}',
        f'zephyr: {git(os.path.join(WORKSPACE, "zephyr"), "describe", "--tags", "--always", "--dirty")}',
        f'fprime: {git(os.path.join(WORKSPACE, "modules/fprime/fprime"), "describe", "--tags", "--always")}',
        f'fprime-zephyr: {git(os.path.join(WORKSPACE, "modules/fprime/fprime-zephyr"), "rev-parse", "--short", "HEAD")}',
    ]
    if args.elf:
        lines.append(f'zephyr.elf: {os.path.abspath(args.elf)}')
        lines.append(f'zephyr.elf sha256: {sha256(args.elf)}')
    if args.sensor == 'adxl355-pl':
        lines.append(f'cubespec-pl: {git(PL_DIR, "describe", "--always", "--dirty", "--abbrev=12")}')
        if args.bit:
            lines.append(f'bitstream: {os.path.abspath(args.bit)}')
            lines.append(f'bitstream sha256: {sha256(args.bit)}')
        lines.append('load: xsdb.cfg <elf> <bit> sd-state (L2 cache on, ACTLR 0x41, as after an SD boot)')
    if args.sensor == 'ina229':
        lines.append(f'shunt: {args.shunt} ohm, max current {args.max_current} A, '
                     f'shunt tolerance {args.shunt_tolerance} %')
    lines.append(f'reference uncertainty: {args.ref_uncertainty} %')
    lines.append(f'soak transfers per point: {args.soak}')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sensor', choices=['ina229', 'adxl355', 'adxl355-pl'])
    boot = parser.add_mutually_exclusive_group(required=True)
    boot.add_argument('--elf', help='load this zephyr.elf over JTAG')
    boot.add_argument('--sd-boot', action='store_true', help='reset and boot the image on the SD card')
    boot.add_argument('--attach', action='store_true', help='use the image the board is already running')
    parser.add_argument('--out', required=True, help='directory for the evidence (created)')
    parser.add_argument('--interactive', nargs='?', const='all', choices=['all', 'TC-15', 'TC-16'],
                        help='also run the operator steps (INA229: all, or only TC-15 or TC-16)')
    parser.add_argument('--soak', type=int, default=20000, help='transfers per SPI clock (default 20000)')
    parser.add_argument('--shunt', type=float, help='INA229: shunt resistance in ohm')
    parser.add_argument('--max-current', type=float, help='INA229: expected maximum current in A')
    parser.add_argument('--shunt-tolerance', type=float, default=1.0, help='INA229: shunt tolerance in %%')
    parser.add_argument('--ref-uncertainty', type=float, default=0.1,
                        help='reference instrument uncertainty in %% of reading (default 0.1)')
    parser.add_argument('--bit', help='adxl355-pl: the cubespec-pl bitstream to load with --elf')
    parser.add_argument('--capture', action='store_true',
                        help='adxl355-pl: store every frame of steps 5, 9, 11, 12 and 13 and write them as CSV')
    parser.add_argument('--port', help='UART device')
    parser.add_argument('--xsdb', help='path to xsdb')
    args = parser.parse_args()
    if args.sensor == 'ina229' and (args.shunt is None or args.max_current is None):
        parser.error('ina229 needs --shunt and --max-current')
    if args.sensor == 'adxl355-pl' and args.elf and not args.bit:
        parser.error('adxl355-pl with --elf needs --bit')

    os.makedirs(args.out, exist_ok=True)
    environment(os.path.join(args.out, 'environment.txt'), args)
    con = Console(find_port(args.port), os.path.join(args.out, 'transcript.log'))
    res = Results(os.path.join(args.out, 'results.txt'))
    try:
        if args.elf and args.sensor == 'adxl355-pl':
            attempt = load_pl(find_xsdb(args.xsdb), args.elf, args.bit, os.path.join(args.out, 'load.log'))
            res.check('boot', 'load the image and the bitstream over JTAG, CPU in the SD boot state',
                      attempt > 0, f'attempt {attempt}' if attempt else 'see load.log')
            if not attempt:
                return 1
        elif args.elf:
            if not load(find_xsdb(args.xsdb), args.elf):
                res.check('boot', f'load {args.elf} over JTAG', False)
                return 1
        elif args.sd_boot:
            subprocess.run(['timeout', '60', find_xsdb(args.xsdb), '-eval',
                            'connect; targets -set -nocase -filter {name =~ "APU*"}; rst -system; disconnect'],
                           capture_output=True)
        else:
            con.serial.write(b'\r')
        if args.sensor == 'ina229':
            ina229(con, res, args)
        elif args.sensor == 'adxl355-pl':
            adxl355_pl(con, res, args)
        else:
            adxl355(con, res, args)
    finally:
        res.close()
        con.close()
        names = sorted(n for n in os.listdir(args.out) if n != 'SHA256SUMS')
        with open(os.path.join(args.out, 'SHA256SUMS'), 'w') as sums:
            for name in names:
                with open(os.path.join(args.out, name), 'rb') as f:
                    sums.write(f'{hashlib.sha256(f.read()).hexdigest()}  {name}\n')
    return 1 if res.failed else 0


if __name__ == '__main__':
    sys.exit(main())
