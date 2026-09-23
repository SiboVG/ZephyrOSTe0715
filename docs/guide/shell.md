# The serial shell

The F Prime application (`apps/fprime_csp_bench`, the FlatSat image) has an
interactive shell on its serial console. It is Zephyr's standard shell, extended
with three command groups for this project:

| Group | Purpose |
|---|---|
| `bench` | Start the CSP/libparam server and show its configuration |
| `csp` | CSP tools: ping another node |
| `param` | libparam client: read and write parameters of other nodes |

Zephyr's own `can` and `kernel` command groups are included as well, for bus and
system diagnostics.

## Using the shell

- The prompt is `uart:~$`. Type a command and press Enter.
- **Tab** completes commands and lists the available subcommands.
- **Up/Down** walk through the command history; `history` lists it.
- Every command accepts `-h` for its own help, e.g. `param get -h`.
- Messages from the application (for example F Prime events) can appear in the
  middle of what you type. That does not affect the command: finish typing and press
  Enter.

Numbers can be given in decimal or, with a `0x` prefix, in hexadecimal.

## `bench`: the CSP/libparam server

When the image starts, it waits 10 seconds before starting CSP, so that the node
address can be chosen:

```text
*** CSP bench server: node 6061/8 (default). Type `bench start [node] [prefix]` within 10 s
to start (on another node), or wait for the defaults. ***
```

### `bench start [node] [prefix]`

Starts CSP now, optionally on another node and network prefix. Only accepted during
the start window.

| Argument | Meaning | Default |
|---|---|---|
| `node` | CSP node address, 1 to 16381 | 6061 |
| `prefix` | CSP network prefix length (netmask), 0 to 13 | 8 |

```text
uart:~$ bench start 6062 8
starting on node 6062/8
[CSP_BENCH_READY] role=server can=can1 node=6062 peer=6062 param=200 type=u32 index=0
```

After the start, the node cannot be changed; reset or power-cycle the board to choose
again:

```text
uart:~$ bench start 6063
already started on node 6062/8; reset the board to change it
```

### `bench info`

```text
uart:~$ bench info
node 6061/8 (default, started), libparam server port 10: parameter 200 (u32)
parameter 201 led_d4 (u8) = 0: LED D4 off; parameter list served on port 12
```

While the server runs, other nodes can ping it and read or write its parameters on
libparam port 10, and download their descriptions (name, ID, type) from the list
service on port 12, as csh's `list download` does:

| ID | Name | Type | Meaning |
|---|---|---|---|
| 200 | `bench_integer` | `uint32` | Test value of the F Prime component, starts at `0x12345678` |
| 201 | `led_d4` | `uint8` | LED D4: 1 on, 0 off. Starts at 0 |

Every change of `led_d4`, from whichever node, is logged on the console:

```text
PARAM led_d4 = 1: LED D4 on
```

The shell's own `param` commands cannot address node 6061 itself; they are for
other nodes.

## `csp`: CSP tools

### `csp ping <node> [bytes] [timeout_ms] [--nocrc]`

Sends a CSP ping (service port 1) and waits for the echo.

| Argument | Meaning | Default |
|---|---|---|
| `node` | Node to ping | required |
| `bytes` | Payload size, 1 to 128 | 32 |
| `timeout_ms` | How long to wait for the reply | 1000 |
| `--nocrc` | Send without CRC32 | CRC32 on |

```text
uart:~$ csp ping 102
ping 102: reply in 3 ms (32 bytes)
uart:~$ csp ping 4242 32 500
ping 4242: no reply within 500 ms
```

!!! note "Why CRC32 by default"
    Many CSP nodes, including the Linux CspBench, only accept packets that carry a
    CRC32 and silently drop the others. libcsp's own service functions and csh send
    CRC32, so the shell does too. Use `--nocrc` only for a node that does not accept
    CRC32.

## `param`: libparam client

