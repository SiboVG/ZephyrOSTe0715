# CAN bus

These tests use `apps/can_bringup`, a small application that does nothing but CAN:

- it echoes every frame with standard ID `0x100` back with ID `0x101` and the same
  data;
- it sends a heartbeat frame with ID `0x7F0` every second: a counter (bytes 0–3), the
  transmit and receive error counters (bytes 4 and 5), the bus state (byte 6) and the
  number of echoed frames (byte 7);
- it prints bus-state changes and every received frame on the console.

Complete the [Hardware setup](hardware-setup.md) first.

## 1. Check the wiring without a peer

Before involving another node, check that the transceiver is connected correctly.
Keep the Kvaser **down** (`sudo ip link set can0 down`), so that nobody acknowledges
frames, and start the application:

```bash
app/scripts/hw_test.py run app/apps/can_bringup --seconds 6
```

Every CAN frame must be acknowledged by at least one other node. Without one, the
controller keeps retransmitting its heartbeat frame and counts an ACK error each time.
What happens next tells whether the wiring is right:

| Observation | Meaning |
|---|---|
| The transmit error counter rises to 128 (error-passive) and **stays there**; only ACK errors; no bus-off | Correct: the transceiver is powered and loops the TX signal back to RX, so the controller reads back what it sends |
| Bit errors, and bus-off about once per second | Wrong: no transceiver, no power, or TX and RX swapped |

Expected output with correct wiring:

```text
STATE error-warning (tx errors 104, rx errors 0)
STATE error-passive (tx errors 128, rx errors 0)
HEARTBEAT 1: error-passive, tx errors 128, rx errors 0, ... ack errors 7805 (send -11)
HEARTBEAT 2: error-passive, tx errors 128, rx errors 0, ... ack errors 14943 (send -11)
```

`send -11` means the next heartbeat could not be queued because the previous one is
still being retried; that is expected here.

## 2. Echo 1000 frames through the Kvaser

Bring the Kvaser up (`sudo ip link set can0 type can bitrate 1000000 && sudo ip link
set can0 up`). The pending frame is acknowledged at once and the board returns to
error-active. Then run the host side of the test:

```bash
app/scripts/can_echo_test.py can0 --count 1000
```

The script sends 1000 frames with ID `0x100`, each with a different counter value,
and waits up to 100 ms for each echo. Afterwards it listens to the heartbeat for a few
seconds. It passes if every echo arrived with the right data, the heartbeat period is
1 s ± 10 %, and the board reports error-active:

```text
echo: 1000/1000 ok, 0 lost, 0 wrong payload in 6.0 s
heartbeat: 6 received, period 0.999 s, last counter 9, error-active, tx errors 0, rx errors 0
PASS
```

The heartbeat period also confirms, independently of the board, that the system
timer runs at the right rate.
