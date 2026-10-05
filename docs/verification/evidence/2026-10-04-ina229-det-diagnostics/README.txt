INA229 bench bring-up diagnostics, 2026-10-04 (ina_det: 0.27 ohm shunt, 0.55 A max)

Console logs of the shell commands sent while finding why TC-14.11 failed in
2026-10-04-1307-ina229-det. The commands were typed by small Python scripts over
/dev/ttyUSB1 (115200 baud); each log is what the board printed. Assessed in
docs/verification/as-run-ina229-2026-10-04.md.

Images: logs 01 to 13 ran bench 887e90c (fprime-ina229 61ecaea, SPI mode 1 at boot),
loaded with `xsdb.cfg <elf> - sd-state`. Logs 14 to 18 ran the same sources plus the
first version of the `ina wreg` command (uncommitted at the time; its `spi=` field
printed the readback status twice). Each `ina wreg` line gives the value written, the
bytes the INA229 clocked out during the write frame (write_rx) and the readback.

01 smoke          identity, register reads, 2000-transfer soaks at 1.116 and 8.93 MHz
02 smoke2         raw VBUS, VSHUNT, DIETEMP before initialization
03 alert_exp      SET_ALERT_CONFIG with four bit values, two SCLKs: all VERIFY_ERROR
04 thresh_exp     SET_THRESHOLD on BOVL and SOVL: written and read back
05 stop_exp       STOP fails the same way (ADC_CONFIG write lost)
06 adc_exp        CONFIGURE_ADC with five configurations: all lost
07 idle_exp       writes with the ADC shut down / after one-shot: DIAG_ALRT still lost
08 clean_exp      one variable per init: ADC_CONFIG lost, CONFIG and BOVL written
09 addr_exp       SUVL, BUVL, TEMP_LIMIT, PWR_LIMIT, SOVL: all written
10 value_exp      second write after a first one: lost (later ones invalid state)
11 value_exp2     the failing values on SOVL as first write after init: all written
12 gap_exp        CONFIGURE_ADC right after init (0 to 0.5 s): lost
13 hist_exp       CONFIGURE_ADC after different preceding transfers: always lost
14 wreg_exp       first raw writes; time after a device reset (0 to 200 ms)
15 corrupt_exp    a lost write leaves CONFIG and the other registers unchanged;
                  write_rx f800 instead of fb6a in the lost frame
16 pullup_exp     after the operator added a pull-up to ina_fpga's floating CS:
                  all reads 0 (sensor wiring disturbed; fixed by the operator)
17 pullup_exp2    with the pull-up and the wiring restored: same lost writes
18 mode_exp       raw writes in SPI modes 0 to 3 at 558 kHz, 1.116 and 8.93 MHz:
                  every write intact in mode 3 only

bench_mode3.py: the wrapper that ran sensor_bench.py with every INA229 point in mode 3
for 2026-10-04-1332-ina229-det-mode3 (the script itself was not changed for that run).
