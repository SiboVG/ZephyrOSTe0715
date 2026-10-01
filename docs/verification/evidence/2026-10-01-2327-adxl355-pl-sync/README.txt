Development run of TE-ADXL-007 before TC-22 existed (written by hand afterwards; not in SHA256SUMS).

Host: Ubuntu 24.04 x86_64, Digilent cable (JTAG interface 0, console /dev/ttyUSB1).
Image: app/apps/fprime_adxl355_bench with the uncommitted pl.cpp/start-pl changes of 2026-10-01
(bench 8bba2bf-dirty, fprime-adxl355 fdf02ef); see load.log for the paths.
Bitstream: cubespec-pl pp_te0701.bit built from the uncommitted milestone-2 tree on top of edefe1c
(pl info: git=0xedefe1cb dirty=1, map 0.2), the sources committed later as cubespec-pl 8857ed4.
Load: xsdb load.tcl <elf> <bit> on 0x41 (L2 cache on, ACTLR 0x41), the procedure xsdb.cfg sd-state now does.
Script: an uncommitted pl_sync_run.py, superseded by sensor_bench.py adxl355-pl (TC-22).
The script and load.tcl as used are in this folder.

Wiring: EXT_CLK and SYNC from TE0701 J15 pins 5 and 9 through the HW-221 translator, with the
translator's ground taken from J15, which the operator then reported as wrong (advice given: take
it from Pmod J1 pin 12). The frames were mostly partial (481 of 20000 complete) and |a| reached 0 g.
The last step expected STALE_DATA without the clock (as TC-18.10); the reads returned an identical
sample (std 0) instead: the first sign of the frozen sensor (TC-22 step 9).
