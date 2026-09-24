# FlatSat as-run record 2026-09-24

This record assesses test case [TC-09](test-cases.md#tc-09-flatsat), the
[FlatSat test](../tests/flatsat.md), run on 2026-09-24. It follows the
[FlatSat record template](flatsat-record-template.md).

The raw evidence is in `docs/verification/evidence/2026-09-24-flatsat/`: the
TE0715 console logs from `flatsat_console.py` and a copy of the csh session. It is
not edited; this page only refers to it. Times are the laptops' local time (CEST,
UTC+2), as in the logs.

## Identification

| Field | Entry |
|---|---|
| Test case | TC-09 FlatSat |
| Procedure | `docs/tests/flatsat.md` at `556e837` (2026-09-24) |
| Date, time | 2026-09-24, 13:31 to 15:18: main session 13:38 to 14:33; follow-ups 14:55 to 15:01 (csh, `can show`) and 15:05 to 15:12 (reads); clean boot and `can show` before and after traffic 15:13 to 15:18 |
| TE0715 operator | S. Van Gool (SVG) |
| FlatSat operator | S. Van Gool (SVG) |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier | TE0715-05-71I33-L on TE0701, serial E220282 |
| Transceiver | TCAN-SOIC8-EVM (SN65HVD233); J6 termination not fitted. Its power supply was not connected at first (deviation 4) |
| SD card image | Not re-hashed. U-Boot loaded `boot.scr` (1114 bytes), `te0715.txt` (133 bytes) and `zephyr.bin` (316312 bytes), and Zephyr reports build `v4.4.2-6-g70b56a29cd74`: all identical to the SD boot in the [2026-09-24 record](as-run-2026-09-24.md) (`zephyr.bin` sha256 `2337e3ab...`) |
| Console host, port | Linux laptop, `/dev/serial/by-id/usb-Digilent_Digilent_USB_Device_25163300AA8C-if01-port0` |
| csh host | FlatSat laptop `lab51` |
| CAN bitrate | 1 Mbit/s |
| TE0715 CSP node / prefix | 6061/8, from `te0715.txt` |
| FlatSat nodes involved | 6022, 6028, 6030 (OBC, not powered until about 15:08) |
| Reads | 6022 parameter 130 (`i16`), 6030 parameter 131[0] (`u16`), as planned in `flatsat_checks.txt` |
| Writes | 6028 parameter 120 (`u8`) |

## Results

Result: **P** pass, **F** fail, **NR** not run, **Void** invalid because of a set-up error and repeated.

