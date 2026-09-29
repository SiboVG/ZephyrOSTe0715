# ADXL355 bench

`app/apps/fprime_adxl355_bench` runs fprime-adxl355's `Adxl355.Manager` and
`Adxl355.SynchronizedApplication` (configured for one sensor) on SPI1 against a real
ADXL355. Set up the wiring first ([SPI sensor benches](spi-sensors.md)).

The sensor runs on its internal clock. The flight design synchronizes seven sensors
to a 1.024 MHz clock and a synchronization pulse from the FPGA; on this bench a
timing thread takes the FPGA's place and triggers the application's `acquireFrame`
port from a kernel timer, so the application's acquisition path runs exactly as in
flight, but without external synchronization.

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
| `adxl init [range] [odr_hz] [hpf]` | Initialize through the manager's `configure` port with the internal clock, as the application's `INITIALIZE_ALL_INTERNAL` does. Defaults ±2 g, 125 Hz, high-pass filter off. Output data rates: 4000, 2000, ..., 7.813, 3.906 Hz |
| `adxl measure on\|off` | Measurement mode through the `measurementControl` port |
| `adxl read [count] [rows 0\|1]` | Fresh samples through the `readAcceleration` port, with mean, standard deviation and magnitude. It waits one sample period between reads, so the manager does not count routine STALE_DATA as errors |
| `adxl temp [count]` | Temperature through the `readTemperature` port |
| `adxl selftest [samples]` | Self test: the mean output with ST1 and ST2 set minus the mean with only ST1 set, per axis, against the data sheet's Table 2 limits; self test is cleared afterwards |
| `adxl timing [n]` | Duration of n successful manager reads, and of STALE_DATA answers |
| `adxl stream start <rate_hz> [frames] [print_every]`, `adxl stream stop`, `adxl stream status` | Enable the application and trigger `acquireFrame` at rate_hz from the timing thread; the counts of complete, partial, stale and implausible frames, sequence gaps, missed timer ticks and the acquisition time per frame |
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
3. With a logic analyzer at 1.116 MHz: SCLK idles low, CS low over each whole
   transfer, data sampled on rising edges (ADXL-INT-001 of the library, for this
   controller). Save the capture with the evidence.

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
   stopped-clock case. `adxl init` restores the internal clock.

### TC-19 The synchronized application

With `adxl init 2 1000 0` (1 kHz):

1. Triggered at 500 Hz for 2500 frames: all complete, none stale, no sequence gap,
   no missed timer tick.
2. Triggered at 2 kHz for 4000 frames: 35 % to 65 % of the frames carry STALE_DATA
   (there is a new sample only every second trigger), none is implausible. Stale
   frames are partial frames, never old data presented as new.

With `adxl init 2 4000 0` (4 kHz):

3. Triggered at 2 kHz for 10000 frames: all complete.
4. Triggered at 4 kHz for 20000 frames: the longest acquisition stays below the
   250 µs period, no trigger is lost, nothing is implausible. Triggered exactly at the
   output data rate, the timer and the sensor's own oscillator drift against each
   other, so an occasional frame is stale: its share is recorded, not failed. Record
   the acquisition times; they cover one sensor at the SCLK in use, not the
   seven-sensor flight budget (ADXL-INT-004).

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
