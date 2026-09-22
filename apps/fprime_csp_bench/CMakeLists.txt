# SPDX-License-Identifier: Apache-2.0
#
# CSP/libparam bench server on the TE0715: the CubeSpec.CspLibparam component
# from CspLibparamFprimeTest over the Zephyr CAN transport of
# fprime-csp-libparam. Build with fprime-util (see README.md).

cmake_minimum_required(VERSION 3.24.2)

set(CSP_BENCH_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../CspLibparamFprimeTest"
    CACHE PATH "CspLibparamFprimeTest checkout providing the CspLibparam component")

# Zephyr first: it selects the cross toolchain before project()
if(NOT BUILD_TESTING)
    list(APPEND EXTRA_DTC_OVERLAY_FILE "${CMAKE_CURRENT_LIST_DIR}/../../boards/te0701-can1.overlay")
    find_package(Zephyr REQUIRED HINTS "${CMAKE_CURRENT_LIST_DIR}/../../../zephyr")
endif()

project(CspBenchZephyr LANGUAGES C CXX)

# Zephyr skips CMake's compiler feature detection, so target_compile_features()
# in the libraries would reject cxx_std_17. The standard itself is selected by
# CONFIG_STD_CPP17 (-std=c++17).
set(CMAKE_CXX_COMPILE_FEATURES cxx_std_98 cxx_std_11 cxx_std_14 cxx_std_17)
set(CMAKE_C_COMPILE_FEATURES c_std_90 c_std_99 c_std_11)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# libcsp and libparam come from the Zephyr modules (CONFIG_LIBCSP, CONFIG_LIBPARAM)
set(FPRIMECSP_ENABLE_ZEPHYR_CAN ON CACHE BOOL "Zephyr CAN transport" FORCE)
add_library(fprimecsp_libparam_c ALIAS libparam)

include("${FPRIME_FRAMEWORK_PATH}/cmake/FPrime.cmake")
fprime_setup_included_code()

add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/config")

add_fprime_subdirectory("${CSP_BENCH_ROOT}/Components/CspLibparam")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/Top")

register_fprime_zephyr_deployment(
    CspBenchZephyr
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/Main.cpp"
    DEPENDS
        Top
)
