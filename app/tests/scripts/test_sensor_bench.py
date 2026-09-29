# SPDX-License-Identifier: Apache-2.0
"""Checks of sensor_bench.py against simulated INA229 and ADXL355 bench consoles."""

import argparse
import re
import threading

import sensor_bench


class FakeConsole(sensor_bench.Console):
    """A bench console without a serial port: run() appends the simulated board's answer."""

    def __init__(self, answer):
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.answer = answer
        self.sent = []

    def run(self, line, pattern, timeout=15):
        since = self.mark()
        self.sent.append(line)
        self.buf.extend((line + '\n' + self.answer(line) + 'uart:~$ \n').encode())
        return self.wait_for(pattern, 0, since), self.text(since)


def results(tmp_path):
    return sensor_bench.Results(str(tmp_path / 'results.txt'))


def ina_args(**overrides):
    values = dict(shunt=0.015, max_current=5.0, soak=1000, interactive=False, attach=True,
                  shunt_tolerance=1.0, ref_uncertainty=0.1)
    values.update(overrides)
    return argparse.Namespace(**values)


class Ina229Board:
    """Answers like fprime_ina229_bench with a healthy INA229 carrying 1 A at 12 V"""

    def __init__(self):
        self.errors = 0
        self.alert = 0x0001  # MEMSTAT

    def __call__(self, line):
        words = line.split()
        if words[:2] == ['ina', 'info']:
            return 'INA_INFO bench=abc library=def sclk_hz=1116071 mode=1\n'
        if words[:2] == ['ina', 'id']:
            return 'INA_ID manufacturer=0x5449 device=0x2291 die=0x229 rev=1 result=PASS\n'
        if words[:2] == ['ina', 'spi']:
            return f'INA_SPI requested_hz={words[2]} sclk_hz=1116071 mode={words[3]}\n'
        if words[:2] == ['ina', 'soak']:
            return f'INA_SOAK n={words[2]} bad_value=0 bad_lead=0 spi_errors=0 min_us=40 mean_us=41 max_us=60 result=PASS\n'
        if words[:2] == ['ina', 'init']:
            return 'INA_INIT status=OK ms=3\n'
        if words[:2] == ['ina', 'read']:
            n = int(words[2])
            row = 'INA_ROW,100,OK,0x7f,12.000000,0.015000000,25.0000,1.000000,12.000000,0.000000,0.000000,0x0003\n'
            return 'INA_HEADER,...\n' + row * n + f'INA_READ_DONE ok={n} failures=0\n'
        if words[:3] == ['ina', 'cmd', 'report']:
            return f'TLM sensor.Samples = 20 (1.0)\nTLM sensor.Errors = {self.errors} (1.0)\nINA_CMD report response=OK\n'
        if words[:3] == ['ina', 'cmd', 'snapshot']:
            return 'TLM sensor.Measurement = bus=12V (1.0)\nINA_CMD snapshot response=OK\n'
        if words[:3] == ['ina', 'cmd', 'init']:
            return 'INA_CMD init response=VALIDATION_ERROR\n'
        if words[:3] == ['ina', 'cmd', 'alert']:
            self.alert = (self.alert & 0x0FFF) | int(words[3], 16)
            return 'INA_CMD alert response=OK\n'
        if words[:3] == ['ina', 'cmd', 'reset-acc']:
            return 'INA_CMD reset-acc response=OK\n'
        if words[:2] == ['ina', 'reg']:
            return f'INA_REG addr=0x0b name=DIAG_ALRT bytes=2 value=0x{self.alert:04x}\n'
        if words[:2] == ['ina', 'timing']:
            return 'INA_TIMING ok_n=200 ok_min_us=500 ok_mean_us=520 ok_max_us=700 failed_n=0\n'
        if words[:3] == ['ina', 'stream', 'start']:
            return 'INA_STREAM_STARTED period_ms=100 rows=20\nINA_STREAM_DONE rows=20 not_ready=0 failures=0\n'
        if words[:3] == ['ina', 'stream', 'stop']:
            return 'INA_STREAM_STOPPED rows=20 not_ready=0 failures=0\n'
        return 'unknown\n'


def test_fields_and_rows():
    assert sensor_bench.fields('INA_ID a=1 b=0x2 result=PASS') == {'a': '1', 'b': '0x2', 'result': 'PASS'}
    assert sensor_bench.fields(None) == {}
    out = 'INA_ROW,1,OK,0x7f\nnoise\nINA_ROW,2,SPI_ERROR\n'
    assert sensor_bench.rows(out, 'INA_ROW') == [['INA_ROW', '1', 'OK', '0x7f'], ['INA_ROW', '2', 'SPI_ERROR']]