| Step | Check | Observed | Log | Result |
|---|---|---|---|---|
| 3 | Boot from SD card | U-Boot ran `boot.scr`, loaded `te0715.txt`; `node 6061/8 (te0715.txt)`; `CSP_BENCH_READY ... node=6061` | `133847` | **P** |
| 3 | `bench info` | `node 6061/8 (te0715.txt, started)`, `led_d4 (u8) = 0: LED D4 off` | `133847` | **P** |
| 4 | csh `list download` | `Got param: led_d4:6061[1]`, `Got param: bench_integer:6061[1]`, `Received 2 parameters`; `list` shows 200 and 201 | csh | **P** |
| 4 | `list add` fallback | Not needed | – | NR |
| 5 | `can show` before | Not run in the main session. After a power cycle at 15:13 (transceiver powered), 30 s after boot: `error-active`, error counters 0, all statistics 0 | `151320` | **P** (deviation 1) |
| 6 | csh `ping 6061` | `Reply in 2 [ms]` | csh | **P** |
| 6 | csh `get bench_integer` | 305419896 | csh | **P** |
| 6 | csh `get led_d4` | 0 | csh | **P** |
| 7 | csh `set led_d4 1` | csh `= 1 u08 Rc`; console `PARAM led_d4 = 1: LED D4 on`; `get` returns 1 | csh, `145520` | **P** |
| 7 | csh `set led_d4 0` | csh `= 0 u08 Rc`; console `PARAM led_d4 = 0: LED D4 off`; `get` returns 0 | csh, `145520` | **P** |
| 7 | `set bench_integer 42`, restore | Read back 42, then restored to 305419896 | csh | **P** |
| 8 | `csp ping 6022` | 3 of 3 replies, 2 ms each | `134732` | **P** |
| 8 | `csp ping 6030` | `no reply within 1000 ms` three times while the OBC was off; after it was powered, `reply in 1 ms` (15:09:54) | `133847`, `134732`, `150556` | **P** (deviation 2) |
| 8 | `param get 6022 130 i16` | `value 2800` | `150556` | **P** |
| 8 | `param get 6030 131 u16 0` (and index 1) | `failed (-1)` while the OBC was off; after it was powered, `value 0` for both indexes | `150556` | **P** (deviation 2) |
| 8 | Further reads on 6030 | parameter 1 (`u32`): `45462 (0x0000b196)`; parameter 25 (`u16`): `206` | `150556` | **P** |
| 9 | `param set 6028 120 u8 ... --confirm` and restore | 17 writes of 0, 1 and 2, each `written and read back` with the value written; last write 0 at 14:33:40 | `134732`, `143218` | **P** |
| 10 | `can show` after (main session) | `error-active`, `rx errors` 0, `tx errors` 0, but `form errors` 11847812 and `stuff errors` 1, counted since the boot at 13:38, when the transceiver had no power | `145520` | Void (deviation 4) |
| 10 | `can show` after traffic, after the power cycle | After `csp ping 6022` (2 ms) and `param get 6022 130 i16` (`2900`): `error-active`, error counters 0, all statistics 0 | `151629` | **P** |
| – | FlatSat nodes' own status | No errors or unexpected behaviour reported by the FlatSat side | – | **P** |

The csh LED checks were also made during the main session: the console shows
`PARAM led_d4 = 1` and `= 0` at 13:44, 13:54 and 14:25 to 14:32 (`133847`,
`134732`).

## Deviations

| # | Step | Description | Effect on the result |
|---|---|---|---|
| 1 | 5 | `can show` was not run before the traffic of the main session. It was run after the power cycle of deviation 4 | The reading at 15:14 stands for step 5 |
| 2 | 8 | Node 6030 (OBC) was not powered until about 15:08, so until then it did not answer pings or reads (`failed (-1)`) | None: after it was powered it answered both |
| 3 | 8 | The planned reads were not run in the main session but in the follow-up at 15:06, by hand; `flatsat_console.py --run flatsat_checks.txt` was not used | None |
| 4 | 3, 10 | The transceiver board's power supply was not connected when the TE0715 booted at 13:38; it was connected later, before the first csh traffic (the exact time is not recorded). Without power, the transceiver does not drive the controller's RX input, and the controller counted errors on whatever it saw there: 11847812 form errors and 1 stuff error, the order of what a controller can count at 1 Mbit/s in the few minutes before the supply was connected. These statistics count from boot and are never reset, while the error counters come back down with every correct frame, which is why they read 0 with the controller error-active at 14:58. An unpowered SN65HVD233 leaves the bus alone, and the FlatSat reported no errors. After a power cycle with the transceiver powered (15:13), all statistics read 0 | The main session's step 10 reading is void; steps 5 and 10 repeated after the power cycle pass (`151320`, `151629`) |
| 5 | – | Several console sessions were opened and closed without output (`133156`, `133328`, `133332`, `133823`, `134705`); `133416` started on a board that had already booted | None; the boot is in `133847` |
| 6 | – | At 13:47 a second console (`134712`) was opened while `133847` still had the port. Its `csp ping 6030` is answered in `133847` | None |
| 7 | 9 | `flatsat_checks.txt` gave the type as `u08`, which the TE0715 refuses (`unknown type 'u08'`); the operator used `u8`. Two further commands were refused without effect: one without `--confirm`, one pasted twice on one line | None; `flatsat_checks.txt` corrected afterwards |
| 8 | – | The console host was a Linux laptop, not a Mac, and `flatsat_console.py` was updated between sessions (waiting for the port, then command history) | None on the results |
| 9 | – | csh writes no log; its session was copied from the terminal into `csh-20260924-1457.txt` | The copy is the csh evidence |
| 10 | – | In `150556` one line starts with `[1;32m`: part of a colour code that arrived split over two reads, so the console's log filter missed it | None; filter fixed in `flatsat_console.py` |

