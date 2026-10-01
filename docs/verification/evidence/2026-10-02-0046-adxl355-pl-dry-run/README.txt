Dry run of sensor_bench.py adxl355-pl (TC-22) before the sources were committed (written by hand
afterwards; not in SHA256SUMS). Not assessed: the assessed run is 2026-10-02-0055-adxl355-pl.

Image: bench 8bba2bf-dirty with the TC-22 changes (committed later as 210d470), fprime-adxl355
17c4829 (FROZEN_DATA). Bitstream: the uncommitted milestone-2 build of the development runs
(git=0xedefe1cb dirty=1), hence the one failure, the clean-build check of TC-22.1.
Script: sensor_bench.py as committed in 210d470 except step 6, which then waited for 12 printed
frames rather than one second.
Written to the scratch directory of the session and copied here unchanged.

Of note: in step 11 the clock stopped with a sample unread, so the frames after it were FROZEN_DATA
(5194); in the assessed run it stopped with the last sample read and they were STALE_DATA.
