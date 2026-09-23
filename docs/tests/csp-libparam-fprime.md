# CSP, libparam and F Prime

Application: `apps/fprime_csp_bench`, the Zephyr counterpart of
`CspBench --role server`: the `CubeSpec.CspLibparam` component of
CspLibparamFprimeTest over `ZephyrCanTransport`, serving the `u32` parameter 200
(`bench_integer`, initial value `0x12345678`) on libparam port 10, on CSP node
6061/8 by default.

Peer: the Linux `CspBench` from CspLibparamFprimeTest (branch `zephyr-transport`)
on the Kvaser `can0`, i.e. the unmodified Linux acceptance test.

```bash
app/scripts/fprime_e2e.py --bench path/to/CspBench \
    --elf app/apps/fprime_csp_bench/build-fprime-automatic-zephyr/zephyr/zephyr.elf \
    --log e2e.log
```

## Linux client against the board

```bash
CspBench --role client --can can0 --node 100 --peer 6061 \
    --write-test --write-value 0xA5A55A5A
```

Each cycle: CSP ping, libparam GET, SET to `0xA5A55A5A` with read-back, and restore
of the original value with read-back. The test needs 5 successful cycles within 10
attempts.

```text
[CSP_BENCH_PROGRESS] Attempt 1: CSP ping 100 -> 6061 received in 4 ms.
[CSP_BENCH_PROGRESS] Attempt 1: libparam GET node 6061 parameter 200[0] (u32) returned 305419896.
[CSP_BENCH_PROGRESS] Attempt 1: libparam SET node 6061 parameter 200[0] = 2779077210; GET read-back verified.
[CSP_BENCH_PROGRESS] Attempt 1: libparam RESTORE node 6061 parameter 200[0] = 305419896; GET read-back verified.
...
[CSP_BENCH_RESULT] PASS attempts=5 successes=5 failures=0
```

## Shell tools

The board's serial shell (see [FlatSat from macOS](../flatsat.md#shell-commands))
against a Linux `CspBench --role server --node 102`:

| Command | Expected | Result |
|---|---|---|
| `csp ping 102` | reply (CRC32) | reply in 3 ms |
| `csp ping 102 32 1000 --nocrc` | no reply: the Linux bench requires CRC32 | no reply |
| `param get 102 200 u32` | `0x12345678` | `305419896 (0x12345678)` |
| `param set 102 200 u32 0xCAFEBABE` | refused without `--confirm` | refused |
| `param set 102 200 u32 0xCAFEBABE --confirm` | written, separate read-back matches | `written and read back: 3405691582 (0xcafebabe)` |
| `param set 102 200 u32 0x12345678 --confirm` | restored | `written and read back: 305419896 (0x12345678)` |
| `csp ping 4242 32 500` | timeout (no such node) | no reply |
| `can show can@e0009000` | no errors | all counters 0 |

!!! note "CRC32"
    The Linux CspBench (and by extension csh-based setups) requires CRC32 on
    incoming packets and drops others silently. The shell's `csp ping` therefore uses
    CRC32 by default, like libcsp's own service functions; libparam requests always
    do.

## Plain libcsp node

`apps/csp_node` is the same server without F Prime (libcsp + libparam only). It was
used to bring up libcsp and libparam on Zephyr before the F Prime integration.