def test_wait_for_only_sees_output_after_the_mark():
    con = FakeConsole(lambda line: '')
    con.buf.extend(b'\x1b[1;32mINA_ID result=FAIL\r\n')
    since = con.mark()
    con.buf.extend(b'INA_ID result=PASS\r\n')
    assert con.wait_for(r'INA_ID .*', 0, since) == 'INA_ID result=PASS'
    assert con.wait_for(r'INA_ID .*', 0) == 'INA_ID result=FAIL'


def test_a_result_line_counts_only_once_complete():
    # A result line read while it is still arriving would lose its last fields
    con = FakeConsole(lambda line: '')
    con.buf.extend(b'ADXL_SOAK n=20000 bad_value=0 spi_er')
    assert con.wait_for(r'ADXL_SOAK n=.*', 0) is None
    con.buf.extend(b'rors=0 result=PASS\r\n')
    line = con.wait_for(r'ADXL_SOAK n=.*', 0)
    assert sensor_bench.fields(line)['result'] == 'PASS'


def test_ina229_healthy_board_passes(tmp_path):
    res = results(tmp_path)
    con = FakeConsole(Ina229Board())
    sensor_bench.ina229(con, res, ina_args())
    assert res.failed == 0, (tmp_path / 'results.txt').read_text()
    # every SPI clock is soaked, then the default setting is restored
    assert con.sent.count('ina soak 1000') == len(sensor_bench.INA229_SPI_POINTS)
    assert con.sent[con.sent.index('ina init 0.015 5.0') - 1] == 'ina spi 1200000 1'


def test_ina229_wrong_identity_and_counted_rejection_fail(tmp_path):
    board = Ina229Board()

    def answer(line):
        if line == 'ina id':
            return 'INA_ID manufacturer=0xffff device=0xffff result=FAIL\n'
        if line == 'ina cmd init 0 5':
            board.errors += 1  # the rejected argument was counted as a device error
        return board(line)

    res = results(tmp_path)
    sensor_bench.ina229(FakeConsole(answer), res, ina_args())
    text = (tmp_path / 'results.txt').read_text()
    assert re.search(r'^FAIL\s+TC-13\.1', text, re.M)
    assert re.search(r'^FAIL\s+TC-14\.10', text, re.M)


def test_ina229_current_inconsistent_with_shunt_voltage_fails(tmp_path):
    board = Ina229Board()

    def answer(line):
        if line.startswith('ina read'):
            # 15 mV across 15 mohm is 1 A, but 0 A is reported (as with SHUNT_CAL 0)
            row = 'INA_ROW,1,OK,0x7f,12.0,0.015,25.0,0.0,0.0,0.0,0.0,0x0003\n'
            return row * 20 + 'INA_READ_DONE ok=20 failures=0\n'
        return board(line)

    res = results(tmp_path)
    sensor_bench.ina229(FakeConsole(answer), res, ina_args())
    assert re.search(r'^FAIL\s+TC-14\.5', (tmp_path / 'results.txt').read_text(), re.M)


