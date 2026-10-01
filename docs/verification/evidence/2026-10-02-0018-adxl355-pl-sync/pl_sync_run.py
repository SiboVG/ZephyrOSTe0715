#!/usr/bin/env python3
"""TE-ADXL-007 run on the TE0715: ADXL355 on the PL's external clock and SYNC.

Loads the bench image and the cubespec-pl bitstream over JTAG (load.tcl: ACTLR.SMP and
L2 set as on an SD boot), then drives the shell and records everything in <out>/.
"""
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path

import serial

OUT = Path(sys.argv[1])
ELF = sys.argv[2]
BIT = sys.argv[3]
LOAD = Path(__file__).with_name("load.tcl")
XSDB = "/tools/Xilinx/Vitis/2022.1/bin/xsdb"
PORT = "/dev/ttyUSB1"

OUT.mkdir(parents=True, exist_ok=True)
transcript = open(OUT / "transcript.log", "w")
results = open(OUT / "results.txt", "w")
failed = 0


def log(text):
    transcript.write(text)
    transcript.flush()


def result(status, step, text):
    global failed
    line = f"{status:<5} {step:<10} {text}"
    print(line)
    results.write(line + "\n")
    results.flush()
    if status == "FAIL":
        failed += 1


def fields(line):
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


con = serial.Serial(PORT, 115200, timeout=0.2)


def read_until(pattern, timeout):
    buf = ""
    end = time.time() + timeout
    while time.time() < end:
        chunk = con.read(4096).decode(errors="replace")
        if chunk:
            log(chunk)
            buf += chunk
            m = re.search(pattern, buf)
            if m:
                return m.group(0), buf
    return None, buf


def cmd(text, pattern, timeout=10.0):
    con.reset_input_buffer()
    con.write((text + "\r").encode())
    line, buf = read_until(pattern, timeout)
    return line, buf


# Load
for attempt in range(3):
    load = subprocess.run(["timeout", "180", XSDB, str(LOAD), ELF, BIT, "on", "0x41"],
                          capture_output=True, text=True)
    (OUT / "load.log").write_text(load.stdout + load.stderr)
    if load.returncode == 0:
        break
result("PASS" if load.returncode == 0 else "FAIL", "load", f"xsdb load.tcl (ACTLR 0x41, L2 on), attempt {attempt + 1}")
line, _ = read_until(r"\[ADXL355_BENCH_READY\]", 20)
result("PASS" if line else "FAIL", "boot", "ready marker")
time.sleep(1)

line, _ = cmd("pl info", r"PL_INFO .*")
result("PASS" if line and "result=PASS" in line else "FAIL", "pl-info", line or "no answer")
line, _ = cmd("adxl info", r"ADXL_INFO .*")
result("INFO", "info", line or "no answer")

# Clock correlation: PL time base against the PS clock over 10 s
first, _ = cmd("pl time", r"PL_TIME .*")
time.sleep(10)
second, _ = cmd("pl time", r"PL_TIME .*")
if first and second:
    a, b = fields(first), fields(second)
    pl = int(b["pl_us"]) - int(a["pl_us"])
    ps = (int(b["ps_us_before"]) + int(b["ps_us_after"]) - int(a["ps_us_before"]) - int(a["ps_us_after"])) / 2
    result("INFO", "time", f"PL {pl} us against PS {ps:.0f} us over 10 s: {1e6 * (pl - ps) / ps:+.1f} ppm; {second}")

# External clock and sync, in the order of the ACC board design notes: configure the
# sensor first (INT2 and DRDY become inputs), then start EXT_CLK, then SYNC
cmd("adxl spi 9000000 0", r"ADXL_SPI .*")
line, _ = cmd("adxl cmd app-init 2 4000 0", r"ADXL_CMD app-init response=\w+", 15)
result("PASS" if line and line.endswith("=OK") else "FAIL", "init", f"INITIALIZE_ALL(G2, HZ_4000, OFF): {line}")
line, _ = cmd("pl clk on", r"PL_CLK .*")
result("INFO", "clk", line or "no answer")
line, _ = cmd("pl sync on 256 8", r"PL_SYNC .*")
result("INFO", "sync", line or "no answer")
line, _ = cmd("pl delay 50", r"PL_DELAY .*")
result("INFO", "delay", line or "no answer")
time.sleep(0.5)  # more than one filter group delay

# 20000 frames on the PL's sync interrupt
line, _ = cmd("adxl stream start-pl 20000", r"ADXL_STREAM_STARTED .*|error.*")
result("PASS" if line and line.startswith("ADXL_STREAM_STARTED") else "FAIL", "start", line or "no answer")
for _ in range(40):
    time.sleep(0.5)
    status, _ = cmd("adxl stream status", r"ADXL_STREAM .*")
    if status and "streaming=0" in status:
        break
