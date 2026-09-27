#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Hardware tests of the INA229 and ADXL355 benches on the TE0715 (SPI1 on Pmod J1).

The board runs apps/fprime_ina229_bench or apps/fprime_adxl355_bench. This script loads
the image over JTAG (--elf), resets the board so it boots from the SD card (--sd-boot),
or uses a board that already runs it (--attach), waits for the ready marker and runs
the automated checks over the serial shell. With --interactive it also runs the steps
that need the operator: reference measurements, fault injection and, for the ADXL355,
the six orientations.

Writes to --out: transcript.log (everything the board printed), results.txt (one line
per check: PASS, FAIL or INFO, the test-case step and the measured values) and
environment.txt; then SHA256SUMS. Exit code 0 only if no check failed.

  app/scripts/sensor_bench.py ina229 --elf <zephyr.elf> --shunt 0.015 --max-current 5 \\
      --out docs/verification/evidence/<date>-ina229
  app/scripts/sensor_bench.py adxl355 --elf <zephyr.elf> --interactive \\
      --out docs/verification/evidence/<date>-adxl355

Test cases: docs/verification/test-cases.md (TC-13 to TC-21).
"""

import argparse
import datetime
import hashlib
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
INA229_SPI_POINTS = [(600000, 1), (1200000, 1), (2300000, 1), (4500000, 1), (9000000, 1), (1200000, 2)]
ADXL355_SPI_POINTS = [(600000, 0), (1200000, 0), (2300000, 0), (4500000, 0), (9000000, 0)]
DEFAULT_SPI = {'ina': (1200000, 1), 'adxl': (1200000, 0)}  # by shell command


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
        """The first line after since that matches pattern, or None after timeout seconds."""
        regex = re.compile(pattern, re.M)
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

    if args.interactive:
        ina229_reference(con, res, args)
        ina229_faults(con, res, args)


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
    # After a power loss the INA229 is back in its reset state (SHUNT_CAL 0), so any
    # reading that is reported valid carries a current and power of 0
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
    since = con.mark()
    started, _ = con.run(f'adxl stream start {rate} {frames}', r'ADXL_STREAM_STARTED .*|error.*')
    if started and started.startswith('ADXL_STREAM_STARTED'):
        con.wait_for(r'ADXL_STREAM_DONE .*', timeout, since)
    line, _ = con.run('adxl stream stop', r'ADXL_STREAM_STOPPED .*')
    return fields(line), line


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
    res.check('TC-19.2', 'ODR 1 kHz, triggered at 2 kHz: about half the frames stale, none implausible',
              0.35 <= stale_share <= 0.65 and f.get('implausible') == '0' and f.get('other') == '0',
              f'stale share {stale_share:.3f}; {line}')
    con.run('adxl init 2 4000 0', r'ADXL_INIT .*', timeout=20)
    f, line = stream(con, 2000, 10000, 30)
    res.check('TC-19.3', 'ODR 4 kHz, triggered at 2 kHz: 10000 complete frames',
              f.get('complete') == '10000' and f.get('stale') == '0' and f.get('seq_gaps') == '0', line)
    f, line = stream(con, 4000, 20000, 30)
    res.check('TC-19.4', 'ODR 4 kHz, triggered at 4 kHz: acquisition within the 250 us period, no trigger lost',
              number(f, 'acq_max_us', 1e9) < 250 and f.get('missed_ticks') == '0' and f.get('seq_gaps') == '0',
              line)
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

def git(path, *command):
    result = subprocess.run(['git', '-C', path, *command], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


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
        with open(args.elf, 'rb') as f:
            lines.append(f'zephyr.elf sha256: {hashlib.sha256(f.read()).hexdigest()}')
    if args.sensor == 'ina229':
        lines.append(f'shunt: {args.shunt} ohm, max current {args.max_current} A, '
                     f'shunt tolerance {args.shunt_tolerance} %')
    lines.append(f'reference uncertainty: {args.ref_uncertainty} %')
    lines.append(f'soak transfers per point: {args.soak}')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sensor', choices=['ina229', 'adxl355'])
    boot = parser.add_mutually_exclusive_group(required=True)
    boot.add_argument('--elf', help='load this zephyr.elf over JTAG')
    boot.add_argument('--sd-boot', action='store_true', help='reset and boot the image on the SD card')
    boot.add_argument('--attach', action='store_true', help='use the image the board is already running')
    parser.add_argument('--out', required=True, help='directory for the evidence (created)')
    parser.add_argument('--interactive', action='store_true', help='also run the operator steps')
    parser.add_argument('--soak', type=int, default=20000, help='transfers per SPI clock (default 20000)')
    parser.add_argument('--shunt', type=float, help='INA229: shunt resistance in ohm')
    parser.add_argument('--max-current', type=float, help='INA229: expected maximum current in A')
    parser.add_argument('--shunt-tolerance', type=float, default=1.0, help='INA229: shunt tolerance in %%')
    parser.add_argument('--ref-uncertainty', type=float, default=0.1,
                        help='reference instrument uncertainty in %% of reading (default 0.1)')
    parser.add_argument('--port', help='UART device')
    parser.add_argument('--xsdb', help='path to xsdb')
    args = parser.parse_args()
    if args.sensor == 'ina229' and (args.shunt is None or args.max_current is None):
        parser.error('ina229 needs --shunt and --max-current')

    os.makedirs(args.out, exist_ok=True)
    environment(os.path.join(args.out, 'environment.txt'), args)
    con = Console(find_port(args.port), os.path.join(args.out, 'transcript.log'))
    res = Results(os.path.join(args.out, 'results.txt'))
    try:
        if args.elf:
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