Both commands use libparam protocol version 2 on port 10, with a 1-second timeout.
`<type>` is one of `u8`, `i8`, `u16`, `i16`, `u32`, `i32`, `u64`, `i64`, `float`,
`double`, and must match the parameter's type on the remote node. `[index]` selects
an element of an array parameter (0 to 127, default 0).

### `param get <node> <id> <type> [index]`

```text
uart:~$ param get 102 200 u32
value 305419896 (0x12345678)
```

### `param set <node> <id> <type> <value> [index] --confirm`

Writes a value and then reads it back with a separate request, to show that the
remote node really holds the new value. Without `--confirm` the command is refused,
so a write is never sent by accident:

```text
uart:~$ param set 102 200 u32 0xCAFEBABE
writes change the remote node: repeat the command with --confirm
uart:~$ param set 102 200 u32 0xCAFEBABE --confirm
written and read back: 3405691582 (0xcafebabe)
```

If the read-back value differs, the command prints `READ-BACK MISMATCH` and fails.

The value is sent exactly as typed, or not at all. A value that does not fit the type,
a negative value for an unsigned type, `inf`, `nan` and anything that is not a number
are refused before anything is sent:

```text
uart:~$ param set 102 200 u8 300 --confirm
u8 value '300' out of range; nothing written
```

!!! warning "Writes on the FlatSat"
    Only write parameters for which the write and the value are approved. Read the
    original value first and restore it afterwards; see the
    [FlatSat test procedure](../tests/flatsat.md).

### Errors

| Message | Meaning |
|---|---|
| `param get 102:200[0] failed (-1)` | No reply: node not reachable, not a libparam server, or unknown parameter ID |
| `Param decoding failed for ID ...` | The reply did not match the requested parameter (e.g. wrong type) |
| `... is already known here (this node's own parameter?)` | The node is the board itself; its own parameter is not accessed through the client |
| `CSP is not started yet (bench start)` | The command was typed during the start window |

## `can`: CAN controller (Zephyr)

The CAN controller's device name is `can@e0009000`. The most useful command is
`can show`, which prints the controller state and error statistics:

```text
uart:~$ can show can@e0009000
core clock:      100000000 Hz
max bitrate:     1000000 bps
...
mode:            normal
state:           error-active
rx errors:       0
tx errors:       0
statistics:
  bit errors:    0
  stuff errors:  0
  crc errors:    0
  form errors:   0
  ack errors:    0
  rx overruns:   0
```

How to read it:

| Field | Healthy | If not |
|---|---|---|
| `state` | `error-active` | `error-warning`/`error-passive`: errors on the bus; `bus-off`: the controller disconnected itself after too many errors (it recovers automatically) |
| `rx errors`, `tx errors` | 0 or low | Rising values mean errors while receiving or sending |
| `ack errors` | 0 | Nobody acknowledged our frames: bus not connected, other nodes off, or a bitrate mismatch |
| `bit`, `stuff`, `crc`, `form errors` | 0 | Electrical problems: termination, CANH/CANL swapped, grounding, or bitrate |

Other `can` subcommands (`dump`, `send`, `filter`, `bitrate`, `mode`, `start`,
`stop`) exist for bench diagnostics.

!!! danger "Do not use on the FlatSat"
    `can send` puts raw frames on the bus, and `can stop`, `can bitrate` and
    `can mode` change the controller under the running CSP stack. Only use them on
    the bench.

## `kernel`: system (Zephyr)

| Command | Shows |
|---|---|
| `kernel uptime` | Time since boot in milliseconds (`-p` for a readable format) |
| `kernel version` | Zephyr version |
| `kernel thread list` | All threads with priority, state and stack use |
| `kernel reboot cold` | Restarts the board (same as a power cycle, but keeps the power on) |

`kernel thread list` shows that the F Prime tasks run at the expected priorities;
see [F Prime on Zephyr](../architecture/fprime.md#threads-and-priorities).

!!! danger "`devmem`"
    `devmem` reads and writes physical memory and hardware registers directly. It is
    part of Zephyr's shell and should not be used unless you know exactly which
    register you are touching.