## Evidence integrity

| File | sha256 |
|---|---|
| `2026-09-24-flatsat/SHA256SUMS` | `9530963092e482f39bbf56372fa2ef413007d8fc56256316cd1d966556ae1ca2` |
| `2026-09-24-flatsat/flatsat-20260924-133847.log` (boot, LED) | `2e9bbb57ef48d6677bff1af660ac7bdc540a4f4a645118bc4ef8ad579489c3f9` |
| `2026-09-24-flatsat/flatsat-20260924-134732.log` (pings, writes) | `facdc2713027bc3b704da341ae7d4e268a579470e0a467ef40afc5a4a1ba8aa2` |
| `2026-09-24-flatsat/flatsat-20260924-143218.log` (writes) | `1bd98349f77b2b6a0c298a3cd9498b6659381d4e5a624e8bed8a9abcd159085e` |
| `2026-09-24-flatsat/flatsat-20260924-145520.log` (LED, `can show`) | `721349fe2883693e041010a3396e7b09fef7653be3d6cbec8e2fb6d373453e8c` |
| `2026-09-24-flatsat/flatsat-20260924-150556.log` (reads) | `1bbf6f06f95d19f23b4d1377c13fed0292450ef219d48fd617035bc8a79204cd` |
| `2026-09-24-flatsat/flatsat-20260924-151320.log` (clean boot, `can show`) | `544d65fbe552bf836d171c1fa8b507dea40a4a1371c06147087086ab07870f47` |
| `2026-09-24-flatsat/flatsat-20260924-151629.log` (`can show` after traffic) | `6f274d1baebb0e6547415344bb4935d7663eb9a02cee9360144c5e5f4f824e37` |
| `2026-09-24-flatsat/csh-20260924-1457.txt` | `3e216ca6a0700a2b9edad40fbbc9fb85b148c599d760f450db088601b69c970b` |

Check the folder with `shasum -a 256 -c SHA256SUMS` (or `sha256sum -c`) inside it.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-FS-001` Joins the bus without errors | **Verified** | After a boot with the transceiver powered, all statistics 0 before and after TE0715 traffic, and no errors reported by the FlatSat. The earlier form errors were counted while the transceiver had no power (deviation 4) |
| `TE-FS-002` Ping both ways | **Verified** | csh → 6061: 2 ms; 6061 → 6022: 3 × 2 ms |
| `TE-FS-003` csh reads and writes TE0715 parameters, LED | **Verified** | List downloaded; both parameters read and written; `led_d4` switched LED D4 on and off, seen by the operator and confirmed by the console |
| `TE-FS-004` TE0715 reads FlatSat parameters | **Verified** | Planned reads 6022/130 (`2800`) and 6030/131[0] (`0`), further reads on 6030, and the read-backs of 6028 parameter 120 |

## Conclusion

The TE0715 worked on the FlatSat bus in both directions: csh found, read and wrote
its parameters and switched its LED, and the TE0715 pinged, wrote and read FlatSat
nodes. The form errors counted in the main session came from the transceiver board
running without its power supply at first, not from the TE0715's behaviour on the
bus: after a power cycle with it powered, the controller counted no errors before or
after traffic. `TE-FS-001` to `TE-FS-004` are verified.

The FlatSat procedure now checks the transceiver's 3.3 V supply before power-on
(step 1).