class Adxl355Board:
    """Answers like fprime_adxl355_bench with a healthy ADXL355 lying flat (+Z up)"""

    def __init__(self, stale_share=0.5, stale_acq_max_us=180):
        self.stale_share = stale_share
        self.stale_acq_max_us = stale_acq_max_us
        self.odr = 125.0

    def __call__(self, line):
        words = line.split()
        if words[:2] == ['adxl', 'info']:
            return 'ADXL_INFO bench=abc library=def\n'
        if words[:2] == ['adxl', 'id']:
            return 'ADXL_ID devid_ad=0xad devid_mst=0x1d partid=0xed revid=0x01 result=PASS\n'
        if words[:2] == ['adxl', 'spi']:
            return f'ADXL_SPI requested_hz={words[2]} sclk_hz=1116071 mode={words[3]}\n'
        if words[:2] == ['adxl', 'soak']:
            return f'ADXL_SOAK n={words[2]} bad_value=0 spi_errors=0 min_us=50 mean_us=52 max_us=70 result=PASS\n'
        if words[:2] == ['adxl', 'init']:
            self.odr = float(words[3]) if len(words) > 3 else 125.0
            return f'ADXL_INIT status=OK ms=40 odr_hz={self.odr:.3f}\n'
        if words[:2] == ['adxl', 'temp']:
            return ''.join(f'ADXL_TEMP status=OK raw=1885 celsius=25.000\n' for _ in range(int(words[2])))
        if words[:2] == ['adxl', 'read']:
            ok = 0 if getattr(self, 'synced', False) else int(words[2])
            return (f'ADXL_READ_DONE ok={ok} failures={int(words[2]) - ok} mean_x_g=0.01 mean_y_g=-0.02 '
                    f'mean_z_g=1.002 std_x_mg=0.3 std_y_mg=0.3 std_z_mg=0.4 magnitude_g=1.0023\n')
        if words[:2] == ['adxl', 'selftest']:
            return 'ADXL_SELFTEST samples=64 dx_g=0.3 dy_g=0.3 dz_g=1.5 result=PASS\n'
        if words[:2] == ['adxl', 'drdy']:
            return 'ADXL_DRDY n=20 ready_first=20 cleared_second=20 reserved_set=0 result=PASS\n'
        if words[:2] == ['adxl', 'timing']:
            return 'ADXL_TIMING ok_n=200 ok_min_us=120 ok_mean_us=125 ok_max_us=160 failed_n=0\n'
        if words[:3] == ['adxl', 'cmd', 'snapshot']:
            return 'TLM sensor.AccelerationZ = 9.81 (1.0)\nADXL_CMD snapshot response=OK\n'
        if words[:3] == ['adxl', 'cmd', 'range']:
            return 'manager: init-synced ...\n'
        if words[:3] == ['adxl', 'cmd', 'app-report']:
            return 'TLM app.SensorCount = 1 (1.0)\nADXL_CMD app-report response=OK\n'
        if words[:3] == ['adxl', 'cmd', 'init-synced']:
            self.synced = True
            return 'ADXL_CMD init-synced response=OK\n'
        if words[:3] == ['adxl', 'stream', 'start']:
            self.synced = False
            self.rate, self.frames = float(words[3]), int(words[4])
            return 'ADXL_STREAM_STARTED\n'
        if words[:3] == ['adxl', 'stream', 'status']:
            return 'ADXL_STREAM triggers=1 frames=1 streaming=0\n'
        if words[:3] == ['adxl', 'stream', 'stop']:
            # a new sample only every second trigger
            stale = int(self.frames * self.stale_share) if self.rate == 2 * self.odr else 0
            acq_max = self.stale_acq_max_us if stale else 180
            return (f'ADXL_STREAM_STOPPED triggers={self.frames} frames={self.frames} '
                    f'complete={self.frames - stale} partial={stale} stale={stale} implausible=0 busy=0 other=0 '
                    f'seq_gaps=0 missed_ticks=0 acq_min_us=120 acq_mean_us=130 acq_max_us={acq_max}\n')
        return 'unknown\n'


def test_adxl355_healthy_board_passes(tmp_path):
    res = results(tmp_path)
    con = FakeConsole(Adxl355Board())
    sensor_bench.adxl355(con, res, ina_args())
    assert res.failed == 0, (tmp_path / 'results.txt').read_text()
    # the 4 kHz budget steps run at 8.93 MHz, then the default clock is restored
    fast = con.sent.index('adxl spi 9000000 0', con.sent.index('adxl init 2 4000 0'))
    assert con.sent[fast + 1] == 'adxl stream start 4000 20000'
    assert con.sent[-2:] == ['adxl spi 1200000 0', 'adxl init 2 125 0']


def test_adxl355_slow_stale_frames_fail_the_budget(tmp_path):
    # a stale frame whose fault handling overruns the 250 us period at 4 kHz
    res = results(tmp_path)
    sensor_bench.adxl355(FakeConsole(Adxl355Board(stale_acq_max_us=265)), res, ina_args())
    text = (tmp_path / 'results.txt').read_text()
    assert re.search(r'^FAIL\s+TC-19\.5', text, re.M)
    assert re.search(r'^PASS\s+TC-19\.4', text, re.M)


def test_adxl355_stale_data_not_detected_fails(tmp_path):
    # triggered at twice the output data rate, a board that never reports STALE_DATA
    # is presenting old samples as new
    res = results(tmp_path)
    sensor_bench.adxl355(FakeConsole(Adxl355Board(stale_share=0.0)), res, ina_args())
    assert re.search(r'^FAIL\s+TC-19\.2', (tmp_path / 'results.txt').read_text(), re.M)
