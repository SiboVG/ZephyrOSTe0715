# FlatSat from macOS

Procedure for connecting the TE0715 to the FlatSat CAN bus with only a Mac for the
console (no JTAG, no Linux host).

## What is on the board

The SD card boots the FlatSat image (`apps/fprime_csp_bench`, see
[SD card boot](sd-card-boot.md)):

| Item | Value |
|---|---|
| CAN | CAN1 on Pmod J1 through the SN65HVD233, 1 Mbit/s |
| CSP | version 2, default node **6061**, prefix **8** (lab51 EGSE subnet 6016/8, next to the Ubuntu test host 6060) |
| Services | CSP ping, and libparam server on port 10: parameter **200** (`u32`, `bench_integer`, initial `0x12345678`) |
| Console | serial shell: `bench`, `csp`, `param`, `can`, `kernel` |

## Before connecting

Confirm with the FlatSat owner:

- the bus bitrate (the image uses 1 Mbit/s);
- that node **6061** (or which other node) may be used on the bus;
- which nodes and parameters may be read, and which writes are approved;
- termination: remove jumper J6 on the EVM if the bus is already terminated at
  both ends; keep a common ground.

## Connect

1. Power off. Connect the EVM's CANH/CANL/GND (J7 or the DSUB9 J9) to the FlatSat
   bus instead of the Kvaser.
2. Connect the TE0701's JTAG/UART micro-USB to the Mac (the UART is only for the
   console; nothing is loaded over it).
3. Find the console port on the Mac. The cable shows two ports; the UART is the one
   ending in **B**:

    ```bash
    ls /dev/cu.usbserial-*
    # /dev/cu.usbserial-25163300AA8CA   (JTAG)
    # /dev/cu.usbserial-25163300AA8CB   (UART console)
    ```

    macOS has the FTDI driver built in; no installation is needed. If the names do
    not end in A/B, the UART is the second of the two ports (in alphabetical order);
    pass it with `--port`.

## Open the console

With the logging console from this repository (Python 3 and pyserial). Copy
`scripts/flatsat_console.py` and `scripts/flatsat_checks.txt` to the Mac first.

```bash
python3 -m pip install --user pyserial
python3 flatsat_console.py            # auto-detects /dev/cu.usbserial-*B
```

Type commands and press Enter; Ctrl-C quits. Everything is written with timestamps
to `flatsat-<date>-<time>.log` for the report.

Alternatives without Python:

```bash
screen /dev/cu.usbserial-25163300AA8CB 115200     # quit: Ctrl-A then K, then y
brew install tio && tio -t --log --log-file flatsat.log /dev/cu.usbserial-25163300AA8CB
```

## Boot

Open the console first, then power on the TE0701. After about 4 s:

```text
*** CSP bench server: default node 6061/8. Type `bench start [node] [prefix]` within 10 s
to start (on another node), or wait for the defaults. ***
uart:~$
```

- Do nothing to start on 6061/8, or
- type `bench start 6062 8` (for example) within 10 s to use another approved node.

The node cannot be changed after the start; power-cycle to choose again. The server
is ready when this line appears:

```text
[CSP_BENCH_READY] role=server can=can1 node=6061 peer=6061 param=200 type=u32 index=0
```

## Shell commands

| Command | Does |
|---|---|
| `bench info` | Node, prefix and start state |
| `csp ping <node> [bytes] [timeout_ms] [--nocrc]` | CSP ping, with CRC32 unless `--nocrc` |
| `param get <node> <id> <type> [index]` | Read a remote parameter (libparam protocol 2, port 10) |
| `param set <node> <id> <type> <value> [index] --confirm` | Write a remote parameter, then read it back with a separate request |
| `can show can@e0009000` | Controller state, error counters, bit/stuff/CRC/form/ACK error statistics |
| `kernel thread list` | Threads, priorities and stack use |

Types: `u8 i8 u16 i16 u32 i32 u64 i64 float double`. Values accept decimal or `0x`
hexadecimal. `param set` without `--confirm` is refused.

## Test sequence

1. **Bus health** after boot:

    ```text
    uart:~$ can show can@e0009000
    ```

    Expect `rx errors: 0`, `tx errors: 0` and no bit/stuff/CRC/form errors. ACK
    errors would mean no other node acknowledges (bus not connected or wrong
    bitrate).

2. **FlatSat → TE0715**: from the FlatSat side (e.g. csh), `ping 6061`.

3. **TE0715 → FlatSat**: `csp ping <OBC_NODE>` a few times; note the round-trip
    times.

4. **Reads**: `param get <OBC_NODE> <PARAM_ID> <TYPE> [INDEX]` for the approved
    parameters.

5. **Writes, only if approved**: read the current value first, write, and restore:

    ```text
    param get <NODE> <ID> <TYPE>
    param set <NODE> <ID> <TYPE> <NEW_VALUE> --confirm
    param set <NODE> <ID> <TYPE> <ORIGINAL_VALUE> --confirm
    ```

6. **Bus health** again: `can show can@e0009000`.

Steps 1, 3, 4 and 6 are in `flatsat_checks.txt`: replace the `<...>` values, then
run them in one go with a log:

```bash
python3 flatsat_console.py --run flatsat_checks.txt
```

!!! warning "Parameter access from csh"
    The TE0715 serves parameter 200 on the libparam port (10) but not libparam's
    list service (port 12, part of libparam's vmem server), so a csh `list download`
    from the node will not work and csh may not be able to `get` the parameter by
    name. CSP ping works in both directions; parameter reads and writes are driven
    from the TE0715's shell.

## Troubleshooting

| Symptom | Check |
|---|---|
| No console output | Port ending in **B**; 115200 8N1; only one program may use the port |
| `ping`: no reply, `can show` shows ACK errors | Bus not connected, other nodes off, or bitrate mismatch |
| `ping`: no reply, no CAN errors | Node not reachable through the FlatSat routing; wrong node or prefix; the peer may require CRC32 (default) or not accept it (`--nocrc`) |
| `can show`: bit or stuff errors, bus-off | Termination, CANH/CANL swapped, ground |
| `param get` fails | Parameter ID, type or index not as in the node's parameter table; node does not serve libparam protocol 2 |
| Board boots PetaLinux | SD card `boot.scr` restored, or card swapped; see [SD card boot](sd-card-boot.md) |
