# CAN bus

Hardware: see [Hardware setup](../hardware-setup.md#can-wiring). Application:
`apps/can_bringup` on CAN1 at 1 Mbit/s:

- frames with standard ID `0x100` are echoed back with ID `0x101`;
- a heartbeat with ID `0x7F0` is sent every second: bytes 0-3 counter (big endian),
  4 TX error counter, 5 RX error counter, 6 bus state, 7 echoed frames;
- bus state changes and received frames are printed on the console.

```bash
app/scripts/hw_test.py run app/apps/can_bringup --seconds 5
```

## Wiring check

Run with the transceiver connected but **the Kvaser down** (nothing acknowledges
frames). The result distinguishes a working transceiver from a wiring fault without
any other equipment:

| Observation | Meaning |
|---|---|
| TX error counter rises to 128 and stays there (error-passive), only ACK errors, no bus-off | Transceiver powered and wired: it loops the controller's TX back to RX; the frame is retransmitted because nobody acknowledges it |
| Bus-off about once per second, bit errors | No transceiver, no power, or TX/RX swapped: the controller does not read back what it sends |

Result with the SN65HVD233:

```text
STATE error-warning (tx errors 104, rx errors 0)
STATE error-passive (tx errors 128, rx errors 0)
HEARTBEAT 1: error-passive, tx errors 128, rx errors 0, ... ack errors 7805 (send -11)
HEARTBEAT 2: error-passive, tx errors 128, rx errors 0, ... ack errors 14943 (send -11)
```

About 7100 ACK errors per second (continuous retransmission), no bus-off: wiring
correct. For comparison, before the transceiver was connected:

```text
STATE error-warning (tx errors 120, rx errors 0)
STATE error-passive (tx errors 176, rx errors 0)
STATE bus-off (tx errors 0, rx errors 0)
STATE error-active (tx errors 0, rx errors 0)
```

which also shows the driver's automatic bus-off recovery.

## Echo test

With the Kvaser up at 1 Mbit/s (`sudo ip link set can0 type can bitrate 1000000 &&
sudo ip link set can0 up`), the host script sends 1000 frames with ID `0x100` and a
counter payload, waits up to 100 ms for each echo, and then checks the heartbeat:

```bash
app/scripts/can_echo_test.py can0 --count 1000
```

Pass criteria: every echo received with the same payload, heartbeat period
1 s ± 10 %, and the board error-active.

```text
echo: 1000/1000 ok, 0 lost, 0 wrong payload in 6.0 s
heartbeat: 6 received, period 0.999 s, last counter 44, error-active, tx errors 0, rx errors 0
PASS
```

The same test passes with the driver built from upstream `main` (`xlnx-can`).
