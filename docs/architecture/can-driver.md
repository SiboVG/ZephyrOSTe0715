# CAN driver

The Zynq-7000 has two CAN controllers (CAN0 and CAN1) in its processing system.
Zephyr had no driver for them. A driver was proposed upstream in 2022
(PR #45101, by Immo Birnbaum), but the PR was closed in 2024 after review stalled,
and Zephyr's CAN driver API has changed considerably since. The new driver,
`drivers/can/can_xlnx.c` with the devicetree compatible `xlnx,zynq-can-1.0` (the same
name as in Linux), uses that PR as a reference but is written for the current API.

## The controller

Each controller has a 64-frame transmit FIFO, a 64-frame receive FIFO, four
acceptance filters, and interrupts for events such as "frame transmitted", "frame
received", "error" and "bus-off". It supports classical CAN up to 1 Mbit/s, normal
and internal-loopback modes.

## Design decisions

### One frame at a time in the transmit FIFO

The driver has to tell the caller of `can_send()` when its frame has been sent. The
controller raises a "transmitted" interrupt, but it has no register that says how
many frames are still in the FIFO. With several frames queued, one interrupt cannot
be attributed to a particular frame. (The 2022 driver completed every waiting caller
on the first interrupt, including callers whose frames had not been sent yet.)

The new driver therefore puts one frame into the FIFO at a time. Each "transmitted"
interrupt then completes exactly one `can_send()`. The cost is a gap of a few
microseconds between frames, small compared with the ~110 µs a frame takes at
1 Mbit/s.

### Filtering in software

The four hardware acceptance filters all feed the same receive FIFO, so they cannot
route frames to different users. The driver leaves them open and matches received
frames against up to 16 software filters (`CONFIG_CAN_XLNX_MAX_FILTERS`), which is
also more than four.

### Start and stop reset the controller

`can_start()` resets the controller and programs the timing and mode from scratch.
`can_stop()` resets it too, which empties both FIFOs; a frame that was still waiting
fails with `-ENETDOWN`. This keeps the driver state and the hardware in step without
special cases.

### Bus-off

If a controller sees too many errors, it disconnects itself from the bus ("bus-off").
The driver then:

1. fails the waiting frame with `-ENETUNREACH`;
2. resets the controller, which empties the FIFOs;
3. restarts it after at least 128 × 11 bit times, the recovery time defined by the
   CAN standard (ISO 11898-1), or, if the application chose manual recovery
   (`CONFIG_CAN_MANUAL_RECOVERY_MODE`), when it calls `can_recover()`.

The controller could also recover by itself, but it is not documented what happens
to a frame left in the FIFO; the reset avoids that uncertainty.

### Error state

The controller has no interrupt for changes of the error state (error-active,
error-warning, error-passive). The driver reads the state on every interrupt and
reports changes to the application, and `can_get_state()` reads it directly.

## Clock

The driver expects the controller's clocks to be running and takes the reference
frequency from the devicetree's `clock-frequency`. On the TE0715 the board code sets
them up; see [Board support](board.md#can-clock).

## Upstream status

| Branch (SiboVG/zephyr) | Base | Status |
|---|---|---|
| `xlnx-can` | upstream `main` | Ready for a pull request after the author's sign-off; independent of the UART fixes. Uses `main`'s new multi-callback state-change API |
| `te0715-can-v4.4.2` | v4.4.2 + UART fixes | Used by this workspace |

On both branches the driver passes Zephyr's `tests/drivers/can/api` and
`tests/drivers/can/timing` on the TE0715; see
[TC-03](../verification/test-cases.md#tc-03-can-driver-in-loopback).
