# Hardware setup

## Equipment

| Item | Details |
|---|---|
| System-on-module | Trenz TE0715-05-71I33-L: Zynq-7030 (xc7z030sbg485-1), 1 GiB DDR3 |
| Carrier | Trenz TE0701, with the Digilent JTAG/UART on micro-USB |
| CAN transceiver | TI SN65HVD233 (3.3 V) on a TI TCAN-SOIC8-EVM |
| CAN peer | Kvaser USBcan Light 2xHS on Ubuntu, in-kernel `kvaser_usb` SocketCAN driver |
| Boot medium | microSD with the Trenz reference design's FSBL and U-Boot |

## 1. Connect the transceiver to Pmod J1

The Zynq's CAN controller only produces logic-level TX and RX signals. The
transceiver turns them into the differential CANH/CANL signals of the bus. The
SN65HVD233 runs from 3.3 V, the same level as the Zynq's pins, so no level shifting is
needed.

With the power off:

| Pmod J1 pin | Signal | EVM header J3 | SN65HVD233 |
|---|---|---|---|
| 10 | MIO12, CAN1 TX | pin 11, TXD | pin 1 (D) |
| 7 | MIO13, CAN1 RX | pin 9, RXD | pin 4 (R) |
| 6 | 3.3 V | pin 1, VCC | pin 3 |
| 12 | GND | pin 2, GND | pin 2 |

!!! warning "Measure the power pins first"
    The Trenz table lists Pmod J1 pin 6 as 3.3 V and pin 12 as GND, while the Pmod
    standard puts GND on pins 5 and 11 and VCC on 6 and 12. Before connecting the
    transceiver, check with a multimeter: with the board off, the GND pin has
    continuity to a mounting hole; with it on, the 3.3 V pin reads 3.3 V.

## 2. Set the EVM jumpers

The EVM supports many 8-pin transceivers; its jumpers select what pins 5 and 8 do.
For the SN65HVD233:

| Jumper | Setting | Why |
|---|---|---|
| J1 | J1A2 – J1A3 | Pin 5 is LBK (loopback). Tied to GND: normal operation |
| J2 | J2A2 – J2A3 | Pin 8 is RS (slope control). Tied to GND: high speed, needed for 1 Mbit/s |
| J8 | shorted | VIO = VCC (this transceiver has no separate I/O supply) |
| J6 | shorted on the bench | Adds 120 Ω to the EVM's built-in 120 Ω for 60 Ω in total: a correctly terminated two-node bus |

On a bus that is already terminated at both ends, such as the FlatSat, remove J6.

## 3. Connect the CAN peer

Connect the EVM's CANH, CANL and GND (header J7, or the DSUB9 connector J9) to Kvaser
channel A (`can0`): DSUB9 pin 7 is CANH, pin 2 CANL, pin 3 GND.

## 4. Bring up the Kvaser interface

```bash
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details -statistics link show can0
```

Expect `state ERROR-ACTIVE` and `bitrate 1000000`. The Kvaser has no listen-only mode:
once it is up it acknowledges frames on the bus.

## 5. Connect the JTAG/UART cable

Connect the TE0701's JTAG/UART micro-USB to the PC (not J12). Linux shows it as
`0403:6010 Digilent USB Device`; see [Connecting to the board](../guide/connect.md).
