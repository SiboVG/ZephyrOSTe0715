# FlatSat test

This procedure connects the TE0715 to the FlatSat CAN bus and checks, in this order,
that it can be seen on the bus, that FlatSat nodes and the TE0715 can ping each other,
that csh on the FlatSat can read and write the TE0715's parameters (including
switching its LED), and that the TE0715 can read (and, where approved, write) FlatSat
parameters. It is test case [TC-09](../verification/test-cases.md#tc-09-flatsat).

No JTAG is involved: the TE0715 boots its image from the SD card, and a laptop (macOS
or Linux) is only used as the serial console. Where the commands differ, the steps
below give both.

## Roles

| Role | Uses | Does |
|---|---|---|
| **TE0715 operator** | a Mac or Linux laptop on the TE0701's micro-USB, `flatsat_console.py` | powers the TE0715, chooses its node, runs the TE0715-side commands, keeps the console log |
| **FlatSat operator** | csh connected to the FlatSat | runs the csh commands |

One person can do both.

## Before the day

### Agree the configuration with the FlatSat owner

| Item | Value to confirm | Used in step |
|---|---|---|
| CAN bitrate | 1 Mbit/s (the image is fixed at 1 Mbit/s) | 1 |
| TE0715 CSP node | default **6061** in the EGSE subnet 6016/8, or another free node | 3 |
| Termination | whether the bus is already terminated at both ends (then remove EVM jumper J6) | 1 |
| FlatSat nodes the TE0715 may talk to | e.g. the OBC's node | 7, 8 |
| FlatSat parameters it may read | ID, type, array index for each | 8 |
| FlatSat parameters it may write | only with explicit approval of parameter and value | 9 |

### Prepare the laptop

1. Copy two files from the workspace to the laptop (USB stick, `scp` or e-mail):
   `app/scripts/flatsat_console.py` and `app/scripts/flatsat_checks.txt`. A static copy
   of these docs is useful too: run `mkdocs build` and copy the `site/` folder.
2. Install the one dependency, pyserial:

    === "macOS"

        ```bash
        python3 -m pip install --user pyserial
        ```

    === "Linux"

        ```bash
        sudo apt install python3-serial     # Debian/Ubuntu; or: python3 -m pip install --user pyserial
        sudo usermod -aG dialout "$USER"    # once, to use serial ports without sudo; log out and in again
        ```

3. Fill in `flatsat_checks.txt`: replace every `<...>` with the agreed nodes and
   parameters.

### Check the board

The SD card must hold the FlatSat image. After a power cycle the console should show
`*** CSP bench server: node 6061/8 (default) ...` within a few seconds; see
[Booting](../guide/boot.md) if it boots PetaLinux instead.

## Procedure

Record each step's result in the
[FlatSat as-run record](../verification/flatsat-record-template.md).

### 1. Connect the hardware

With the TE0701 powered off:

1. Connect the EVM's CANH, CANL and GND (header J7 or the DSUB9 J9) to the FlatSat
   bus. Keep a common ground.
2. Set EVM jumper J6 as agreed (removed if the bus is already terminated).
3. Check that the EVM's 3.3 V supply is connected (Pmod J1 pin 6 to EVM J3 pin 1, see
   [Hardware setup](hardware-setup.md#1-connect-the-transceiver-to-pmod-j1)). Without
   it, the CAN controller counts millions of form errors on its undriven input, and
   `can show` keeps them until the next boot.
4. Connect the TE0701's JTAG/UART micro-USB (not J12) to the laptop.

### 2. Open the console

Start the logging console **before** powering the board, so the log includes the
boot:

```bash
python3 flatsat_console.py
```

The cable's serial chip is powered by the board, so its port does not exist yet. The
console says so and waits:

```text
[console] waiting for the Digilent UART; power on the board (Ctrl-C quits)
```

As soon as the board is powered on (step 3), the port appears and the console opens
it by itself and logs to `flatsat-<date>-<time>.log`. Keep it open for the whole
test. Up and Down recall earlier commands.

The cable shows up as two serial ports (see
[Connecting to the board](../guide/connect.md)), and the console uses the second one.
To check them by hand, or to pass one with `--port`, list them once the board is on:

=== "macOS"

    The console is the port ending in **B**:

    ```bash
    ls /dev/cu.usbserial-*
    # /dev/cu.usbserial-25163300AA8CA   JTAG (not used)
    # /dev/cu.usbserial-25163300AA8CB   console
    ```

=== "Linux"

    The console is the port ending in **if01-port0**:

    ```bash
    ls /dev/serial/by-id/
    # usb-Digilent_Digilent_USB_Device_25163300AA8C-if00-port0   JTAG (not used)
    # usb-Digilent_Digilent_USB_Device_25163300AA8C-if01-port0   console
    ```

### 3. Power on and choose the node

Power on the TE0701. The console prints `[console] ... at 115200 8N1` when it opens
the port. If it keeps waiting, the laptop does not see the cable at all: check that it
is a data cable (not charge-only), that it is in the JTAG/UART connector and not J12,
and try without a USB hub. `ioreg -p IOUSB` (macOS) or `lsusb` (Linux) should then
show a Digilent device.

After a few seconds:

```text
*** Booting Zephyr OS build v4.4.2-6-g70b56a29cd74 ***

*** CSP bench server: node 6061/8 (default). Type `bench start [node] [prefix]` within 10 s
to start (on another node), or wait for the defaults. ***
```

- For node 6061, wait, or type `bench start`.
- For another node, type `bench start <node> 8` within 10 seconds.
- If the agreed node is known in advance, store it on the SD card instead, so it
  survives power cycles: put `csp_node=<node>` in `te0715.txt` on the card (see
  [Configuration](../guide/configuration.md#the-csp-node-te0715txt-on-the-sd-card)).
  The banner then says `(te0715.txt)`.

Continue when this line appears:

```text
[CSP_BENCH_READY] role=server can=can1 node=6061 peer=6061 param=200 type=u32 index=0
```

Then confirm the configuration:

```text
uart:~$ bench info
node 6061/8 (default, started), libparam server port 10: parameter 200 (u32)
parameter 201 led_d4 (u8) = 0: LED D4 off; parameter list served on port 12
```

### 4. On the FlatSat side: load the TE0715 parameters in csh

csh only knows a node's parameters after loading their descriptions (name, ID, type).
The TE0715 serves its list, so csh can download it:

```text
node 6061
list download
list
```

`node 6061` makes 6061 the default node for the following commands (the csh prompt
then shows `6061`), and `list download` asks the TE0715 for its parameter list
(libparam's list service on port 12). Expected output, as recorded on the bench with
csh 2.10.5:

```text
Got param: led_d4:6061[1]
Got param: bench_integer:6061[1]
Received 2 parameters, of which 0 remote parameters were skipped
```

`list` then shows the two TE0715 parameters, without values yet (`-`) because csh
has not read them:

```text
 200:6061  bench_integer        = - raw
 201:6061  led_d4               = -
```

| ID | Name | Type | Meaning |
|---|---|---|---|
| 200 | `bench_integer` | `uint32` | Test value, starts at 305419896 (0x12345678) |
| 201 | `led_d4` | `uint8` | LED D4 on the TE0715: 1 on, 0 off |

If `list download` fails (for example because the gateway does not pass the list
service's RDP connection), add the two parameters by hand instead. This only
describes them to csh; it does not change anything on the TE0715:

```text
list add -n 6061 -a 1 -m c bench_integer 200 uint32
list add -n 6061 -a 1 -m c led_d4 201 uint8
list
```

Both options matter. `-a 1` gives the array length 1 that the TE0715 uses: without
it, csh can neither read nor write the parameter. `-m c` marks them as configuration
parameters: without a mask, csh's `list` and `get` hide them. `list` shows the same
two lines as above, without the unit `raw`.

### 5. Check the bus

On the TE0715:

```text
uart:~$ can show can@e0009000
```

| Expect | If not |
|---|---|
| `state: error-active` | error-warning/passive or bus-off: stop, check wiring, termination and bitrate |
| `rx errors` and `tx errors` 0 | rising counts: electrical problem |
| all error statistics 0 | `ack errors`: nobody acknowledges (not connected, or bitrate mismatch) |

### 6. FlatSat → TE0715

In csh:

```text
ping 6061
get bench_integer
get led_d4
```

Expected:

```text
Ping node 6061 size 0 timeout 1000: Reply in 2 [ms]
 200:6061  bench_integer        = 305419896 raw
 201:6061  led_d4               = 0
```

### 7. Switch the TE0715's LED from csh

In csh:

```text
set led_d4 1
```

- csh confirms the write: ` 201:6061  led_d4               = 1                    u08	 Rc`
- The green LED D4 on the TE0715 module switches on.
- The TE0715 console prints `PARAM led_d4 = 1: LED D4 on`.
- `get led_d4` in csh returns 1.

Then switch it off again and check:

```text
set led_d4 0
get led_d4
```

Optionally, check a write of the test value too, and restore it:

```text
set bench_integer 42
get bench_integer
set bench_integer 305419896
```

### 8. TE0715 → FlatSat

On the TE0715, for each agreed node and parameter:

```text
uart:~$ csp ping <node>
uart:~$ param get <node> <id> <type> [index]
```

Types are `u8 i8 u16 i16 u32 i32 u64 i64 float double`. Note the ping round-trip
times and the values.

Or run all prepared commands at once, which also logs them (close the interactive
console first, since only one program can use the port):

```bash
python3 flatsat_console.py --run flatsat_checks.txt
```

### 9. TE0715 writes to the FlatSat (only if approved)

Only for a parameter and value approved for this test. Read the original value, write,
check, and restore:

```text
uart:~$ param get <node> <id> <type>
uart:~$ param set <node> <id> <type> <new value> --confirm
uart:~$ param set <node> <id> <type> <original value> --confirm
```

Each `param set` reads the value back with a separate request and reports a mismatch.

### 10. Finish

1. Run `can show can@e0009000` again and compare with step 5.
2. In csh, `list forget 6061` removes the TE0715's parameters from the session.
3. Quit the console (Ctrl-C) and keep the log file with the as-run record.
4. Power off before disconnecting the bus.

## When to stop

Stop and power off the TE0715 if:

- the TE0715 or a FlatSat node goes bus-off or error-passive;
- FlatSat nodes report unexpected traffic or behaviour;
- a read returns a value that cannot be interpreted safely; or
- a write was not acknowledged or its read-back does not match.

## Troubleshooting

| Symptom | Check |
|---|---|
| The console keeps waiting after power-on | Board powered; data cable (not charge-only) in the JTAG/UART connector, not J12; no USB hub; on Linux, the printed error (e.g. no permission: `dialout`) |
| No console output | The console port (**B** on macOS, **if01** on Linux); on Linux, membership of `dialout`; only one program may use the port; 115200 8N1 |
| The board boots PetaLinux | `boot.scr` on the SD card was restored; see [Booting](../guide/boot.md) |
| csh `ping 6061` gets no reply | Node chosen in step 3; the FlatSat's routing to the 6016/8 subnet; `can show` on the TE0715 |
| `csp ping` from the TE0715 gets no reply, no CAN errors | The node may not accept CRC32: try `--nocrc`; or it is not routed |
| `ack errors` rising | TE0715 not connected to the bus, other nodes off, or wrong bitrate |
| Bit, stuff, CRC or form errors | EVM powered (the statistics count from boot, so power-cycle the TE0715 after powering the EVM); termination (J6), CANH/CANL swapped, grounding |
| `list download` fails | Use the `list add` commands in step 4 |
| `get led_d4` in csh says the parameter is unknown | Load the list first (step 4); check `node` is 6061 |
| `list`, `get` or `set` print nothing after `list add` | The `-a 1 -m c` options are missing: `list forget 6061` and add them again |
| csh prints `RTNETLINK answers: Operation not permitted` at `csp add can` | Harmless: csh tries to set the bitrate, which is already set |
| `param get` on the TE0715 fails | ID, type or index not as in the node's parameter table |
