cmake_minimum_required(VERSION 3.20.0)

# 1. Define BOARD ROOT (Must  be absolute path or use CMAKE_CURRENT_SOURCE_DIR)
list(APPEND BOARD_ROOT ${CMAKE_CURRENT_SOURCE_DIR})

# 2. Pull in Zephyr
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(te0715_test)
target_sources(app PRIVATE src/main.c)