stop, _ = cmd("adxl stream stop", r"ADXL_STREAM_STOPPED .*")
if stop:
    f = fields(stop)
    ok = (f["frames"] == "20000" and f["complete"] == "20000" and f["stale"] == "0" and f["implausible"] == "0"
          and f["seq_gaps"] == "0" and f["missed_ticks"] == "0" and f["pl_overruns"] == "0"
          and int(f["acq_max_us"]) < 250)
    result("PASS" if ok else "FAIL", "4kHz", f"20000 frames on the PL sync, all complete, none stale, no gap: {stop}")
else:
    result("FAIL", "4kHz", "no stop answer")

# A few frames printed: the sync times are 250 us apart on the PL time base
cmd("adxl tlm off", r"\$ ")
_, buf = cmd("adxl stream start-pl 12 1", r"(ADXL_FRAME,[^\n]*\n.*){12}", 10)
cmd("adxl stream stop", r"ADXL_STREAM_STOPPED .*")
frames = re.findall(r"ADXL_FRAME,(\d+),(\d+),(0x[0-9a-f]+),(\w+),(-?\d+),(-?\d+),(-?\d+),([-\d.]+),([-\d.]+),([-\d.]+)", buf)
if len(frames) >= 10:
    times = [int(fr[1]) for fr in frames]
    steps = sorted(set(b - a for a, b in zip(times, times[1:])))
    g = [(float(fr[7]) ** 2 + float(fr[8]) ** 2 + float(fr[9]) ** 2) ** 0.5 for fr in frames]
    # The console printer skips frames while it is busy: steps are whole sync periods
    result("PASS" if all(st % 250 == 0 for st in steps) else "FAIL", "spacing",
           f"{len(frames)} printed frames, sync_us steps {steps} (multiples of 250), "
           f"|a| {min(g):.4f} to {max(g):.4f} g")
else:
    result("FAIL", "spacing", f"only {len(frames)} frames printed")

# Delay sweep: how soon after the sync instant the new sample can be read
for delay in (2, 5, 10, 20, 30):
    cmd(f"pl delay {delay}", r"PL_DELAY .*")
    cmd("adxl stream start-pl 4000", r"ADXL_STREAM_STARTED .*")
    time.sleep(1.5)
    stop, _ = cmd("adxl stream stop", r"ADXL_STREAM_STOPPED .*")
    f = fields(stop or "")
    result("INFO", f"delay{delay}", f"IRQ_DELAY {delay} us: complete={f.get('complete')} stale={f.get('stale')} "
           f"missed={f.get('missed_ticks')}")
cmd("pl delay 50", r"PL_DELAY .*")

# Stopping the external clock after it ran. The sensor's core runs on EXT_CLK, so it
# freezes: DATA_RDY stays set (a STATUS read no longer clears it) and the data
# registers keep the last sample. The library's STALE_DATA check does not see this;
# only a clock that never ran leaves DATA_RDY clear (TC-18.10).
cmd("pl sync off", r"PL_SYNC .*")
cmd("pl clk off", r"PL_CLK .*")
time.sleep(0.1)
line, _ = cmd("adxl drdy 50", r"ADXL_DRDY .*", 10)
f = fields(line or "")
result("PASS" if f.get("ready_first") == "50" and f.get("cleared_second") == "0" else "FAIL", "noclk",
       f"without EXT_CLK DATA_RDY stays set, STATUS reads do not clear it: {line}")
line, _ = cmd("adxl read 3 0", r"ADXL_READ_DONE .*", 10)
f = fields(line or "")
frozen = all(float(f.get(k, "nan")) == 0.0 for k in ("std_x_mg", "std_y_mg", "std_z_mg"))
result("PASS" if f.get("ok") == "3" and frozen else "FAIL", "frozen",
       f"the reads return the last sample again, as if fresh: {line}")

# Restarting: clock, then SYNC, then one filter settling time
cmd("pl clk on", r"PL_CLK .*")
cmd("pl sync on 256 8", r"PL_SYNC .*")
time.sleep(1)
line, _ = cmd("adxl drdy 200", r"ADXL_DRDY .*", 10)
result("PASS" if line and "result=PASS" in line else "FAIL", "restart", f"DATA_RDY clears again: {line}")
line, _ = cmd("adxl read 5 0", r"ADXL_READ_DONE .*", 10)
f = fields(line or "")
result("PASS" if f.get("ok") == "5" and float(f.get("std_x_mg", "0")) > 0 else "FAIL", "resumed",
       f"fresh samples again: {line}")
cmd("pl sync off", r"PL_SYNC .*")
cmd("pl clk off", r"PL_CLK .*")

con.close()
results.write(f"DONE {failed} failed\n")
results.close()
transcript.close()
names = sorted(p.name for p in OUT.iterdir() if p.name != "SHA256SUMS")
with open(OUT / "SHA256SUMS", "w") as sums:
    for name in names:
        sums.write(f"{hashlib.sha256((OUT / name).read_bytes()).hexdigest()}  {name}\n")
print(f"DONE {failed} failed")
sys.exit(1 if failed else 0)
