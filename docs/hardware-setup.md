# Hardware setup

## Equipment

| Item | Details |
|---|---|
| System-on-module | Trenz TE0715-05-71I33-L: AMD Zynq-7030 (xc7z030sbg485-1), 1 GiB DDR3, Silicon v3.1 |
| Carrier | Trenz TE0701, with its on-board Digilent FT2232H JTAG/UART (micro-USB) |
| CAN transceiver | TI SN65HVD233 (3.3 V) on a TI TCAN-SOIC8-EVM |
| CAN peer | Kvaser USBcan Light 2xHS on Ubuntu (SocketCAN `kvaser_usb`), channel `can0` |
| Boot medium | microSD card with the Trenz FSBL + U-Boot (`BOOT.BIN`) of the reference design |
| Reference design | Trenz TE0715 test_board, Vivado 2022.2, variant `04_30_1i_1gb` |

!!! note "Use the JTAG/UART micro-USB, not J12"
    J12 on the TE0701 is the Zynq's own USB OTG port; nothing enumerates there
    until software drives it. The JTAG/UART cable enumerates as
    `0403:6010 Digilent USB Device` with two interfaces: JTAG (A / `if00`) and the
    console UART (B / `if01`).

## CAN wiring

```mermaid
flowchart LR
    Z["TE0715<br/>CAN1"] -- "MIO12 TX / MIO13 RX" --> P["TE0701<br/>Pmod J1"]
    P -- "TXD, RXD, 3.3 V, GND" --> E["TCAN-SOIC8-EVM J3<br/>SN65HVD233"]
    E -- "CANH, CANL, GND (J7 / J9)" --> K["Kvaser can0<br/>or FlatSat bus"]
```

| Pmod J1 | Zynq signal | EVM J3 | SN65HVD233 pin |
|---|---|---|---|
| 10 | MIO12, CAN1 TX | 11 (TXD) | 1 (D) |
| 7 | MIO13, CAN1 RX | 9 (RXD) | 4 (R) |
| 6 | 3.3 V | 1 (VCC) | 3 (VCC) |
| 12 | GND | 2 (GND) | 2 (GND) |

!!! warning "Measure the Pmod power pins"
    The Trenz table lists pin 6 as 3.3 V and pin 12 as GND, while the Pmod
    standard uses 5/11 for GND and 6/12 for VCC. Check with a multimeter (continuity
    to a mounting hole with the board off, 3.3 V with it on) before connecting the
    transceiver.

Why CAN1 on MIO12/13: of the CAN pin pairs routed to Pmod J1, MIO10/11 (CAN0) are
also used as an I2C bus by the TE0701 system controller CPLD, while MIO12/13 are
only used by the CPLD for Microchip modules and are plain GPIO for AMD modules.

### TCAN-SOIC8-EVM jumpers for the SN65HVD233

| Jumper | Setting | Effect |
|---|---|---|
| J1 | J1A2-J1A3 | Pin 5 (LBK) to GND: normal mode, loopback off |
| J2 | J2A2-J2A3 | Pin 8 (RS) to GND: high-speed mode (needed for 1 Mbit/s) |
| J8 | shorted | VIO = VCC |
| J6 | shorted | Adds R13 (120 Ω) to the fitted R10 + R14 (120 Ω): 60 Ω for a short two-node bench bus |

On the FlatSat, remove J6 if the bus is already terminated at both ends.

### Kvaser

```bash
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
ip -details -statistics link show can0   # expect ERROR-ACTIVE, bitrate 1000000
```

## Host permissions (Ubuntu)

```bash
# JTAG: Xilinx/Digilent cable rules (from Vivado)
sudo cp /tools/Xilinx/Vivado/2022.1/data/xicom/cable_drivers/lin64/install_script/install_drivers/52-xilinx-*.rules /etc/udev/rules.d/
# UART: access for the logged-in user, also after re-plugging the cable
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{manufacturer}=="Digilent", TAG+="uaccess"' \
    | sudo tee /etc/udev/rules.d/70-digilent-uart.rules
sudo udevadm control --reload && sudo udevadm trigger --action=add
```

The console is `/dev/serial/by-id/usb-Digilent_*-if01-port0`, 115200 8N1.
