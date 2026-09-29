# Sensor bench as-run record (template)

Copy this page (for example to `as-run-ina229-<date>.md` or `as-run-adxl355-<date>.md`),
fill it in while running the [INA229 bench](../tests/ina229.md) or the
[ADXL355 bench](../tests/adxl355.md), and keep the `sensor_bench.py` package next to it
in `docs/verification/evidence/`. Record a failure as a failure; add a deviation rather
than editing a log. `results.txt` gives the verdict and the measured values of each
step; this record adds what the script cannot know.

## Identification

| Field | Entry |
|---|---|
| Test cases | TC-13 to TC-16 (INA229) / TC-17 to TC-21 (ADXL355) |
| Procedure | `docs/tests/ina229.md` / `docs/tests/adxl355.md`, revision / date: |
| Date, start time (UTC) | |
| Operator | |
| Evidence package | `docs/verification/evidence/<directory>`; `SHA256SUMS` sha256: |
| Result line of `results.txt` | `DONE ... passed, ... failed` |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier | TE0715-05-71I33-L on TE0701, serial: |
| Image | `zephyr.elf` sha256 (from `environment.txt`): |
| Bench and library revisions | from the boot banner / `info` line; `-dirty` is a deviation: |
| Sensor board | make, model, revision, serial or marking: |
| Wiring | Pmod J1 pins as in the guide? yes / no (describe), lead length: |
| Sensor supply | source, measured voltage at the sensor: |
| Pmod J1 power pins measured | pin 6 = V, pin 12 continuity to ground: |
| CAN transceiver disconnected | yes / no |
| INA229 only: shunt | resistance, tolerance, rating: |
| INA229 only: load circuit | supply voltage, load, current: |
| INA229 only: reference instruments | model, serial, calibration date, uncertainty used: |
| ADXL355 only: mounting | block / fixture, surface levelled? |
| Ambient temperature | |

## Results

Result: **P** pass, **F** fail, **NR** not run (give the reason). Copy the verdicts from
`results.txt`; add the observations the script does not make.

| Test case | Step | Check | Result | Notes |
|---|---|---|---|---|
| TC-13 / TC-17 | 1 | Identity | | |
| TC-13 / TC-17 | 2 | Soak at every SCLK (list the SCLKs that failed) | | |
| TC-14 / TC-18 | all | Manager: initialization, readings, commands, telemetry, timing | | read duration (max): |
| TC-15 | 1-3 | INA229 against references (both current directions) | | operating point: |
| TC-16 | 1-5 | INA229 faults; behaviour after the supply returns (step 4) | | |
| TC-19 | 1-4 | Application streams; acquisition time at 4 kHz (max) | | |
| TC-20 | all | Six orientations; offsets and sensitivities | | |
| TC-21 | 1-4 | ADXL355 faults | | |
| – | – | Unexpected events or telemetry in `transcript.log` | | |

## Findings for the libraries

Results that affect a library's requirements or its open hardware items (for example
INA-HIL-00x of fprime-ina229, or a step of fprime-adxl355's acceptance plan), and
what should change there:

| # | Library | Item | Finding |
|---|---|---|---|
| | | | |

## Deviations

| # | Step | Description | Effect on the result |
|---|---|---|---|
| | | | |
