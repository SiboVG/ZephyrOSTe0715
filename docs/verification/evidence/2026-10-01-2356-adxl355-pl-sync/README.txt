Development run of TE-ADXL-007 before TC-22 existed (written by hand afterwards; not in SHA256SUMS).

Host: Ubuntu 24.04 x86_64, Digilent cable (JTAG interface 0, console /dev/ttyUSB1).
Image: app/apps/fprime_adxl355_bench with the uncommitted pl.cpp/start-pl changes of 2026-10-01
(bench 8bba2bf-dirty, fprime-adxl355 fdf02ef); see load.log for the paths.
Bitstream: cubespec-pl pp_te0701.bit built from the uncommitted milestone-2 tree on top of edefe1c
(pl info: git=0xedefe1cb dirty=1, map 0.2), the sources committed later as cubespec-pl 8857ed4.
Load: xsdb load.tcl <elf> <bit> on 0x41 (L2 cache on, ACTLR 0x41), the procedure xsdb.cfg sd-state now does.
Script: an uncommitted pl_sync_run.py, superseded by sensor_bench.py adxl355-pl (TC-22).
Same script as 2026-10-01-2327 apart from the frame-spacing check (whole multiples of 250 us).

Run after the advice to move the translator ground; the wiring at this run was not recorded. The
same partial frames as 2026-10-01-2327 (481 of 20000 complete).
