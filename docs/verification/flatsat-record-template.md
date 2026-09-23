# FlatSat as-run record (template)

Copy this page (for example to `as-run-flatsat-<date>.md`), fill it in during the
[FlatSat test](../tests/flatsat.md), and keep the console log and the csh log next
to it. Record a failure as a failure; add a deviation rather than editing a log.

## Identification

| Field | Entry |
|---|---|
| Test case | TC-09 FlatSat |
| Procedure | `docs/tests/flatsat.md`, revision / date: |
| Date, start time (UTC) | |
| TE0715 operator | |
| FlatSat operator | |
| FlatSat owner's approval of the configuration | name, date: |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier | TE0715-05-71I33-L on TE0701, serial: |
| Transceiver | TCAN-SOIC8-EVM (SN65HVD233); J6 termination fitted? yes / no |
| SD card image | `zephyr.bin` sha256 (from `environment.txt` of the last bench run): |
| Mac, console port | `/dev/cu.usbserial-...B` |
| CAN bitrate | 1 Mbit/s |
| TE0715 CSP node / prefix | |
| FlatSat nodes involved | |
| Approved reads (node, ID, type, index) | |
| Approved writes (node, ID, type, value) | none / |

## Results

Result: **P** pass, **F** fail, **NR** not run (give the reason).

| Step | Check | Expected | Observed | Result |
|---|---|---|---|---|
| 3 | Boot from SD card | `CSP_BENCH_READY` on the agreed node | | |
| 3 | `bench info` | node, `led_d4 (u8) = 0` | | |
| 4 | csh `list download` | `bench_integer` 200, `led_d4` 201 listed | | |
| 4 | (only if the download failed) `list add` fallback | both parameters listed | | |
| 5 | `can show` before | error-active, counters 0 | | |
| 6 | csh `ping <TE0715>` | reply; time: | | |
| 6 | csh `get bench_integer` | 305419896 | | |
| 6 | csh `get led_d4` | 0 | | |
| 7 | csh `set led_d4 1` | LED D4 on; console `led_d4 = 1`; `get` returns 1 | | |
| 7 | csh `set led_d4 0` | LED D4 off; `get` returns 0 | | |
| 7 | (optional) `set bench_integer 42`, restore | read back 42, then 305419896 | | |
| 8 | `csp ping <node>` for each agreed node | reply; times: | | |
| 8 | `param get` for each approved parameter | a plausible value: | | |
| 9 | (only if approved) `param set ... --confirm` and restore | both read back | | |
| 10 | `can show` after | same state and counters as step 5 | | |
| – | FlatSat nodes' own status | no errors or unexpected behaviour reported | | |

## Deviations

| # | Step | Description | Effect on the result |
|---|---|---|---|
| | | | |

## Evidence

| File | sha256 |
|---|---|
| `flatsat-<date>-<time>.log` (console) | |
| csh session log | |

On macOS: `shasum -a 256 <file>`.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-FS-001` Joins the bus without errors | | |
| `TE-FS-002` Ping both ways | | |
| `TE-FS-003` csh reads and writes TE0715 parameters, LED | | |
| `TE-FS-004` TE0715 reads FlatSat parameters | | |

Signed (TE0715 operator), date:
