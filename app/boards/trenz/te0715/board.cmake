# SPDX-License-Identifier: Apache-2.0

# `west flash` / `west debug` load zephyr.elf into DDR over JTAG with AMD xsdb
# (xsdb must be on PATH, e.g. /tools/Xilinx/Vitis/2022.1/bin). Nothing is
# written to QSPI flash or the SD card. See support/xsdb.cfg.
include(${ZEPHYR_BASE}/boards/common/xsdb.board.cmake)
