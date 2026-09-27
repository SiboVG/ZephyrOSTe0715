# SPDX-License-Identifier: Apache-2.0
#
# ADXL355 bench on the TE0715: the Adxl355.Manager and Adxl355.SynchronizedApplication of
# fprime-adxl355 on SPI1 (Pmod J1), driven from the serial shell and a frame timing
# thread. Build with fprime-util (see docs/tests/adxl355.md).

cmake_minimum_required(VERSION 3.24.2)

# fprime-adxl355 is a checkout next to the west workspace (settings.ini library_locations;
# see docs/getting-started/index.md)
get_filename_component(ADXL355_LIBRARY_PATH "${CMAKE_CURRENT_LIST_DIR}/../../../../fprime-adxl355" REALPATH)
if(NOT EXISTS "${ADXL355_LIBRARY_PATH}/library.cmake")
    message(FATAL_ERROR "fprime-adxl355 not found next to the workspace (${ADXL355_LIBRARY_PATH})")
endif()

# Zephyr first: it selects the cross toolchain before project()
if(NOT BUILD_TESTING)
    list(APPEND EXTRA_DTC_OVERLAY_FILE "${CMAKE_CURRENT_LIST_DIR}/../../boards/te0701-spi1.overlay")
    find_package(Zephyr REQUIRED HINTS "${CMAKE_CURRENT_LIST_DIR}/../../../zephyr")
endif()

project(Adxl355Te0715 LANGUAGES C CXX)

# Zephyr skips CMake's compiler feature detection; the standard is selected by
# CONFIG_STD_CPP17 (as in apps/fprime_csp_bench)
set(CMAKE_CXX_COMPILE_FEATURES cxx_std_98 cxx_std_11 cxx_std_14 cxx_std_17)
set(CMAKE_C_COMPILE_FEATURES c_std_90 c_std_99 c_std_11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include("${FPRIME_FRAMEWORK_PATH}/cmake/FPrime.cmake")
fprime_setup_included_code()

add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/config")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Components/Client")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Top")

register_fprime_zephyr_deployment(
    Adxl355Te0715
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/Main.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/bench_cmds.cpp"
        "${CMAKE_CURRENT_LIST_DIR}/shell_cmds.c"
    DEPENDS
        Top
)

# Bench and fprime-adxl355 revisions for the boot banner and `adxl info`
include("${CMAKE_CURRENT_LIST_DIR}/../../fprime-bench/cmake/bench.cmake")
bench_add_revision_header("${ADXL355_LIBRARY_PATH}")
