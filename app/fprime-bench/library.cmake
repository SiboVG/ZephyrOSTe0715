####
# F Prime components shared by the TE0715 sensor benches (apps/fprime_ina229_bench and
# apps/fprime_adxl355_bench): a command sender for the serial shell, a console
# telemetry printer, and SPI and argument-parsing helpers. Verification code, not
# flight code.
####
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/TeBench/ShellCommander")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/TeBench/TlmPrinter")
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/TeBench/Support")
