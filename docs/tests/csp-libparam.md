# CSP and libparam with the Linux bench

These tests run the FlatSat image (`apps/fprime_csp_bench`) against the Linux
acceptance bench. The Linux `CspBench` is unchanged and talks to the TE0715 exactly
as it talks to another Linux process in its own loopback test, so a pass shows that
the Zephyr build interoperates with the reference implementation.

The TE0715 serves:

| ID | Name | Type | Initial value | Provided by |
|---|---|---|---|---|
| 200 | `bench_integer` | `uint32` | `0x12345678` | the F Prime `CspLibparam` component |
| 201 | `led_d4` | `uint8` | 0 | the application: 1 switches LED D4 on, 0 off |

and answers CSP pings and libparam list requests (port 12).

Complete the [Hardware setup](hardware-setup.md) and the [CAN bus](can-bus.md) tests
first, with the Kvaser interface up at 1 Mbit/s.

## 1. Load the image and start the server

```bash
xsdb app/boards/trenz/te0715/support/xsdb.cfg \
    app/apps/fprime_csp_bench/build-fprime-automatic-zephyr/zephyr/zephyr.elf
```

Open the console ([Connecting to the board](../guide/connect.md)). Within 10 s, type
`bench start` to start on the default node 6061 without waiting. The server is ready
when this line appears:

```text
[CSP_BENCH_READY] role=server can=can1 node=6061 peer=6061 param=200 type=u32 index=0
```

Close the console before the next step if you use `fprime_e2e.py`, which needs the
serial port.

## 2. Linux client against the board

```bash
CSP_BENCH_BIN=../CspLibparamFprimeTest/build-artifacts/Linux/Deployments_CspBench/bin/CspBench
$CSP_BENCH_BIN --role client --can can0 --node 100 --peer 6061 \
    --write-test --write-value 0xA5A55A5A
```

This is the bench's standard client test. Each cycle pings the board, reads parameter
200, writes the test value and reads it back, then restores the original value and
reads it back. It needs 5 successful cycles within 10 attempts:

```text
[CSP_BENCH_PROGRESS] Attempt 1: CSP ping 100 -> 6061 received in 4 ms.
[CSP_BENCH_PROGRESS] Attempt 1: libparam GET node 6061 parameter 200[0] (u32) returned 305419896.
[CSP_BENCH_PROGRESS] Attempt 1: libparam SET node 6061 parameter 200[0] = 2779077210; GET read-back verified.
[CSP_BENCH_PROGRESS] Attempt 1: libparam RESTORE node 6061 parameter 200[0] = 305419896; GET read-back verified.
...
[CSP_BENCH_RESULT] PASS attempts=5 successes=5 failures=0
```

## 3. The LED parameter

The same client can switch the LED: point it at parameter 201, type `u8`, with test
value 1. Each cycle switches D4 on, reads it back and switches it off again, so the
LED flashes once per second:

```bash
$CSP_BENCH_BIN --role client --can can0 --node 100 --peer 6061 \
    --param-id 201 --param-type u8 --write-test --write-value 1
```

The board's console logs each change:

```text
PARAM led_d4 = 1: LED D4 on
PARAM led_d4 = 0: LED D4 off
```

## 4. The board as a client: shell tools

Start a Linux server on another node:

```bash
$CSP_BENCH_BIN --role server --can can0 --node 102
```

and use the board's shell against it:

```text
uart:~$ csp ping 102
ping 102: reply in 3 ms (32 bytes)
uart:~$ param get 102 200 u32
value 305419896 (0x12345678)
uart:~$ param set 102 200 u32 0xCAFEBABE --confirm
written and read back: 3405691582 (0xcafebabe)
uart:~$ param set 102 200 u32 0x12345678 --confirm
written and read back: 305419896 (0x12345678)
```

## 5. csh against the board

[csh](https://github.com/spaceinventor/csh) is Space Inventor's command shell, the
tool the FlatSat operators use. The FlatSat's csh steps can be rehearsed on the
bench with csh on the Kvaser (test case TC-10).

Build csh 2.10.5. Ubuntu 24.04's meson (1.3.2) fails at the link step with
"multiple definition" errors, so use a current meson from PyPI, as csh's README does:

```bash
sudo apt install libcurl4-openssl-dev libzmq3-dev libsocketcan-dev libbsd-dev \
    libelf-dev libyaml-dev pkg-config ninja-build python3-dev
git clone --recurse-submodules --branch 2.10.5 https://github.com/spaceinventor/csh.git
uv venv meson-venv && uv pip install --python meson-venv/bin/python meson pexpect pyserial
cd csh && PATH=../meson-venv/bin:$PATH ./configure && ninja -C builddir && cd ..
```

Then run the rehearsal. `app/scripts/csh_tc10.csh` holds the commands: CSP set-up as
node 100 on `can0`, `list download`, get and set by name, and the manual `list add`
fallback. csh needs a terminal, so `csh_check.py` runs them through a pty while
logging the board's console:

```bash
meson-venv/bin/python app/scripts/csh_check.py --csh csh/builddir/csh \
    --commands app/scripts/csh_tc10.csh --log tc10.log
```

The output of each command is shown in the
[FlatSat procedure](flatsat.md#4-on-the-flatsat-side-load-the-te0715-parameters-in-csh).

## All of it at once

Steps 1 to 4 and a standalone SD boot are automated:

```bash
app/scripts/fprime_e2e.py --bench $CSP_BENCH_BIN \
    --elf app/apps/fprime_csp_bench/build-fprime-automatic-zephyr/zephyr/zephyr.elf \
    --log e2e.log
app/scripts/fprime_e2e.py --bench $CSP_BENCH_BIN --sd-boot --log sd-boot.log
```

Each prints one `PASS`/`FAIL` line per check and exits with 0 only if all pass.
