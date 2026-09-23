# UART driver fixes

The console UART runs Zephyr's `uart_xlnx_ps` driver. Its standard test suite,
`tests/drivers/uart/uart_basic_api`, showed three bugs on the TE0715. The fixes are in
upstream pull request
[zephyrproject-rtos/zephyr#119996](https://github.com/zephyrproject-rtos/zephyr/pull/119996).

## 1. A baud-rate change took effect one call late

`uart_configure()` stored the new baud rate only after programming the hardware, and
the function that programs it read the stored value instead of its argument. So the
hardware always ran at the *previous* requested rate: asking for 57600 left the UART
at 115200, and asking for 115200 afterwards programmed 57600.

**Fix:** use the requested rate. **Check:** an application that switches
115200 → 57600 → 115200 now prints cleanly at each rate.

## 2. Reconfiguring cut a character in half

To change settings the driver switches the transmitter off, but it did so while a
character could still be on its way out. The receiving side (the PC) then saw a
broken character. When the console is busy, there is no pause in which the receiver
could find the start of the next character again, so it stayed out of step for
hundreds of characters: the test output was garbled for 300 to 800 bytes. In the
garbled data, every `=` (0x3D) arrived as 0xEA, which is exactly what a receiver two
bits out of step reads.

**Fix:** wait until the transmit FIFO is empty and the transmitter is idle before
switching it off, as the Linux driver does. **Check:** no garbled bytes.

## 3. The transmit interrupt reported "ready" when the FIFO was full

The driver used the controller's "TX trigger" flag to decide whether more data can be
written. That flag means the FIFO is filled *up to or above* a threshold, so the driver
reported "ready" when the FIFO was nearly full. A caller could then be told to write
while no space was left; the test's writer took that as "done" and stopped after one
character.

**Fix:** use only the "TX FIFO empty" interrupt, and report "ready" only if the
transmit interrupt is enabled and the FIFO is not full. **Check:** `uart_basic_api`
passes 7/7, in three consecutive runs.
