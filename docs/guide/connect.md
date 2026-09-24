# Connecting to the board

The TE0701 carrier has one micro-USB connector for the host: the Digilent
**JTAG/UART** port. Through it a host PC gets two things at once:

- **JTAG**, used by `xsdb` to reset the board and load images into memory; and
- the **serial console** of the TE0715 (UART0), at 115200 baud, 8 data bits, no
  parity, 1 stop bit.

!!! warning "Not J12"
    J12 on the TE0701 is the Zynq's own USB port. Nothing appears on the host when
    it is plugged in there, because no software on the board drives it.

When the cable is connected correctly, the host sees a Digilent FT2232H with two
channels. Channel A is JTAG, channel B is the serial console.

| Host | JTAG | Serial console |
|---|---|---|
| Linux | used by `xsdb` | `/dev/serial/by-id/usb-Digilent_Digilent_USB_Device_<serial>-if01-port0` |
| macOS | not used | `/dev/cu.usbserial-<serial>B` |

On the development board the serial number is `25163300AA8C`.

## Opening the console

Only one program can use the serial port at a time. Close the terminal before running
one of the test scripts, which need the port themselves.

=== "Logging console (recommended)"

    `app/scripts/flatsat_console.py` works on Linux and macOS and writes everything,
    with timestamps, to a log file:

    ```bash
    python3 -m pip install --user pyserial     # once
    python3 app/scripts/flatsat_console.py
    ```

    It finds the port by itself, and waits for it if the board is still off (the
    cable's serial chip is powered by the board); use `--port` to name it. Type a
    command and press Enter; Ctrl-C or Ctrl-D quits. On macOS and Linux, Up and Down
    recall earlier commands (also from previous sessions), Left and Right edit the
    line, and Ctrl-R searches the history; the board's output is printed above the
    line being typed. The log is `flatsat-<date>-<time>.log` in the current
    directory, or the file given with `--log`.

=== "tio"

    ```bash
    sudo apt install tio          # Linux
    brew install tio              # macOS
    tio -t --log --log-file console.log <port>
    ```

    Quit with Ctrl-T, then Q.

=== "screen"

    ```bash
    screen <port> 115200
    ```

    Quit with Ctrl-A, then K, then Y. `screen` does not timestamp its output.

## What you see at boot

The board prints the output of the boot loaders, then Zephyr's banner and the
application's messages. For the FlatSat image booting from the SD card:

```text
U-Boot 2022.01 (Apr 04 2022 - 07:53:54 +0000)
...
Found U-Boot script /boot.scr
=== TE0715: booting Zephyr from zephyr.bin ...
*** Booting Zephyr OS build v4.4.2-6-g70b56a29cd74 ***

*** CSP bench server: default node 6061/8. Type `bench start [node] [prefix]` within 10 s
to start (on another node), or wait for the defaults. ***

uart:~$
[CSP_BENCH_READY] role=server can=can1 node=6061 peer=6061 param=200 type=u32 index=0
```

`uart:~$` is the prompt of the serial shell; the commands are described in
[The serial shell](shell.md).
