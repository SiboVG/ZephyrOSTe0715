# ADXL355 bench

`app/apps/fprime_adxl355_bench` runs fprime-adxl355's `Adxl355.Manager` and
`Adxl355.SynchronizedApplication` (configured for one sensor) on SPI1 against a real
ADXL355. Set up the wiring first ([SPI sensor benches](spi-sensors.md)).

For TC-17 to TC-21 the sensor runs on its internal clock. The flight design
synchronizes seven sensors to a 1.024 MHz clock and a synchronization pulse from the
FPGA; for those test cases a timing thread takes the FPGA's place and triggers the
application's `acquireFrame` port from a kernel timer, so the application's
acquisition path runs as in flight, but without external synchronization. TC-22 runs
the flight mode: the [cubespec-pl](https://github.com/SiboVG/cubespec-pl) bitstream
generates the clock and the pulse, and its sync interrupt triggers `acquireFrame`
([External synchronization](#external-synchronization-from-the-pl)). A 10 Hz rate group calls the manager's
and the application's `schedIn` ports, which publish the fault events their
acquisition path queues.

Mount the sensor board so it can rest flat and on each of its sides (for TC-20), for
example on a small block with square faces.

The EVAL-ADXL355Z's 3-pin jumper labelled STBY is a leftover of the ADXL354 layout: on
the ADXL355 it connects pin 7, which the data sheet reserves (ground or open), and the
part is put into measurement mode through its POWER_CTL register instead. The position
makes no difference (checked on GND, open and VDDIO, see the
[as-run record of 2026-09-29](../verification/as-run-adxl355-2026-09-29.md#pin-7-the-eval-boards-stby-jumper));
the data sheet's choice is GND (pins 2–3) or no jumper.
The headers are described in UG-1030 (P1: VDDIO, VDD, GND, INT1, INT2, DRDY; P2:
V1P8ANA, V1P8DIG, MISO, CS, SCLK, MOSI); leave V1P8ANA and V1P8DIG unconnected.

## Shell commands

| Command | What it does |
|---|---|
| `adxl info` | Bench and library revisions, SPI settings, output data rate, streaming state |
| `adxl spi [hz [mode]]` | Show or change the SPI clock request and mode (not while streaming) |
| `adxl id` | Read DEVID_AD, DEVID_MST, PARTID and REVID directly over SPI; PASS for 0xAD, 0x1D, 0xED |
| `adxl reg <addr> [count]` | Read registers directly over SPI. Reading STATUS (0x04) clears DATA_RDY, reading FIFO_DATA (0x11) removes FIFO entries |
| `adxl soak <n>` | n direct reads alternating a 4-byte read from 0x00 and a 2-byte read from 0x01, each checked |
| `adxl drdy [n]` | Two STATUS reads back to back, once per sample period: reserved bits 7:5 read 0, and the second read finds DATA_RDY clear whenever the first found it set |
| `adxl phase [n]` | With the PL's clock and pulses running: where in the SYNC period the sensor sets DATA_RDY. STATUS is polled back to back, each poll bracketed by readings of the PL time base, until n polls have found it set; prints the interval common to all of them (`phase_lo_us` to `phase_hi_us`, from the sync instant) |
| `adxl init [range] [odr_hz] [hpf]` | Initialize through the manager's `configure` port with the internal clock, as the application's `INITIALIZE_ALL_INTERNAL` does. Defaults ±2 g, 125 Hz, high-pass filter off. Output data rates: 4000, 2000, ..., 7.813, 3.906 Hz |
| `adxl measure on\|off` | Measurement mode through the `measurementControl` port |
| `adxl read [count] [rows 0\|1]` | Fresh samples through the `readAcceleration` port, with mean, standard deviation and magnitude. It waits one sample period between reads, so the manager does not count routine STALE_DATA as errors |
| `adxl temp [count]` | Temperature through the `readTemperature` port |
| `adxl selftest [samples]` | Self test: the mean output with ST1 and ST2 set minus the mean with only ST1 set, per axis, against the data sheet's Table 2 limits; self test is cleared afterwards |
| `adxl timing [n]` | Duration of n successful manager reads, and of STALE_DATA answers |
| `adxl stream start <rate_hz> [frames] [print_every]`, `adxl stream stop`, `adxl stream status` | Enable the application and trigger `acquireFrame` at rate_hz from the timing thread; the counts of complete, partial, stale, implausible and frozen frames, sequence gaps, missed timer ticks, the acquisition time per frame, and the smallest and largest \|a\| of the valid samples (`mag_min_g`, `mag_max_g`) |
| `adxl stream start-pl [frames] [print_every]` | The same, triggered by the PL's sync interrupt; the frame time is the sync instant on the PL time base. Also counts missed sync events (`missed_ticks`, from gaps in `EVENT_COUNT`), `OVERRUN` interrupts (`pl_overruns`) and 100 ms waits without an event (`pl_timeouts`) |
| `pl info` | The bitstream: sysctrl identification, address-map version, populated slots, build (`git`, `dirty`, `build_time`), the time base frequency and the acc core; `result=PASS` if it is the cubespec-pl pp target with the map version the bench was built against |
| `pl clk on\|off`, `pl sync on [period [width]]\|off`, `pl delay <us>` | The acc core: EXT_CLK, the SYNC train (period and width in EXT_CLK periods, default 256 and 8: 250 µs) and the interrupt delay after each sync instant |
| `pl status`, `pl time` | The acc registers; the PL time base, with the PS clock read just before and after |
| `adxl cmd <command> [args]` | Send a command through the command dispatcher. Manager: `init-synced <range> <odr> <hpf>`, `start`, `stop`, `range <r>`, `filter <odr> <hpf>`, `sync <mode> <extclk>`, `offsets <x> <y> <z>`, `activity <mask> <threshold> <count>`, `interrupts <map> <active_high>`, `selftest <st1> <st2>`, `fifo-wm <n>`, `snapshot`, `clear-throttle`. Application: `app-init`, `app-init-internal` (both `<range> <odr> <hpf>`), `app-count <n>`, `app-enable <0\|1>`, `app-report`, `app-clear-throttle` |
| `adxl tlm [on\|off]` | Printing of telemetry on the console |

Samples and frames are CSV rows, for example:

```text
ADXL_HEADER,time_ms,status,raw_x,raw_y,raw_z,x_g,y_g,z_g
ADXL_ROW,40211,OK,-2310,1788,256940,-0.009023,0.006984,1.003672
ADXL_FRAME_HEADER,sequence,sync_us,valid,status,raw_x,raw_y,raw_z,x_g,y_g,z_g
ADXL_FRAME,500,41311208,0x01,OK,-2298,1802,256911,-0.008977,0.007039,1.003559
```

## Procedure

`sensor_bench.py adxl355` runs these steps; the numbers are those of the
[test case specifications](../verification/test-cases.md).

### TC-17 SPI1 link

1. `adxl id`: identity PASS; record REVID.
2. `adxl soak` with 20000 transfers at every SCLK of the clock table, mode 0.

The identity and the soaks also verify the chip select and the SPI mode by function
(`TE-SPI-002`, `TE-SPI-003`); no waveform is captured.

### TC-18 The F Prime manager

1. `adxl init 2 125 0`: `status=OK` (reset, NVM shadow-register check, configuration
   read back, measurement started).
2. `adxl temp 3`: 5 to 50 °C (the sensor's temperature output is not calibrated).
3. `adxl read 200 0`: all fresh; the magnitude of the mean at rest within 0.79 to
   1.21 g. The data sheet (Table 2) gives the sensitivity within ±8 % and the 0 g
   offset within ±75 mg per axis, so 1 g × (1 ± 0.08) ± √3 × 0.075 g. The noise per
   axis is recorded.
4. `adxl selftest 64`: X and Y 0.1 to 0.6 g, Z 0.5 to 3.0 g (Table 2).
5. `adxl drdy 20`: reserved STATUS bits read 0 and a STATUS read clears DATA_RDY
   (the library's ADXL-INT-008, here with the internal clock).
6. `adxl timing 200`: none failed; record the duration of one status-checked read.
7. Commands: `snapshot` and `app-report` answer OK with telemetry (sensor count 1); an
   invalid range is refused.
8. `adxl cmd init-synced 2 1000 0` with no 1.024 MHz clock connected, then
   `adxl read 1`: no sample is reported fresh (STALE_DATA). This is the library's
   case of a clock that never ran; a clock that stops after running is TC-22 step 9.
   `adxl init` restores the internal clock.

### TC-19 The synchronized application

With `adxl init 2 1000 0` (1 kHz):

1. Triggered at 500 Hz for 2500 frames: all complete, none stale, no sequence gap,
   no missed timer tick.
2. Triggered at 2 kHz for 4000 frames: 35 % to 65 % of the frames carry STALE_DATA
   (there is a new sample only every second trigger), none is implausible. Stale
   frames are partial frames, never old data presented as new.

With `adxl init 2 4000 0` (4 kHz):

3. Triggered at 2 kHz for 10000 frames: all complete.

Steps 4 and 5 check the 250 µs period of 4 kHz triggering, so they run at SCLK
8.93 MHz (`adxl spi 9000000 0`), the clock closest to the flight SPI's 10 MHz. At the
default 1.116 MHz the 15-byte read alone takes about 107 µs. Afterwards the default
clock is restored.

4. Triggered at 4 kHz for 20000 frames: the longest acquisition stays below the
   250 µs period, no trigger is lost, nothing is implausible. Triggered exactly at the
   output data rate, the timer and the sensor's own oscillator drift against each
   other, so an occasional frame is stale: its share is recorded, not failed.
5. With `adxl init 2 2000 0` (2 kHz), triggered at 4 kHz for 20000 frames: 35 % to
   65 % of the frames stale, and the same limits as step 4. Here every second frame
   is a stale or recovery edge. The manager and the application queue these edges on
   the acquisition path and publish them as events (throttled after 10 each) and
   telemetry from the 10 Hz rate group, so this step bounds the cost of a fault edge on
   the acquisition path.

Record the acquisition times. They cover one sensor at 8.93 MHz, not the seven-sensor
flight budget (ADXL-INT-004).

### TC-20 Six orientations (interactive)

Rest the board with each axis up and then down; 200 samples each. The axis along
gravity reads ±1 g within 0.83 to 1.17 g, the other two stay below 0.2 g (Table 2 plus
up to about 5° of placement error). From each pair: the 0 g offset within ±75 mg and
the sensitivity within ±8 % of nominal.

### TC-21 Faults (interactive)

1. Disconnect MISO: `adxl id` fails, no sample is reported valid, and frames are
   partial (IMPLAUSIBLE_DATA: the pulled-up line reads as all ones).
2. Reconnect MISO: frames complete again without reinitialization.
3. Disconnect CS: no sample is reported valid.
4. Reconnect CS: samples recover.

## External synchronization from the PL

TC-22 runs the sensor as in flight: on a 1.024 MHz clock on its `INT2` pin and a
4 kHz synchronization pulse on its `DRDY` pin (`SYNC` register 0x05: `EXT_CLK` = 1,
`EXT_SYNC` = 01), both from the `acc` core of the cubespec-pl `pp_te0701` bitstream.
The PL interrupts the PS a programmable delay after every sync instant, with the
instant's time on the PL time base, and the timing thread triggers `acquireFrame` from
that interrupt instead of its kernel timer. The SPI stays on Pmod J1 (TC-17).

### Wiring

The PL pins are on TE0701 header J15, bank 13 at 1.8 V; the sensor's I/O runs at the
3.3 V of Pmod J1, so a TXS0108E level translator (a HW-221 module) sits between them.
Do not raise the bank voltage instead: on the TE0701 its supply also feeds an HP bank
with a 1.8 V maximum.

| From | To |
|---|---|
| J15 pin 1 (1.8 V) | HW-221 `VA` and `OE` |
| Pmod J1 pin 6 (3.3 V) | HW-221 `VB` (the sensor's VDDIO and VDD as for TC-17) |
| Pmod J1 pin 12 (GND) | HW-221 `GND` (the sensor's ground as for TC-17) |
| J15 pin 5 (`acc_ext_clk`, W13) | HW-221 `A1`; `B1` through 1 kΩ to P1-4 (`INT2`) |
| J15 pin 9 (`acc_sync`, U12) | HW-221 `A2`; `B2` through 1 kΩ to P1-6 (`DRDY`) |

`OE` must be tied to `VA`, or every channel is off. The 1 kΩ resistors limit the
current while the sensor still drives `INT2` and `DRDY` as outputs, before it is
configured for the external clock. Take the translator's ground from Pmod J1, the
sensor's ground, not from J15. The core's pin description is in cubespec-pl's
`docs/cores/acc.md`.

### Image and bitstream

The bench builds against cubespec-pl next to the workspace (`../cubespec-pl`, the
workspace's `pl/cubespec-pl`): `pl.overlay` includes its devicetree fragment
`sw/dts/pp-pl.dtsi`, and `pl.cpp` its register header `sw/include/pp_regs.h`. Build the
bitstream from a committed cubespec-pl tree (`make bit` there, see its
`docs/getting-started.md`), so that `pl info` reports its commit and `dirty=0`.

`sensor_bench.py adxl355-pl --elf <zephyr.elf> --bit <pp_te0701.bit>` loads both with
`xsdb.cfg <elf> <bit> sd-state`: the bitstream, then the PS initialization, then the
CPU state an SD boot leaves (L2 cache on, ACTLR 0x41), then the image. Without
`sd-state` the image runs several times slower ([known issues](../known-issues.md)).
Without a bitstream, a `pl` command stalls the bus: the PL register window does not
answer.

### TC-22 External synchronization

`sensor_bench.py adxl355-pl` runs these steps:

1. `pl info`: the cubespec-pl pp target, map 0.2, time base and acc present; built
   from the checked-out cubespec-pl commit, clean. `adxl id`: PASS.
2. `pl time` twice, 10 s apart: the PL time base within 1 ppm of the PS clock (both
   come from the PS crystal).
3. At SCLK 8.93 MHz: `adxl cmd app-init 2 4000 0` (`INITIALIZE_ALL`, ±2 g, 4 kHz, the
   external clock and synchronization), then `pl clk on`, `pl sync on 256 8` and
   `pl delay 50`, then 0.5 s, more than one filter group delay. This is the order of
   the ACC board design notes: the sensor is configured, so that `INT2` and `DRDY` are
   inputs, before the PL drives them.
4. `adxl drdy 200`: reserved STATUS bits read 0 and a STATUS read clears DATA_RDY, on
   the external clock.
5. `adxl stream start-pl 20000`: every frame complete, none stale, frozen or
   implausible, no sequence gap, missed event or overrun, the longest acquisition below
   250 µs; \|a\| of every valid sample within 0.79 to 1.21 g (TC-18 step 3) and its
   spread below 20 mg, so no sample, the first ones included, is corrupted.
6. 12 frames printed: their times are whole multiples of 250 µs apart on the PL time
   base (the console skips frames while it prints).
7. `adxl phase 400`, then three times: both signals off, a pause of a different
   length, the clock and the pulses on again, 1 s, `adxl phase 400` and 4000 clean
   frames. Each restart moves the pulse train against the sensor's own sample timing,
   so if the sensor did not follow the pulse, the phase would move with it. The four
   phase intervals must overlap.
8. With the interrupt 2, 5, 10, 20 and 30 µs after the sync instant: 4000 clean frames
   each.
9. Both signals off, so the clock stops with a sample unread. `adxl drdy 50`: DATA_RDY
   stays set, and no STATUS read clears it: the sensor's logic runs on EXT_CLK. Then
   100 frames triggered by the timer at 4 kHz, as a broken clock line with the
   interrupt still running would give: the first 8 are complete (that sample, then its
   repeats up to fprime-adxl355's `FROZEN_REPEAT_LIMIT`), the other 92 `FROZEN_DATA`.
10. The clock and the pulses on again, 1 s: `adxl drdy 200` passes, and 4000 frames on
    the sync interrupt are clean, without reinitialization.
11. Timer-triggered at 4 kHz, the clock stopped after 0.5 s: every incomplete frame is
    stale or frozen, none implausible. Which one depends on where in the period the
    clock stops: with the last sample already read, DATA_RDY stays clear (STALE_DATA).
12. The clock and the pulses on again; `adxl stream start-pl 20000`, the pulses stopped
    after 0.5 s: the triggers stop, the event waits time out (`pl_timeouts`), and every
    frame before is complete.

Afterwards the script restores the default SCLK and the internal clock. The
acquisition times cover one sensor at 8.93 MHz, not the seven-sensor flight budget
(ADXL-INT-004).

## Not covered yet

- **Seven sensors and the flight carrier.** TC-22 synchronizes one EVAL-ADXL355Z on
  the TE0701. The flight carrier's pins, seven sensors on one clock and pulse, and the
  seven-sensor acquisition budget (fprime-adxl355 ADXL-INT-004) are still open.
- **Signal capture.** The clock and the pulse are not captured with a scope or logic
  analyzer; TC-22 shows their effect on the sensor (DATA_RDY phase, fresh samples), and
  cubespec-pl's testbenches their timing.
