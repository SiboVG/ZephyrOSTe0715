# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(bench_test)

set(BENCH_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../apps/fprime_csp_bench)
target_sources(app PRIVATE src/value.c src/config.c ${BENCH_DIR}/bench_value.c ${BENCH_DIR}/bench_config.c)
target_include_directories(app PRIVATE ${BENCH_DIR})
