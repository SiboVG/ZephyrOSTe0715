# CSP over Ethernet as-run record 2026-10-23

This record assesses test case
[TC-25](test-cases.md#tc-25-csp-and-libparam-over-ethernet), CSP and libparam between
the TE0715 and the Linux bench over the Ethernet link
([Ethernet link, TC-25](../tests/ethernet.md#csp-and-libparam-over-ethernet-tc-25)), run
on 2026-10-23.

The raw evidence is in `docs/verification/evidence/2026-10-23-1741-tc25/`. It is not
edited; this page only refers to it. Times are the host's local time (CEST, UTC+2).

## Identification

| Field | Entry |
|---|---|
| Test case | TC-25 CSP and libparam over Ethernet, as specified at `61365e1` |
| Date, time | 2026-10-23, 17:41 (load) to 17:43 |
| Revisions | zephyr-te0715 `61365e1`, fprime-csp-libparam `becda86`, CspLibparamFprimeTest `1cd24aa`, Zephyr `70b56a29` with the workspace patches `0001` to `0003` (`environment.txt`) |
| Image | `apps/fprime_csp_bench` with `udp.conf`, `zephyr.bin` sha256 `bfd1b3fc...89f7b0` |
| Operator | Runs executed by Claude Code on SVG's request, on SVG's bench host; no manual step |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier, cable, host port | As in the [TC-24 record](as-run-zephyr-ethernet-2026-10-23.md): direct cable, `enxa0cec8ebc610` at 100 Mbit/s full duplex, 192.168.70.1/24 |
| Board | 192.168.70.2, MAC `02:00:00:07:15:01`; CSP node 6061/8 (the image's default; a console-loaded image does not use `te0715.txt`); UDP port 9220, peer 192.168.70.1:9220 |
| Linux side | `CspBench` (sha256 `748f4aca...bcd2cc4`) and `CspPingClient` (`edc91c90...9e0a695`) from CspLibparamFprimeTest `1cd24aa`, over UDP to 192.168.70.2 |
| Loading | `uboot_load.py` from the running TC-24 image's shell, XMODEM, CRC32 `0x8b7ad6aa` matched |

## Results

Result: **P** pass, **F** fail.

| Step | Check | Observed | Result |
|---|---|---|---|
| Load | Server started over Ethernet | `eth_xlnx_gem: ethernet@e000b000 link up, 100 MBit/s`; `[CSP_BENCH_READY] role=server udp=192.168.70.1:9220 node=6061 peer=6061 param=200 type=u32 index=0` | **P** |
| – | `bench info` | node 6061/8, started | **P** |
| 1 | Linux CspBench client, parameter 200, write test | `[CSP_BENCH_RESULT] PASS attempts=5 successes=5 failures=0`; every ping 1 ms; every write read back and restored | **P** |
| 2 | Linux client, `led_d4` (201, `u8`, value 1) | `PASS attempts=2 successes=2`; the board logged `PARAM led_d4 = 1: LED D4 on` and `= 0: LED D4 off` for each cycle; `bench info` shows the LED off afterwards | **P** |
| 3 | Plain libcsp `csp_if_udp` (`CspPingClient --udp`) | `[CSP_REFERENCE_PING_RESULT] PASS node=100 peer=6061 ping_ms=1` | **P** |
| 4 | Board shell against a Linux CspBench server (node 102) | `csp ping 102`: reply in 0 ms; with `--nocrc`: no reply (the server requires CRC32); `param get` 0x12345678; unconfirmed `param set` refused; confirmed write read back 0xcafebabe; `u8 300` refused; read 0xcafebabe; restore read back 0x12345678; `csp ping 4242`: no reply within 500 ms | **P** |
| – | Script verdict | `14/14 checks passed`, exit status 0 | **P** |

## Deviations

None. The board was loaded over the console (`uboot_load.py`) from the running TC-24 image,
as the procedure allows; no reset by hand or over JTAG was needed.

## Evidence integrity

| File | sha256 |
|---|---|
| `2026-10-23-1741-tc25/SHA256SUMS` | `781afc5585257c24ed246b1150ee930af0715c7f6e801e0aa9640f1812bb8012` |
| `2026-10-23-1741-tc25/environment.txt` | `7044f106b518c8f583746e92866400f610fd3c576e2287f368d9705c38977425` |
| `2026-10-23-1741-tc25/load.log` | `a44c532e4619ae1cd5aa46909b344bc4ae1f401c42765dbc5d3668180b2adaf3` |
| `2026-10-23-1741-tc25/e2e.log` | `7ebf58d0f75ff1a074bbe429a85ab1d0912cc336475c73f181bb8baed947d688` |
| `2026-10-23-1741-tc25/e2e-summary.txt` | `18eea6da08dfc5cb69354a970ad9eedd8df676b3cebfdfb34fdbba9e4d1b5bef` |

Check the folder with `sha256sum -c SHA256SUMS` inside it.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-ETH-003` The F Prime server over UDP on Ethernet | **Verified** | Client test 5/5, `led_d4` switched, and pings from libcsp's own `csp_if_udp` answered |
| `TE-ETH-004` Shell client tools over UDP | **Verified** | Ping, read, confirmed write with read-back and restore, and the refusals, as over CAN |

The run is also hardware evidence for fprime-csp-libparam's `FCL-UDP-001` (the datagram
format interoperates with libcsp's own UDP interface, on Zephyr against Linux) and
`FCL-UDP-007` (the transport built into the Zephyr image).

## Conclusion

The TE0715 carries CSP and libparam over its Ethernet port as it does over CAN: the F
Prime server and the shell's client tools work over fprime-csp-libparam's UDP transport,
and plain libcsp (the interface csh's `csp add udp` uses) talks to it. Round trips are
about 1 ms at 100 Mbit/s.
