# System overview

## Hardware

```mermaid
flowchart LR
    subgraph TE0715["TE0715-05-71I33-L"]
        PS["Zynq-7030 processing system<br/>2 x Cortex-A9, 666.67 MHz<br/>1 GiB DDR3"]
    end
    subgraph TE0701["TE0701 carrier"]
        USB["Digilent FT2232H<br/>JTAG + UART"]
        PMOD["Pmod J1"]
        SD["microSD"]
    end
    PS -- "UART0 (MIO14/15)" --> USB
    PS -- "JTAG" --> USB
    PS -- "CAN1 (MIO12/13)" --> PMOD
    PS -- "SD0" --> SD
    USB -- "micro-USB" --> HOST["Host PC or Mac"]
    PMOD --> XCVR["SN65HVD233<br/>TCAN-SOIC8-EVM"] --> BUS["CAN bus<br/>1 Mbit/s"]
```

The Zynq-7030 combines an ARM processing system (PS) with programmable logic (PL).
This project only uses the PS; the FPGA bitstream that the SD card's boot loader
loads is not needed by Zephyr. Zephyr runs on the first Cortex-A9 core.

## Software

The software is layered so that each piece can be tested on its own, and so that
the F Prime code is the same as on the Linux bench:

```mermaid
flowchart TB
    APP["F Prime application<br/>apps/fprime_csp_bench"]
    COMP["CubeSpec.CspLibparam component<br/>(CspLibparamFprimeTest)"]
    LIB["fprime-csp-libparam<br/>Stack, Registry, Server, Client, ZephyrCanTransport"]
    FPZ["F Prime + fprime-zephyr<br/>OS layer on Zephyr"]
    CSP["libcsp csh/2.10<br/>+ Zephyr CAN interface"]
    PARAM["libparam csh/2.10"]
    ZEPHYR["Zephyr 4.4.2<br/>CAN driver, UART driver, board te0715"]
    APP --> COMP --> LIB
    APP --> FPZ
    LIB --> CSP & PARAM
    PARAM --> CSP
    CSP --> ZEPHYR
    FPZ --> ZEPHYR
```

| Layer | Provided by | Changed in this project |
|---|---|---|
| Application, topology, serial shell | `app/apps/fprime_csp_bench` | new |
| `CspLibparam` component | CspLibparamFprimeTest | transport chosen per platform |
| CSP/libparam integration | fprime-csp-libparam | new `ZephyrCanTransport` |
| OS layer | fprime-zephyr | task stack size and priority fixes (patches) |
| CSP, parameters | libcsp, libparam `csh/2.10` | two build patches |
| Drivers, board | Zephyr | new CAN driver, UART fixes, new board |

## The pages in this section

- [Board support](board.md): what the `te0715` board definition sets up.
- [CAN driver](can-driver.md): the new driver for the Zynq's CAN controllers.
- [UART driver fixes](uart-driver.md): three bugs found in the console driver.
- [F Prime on Zephyr](fprime.md): how the F Prime build, topology and threads work.
- [Dependencies and patches](dependencies.md): pinned revisions and every patch.
