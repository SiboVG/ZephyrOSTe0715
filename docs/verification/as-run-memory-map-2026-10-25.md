# System RAM above the CPU-only DDR as-run record 2026-10-25

This record covers test case
[TC-26](test-cases.md#tc-26-system-ram-above-the-cpu-only-ddr), run on 2026-10-25. TC-26
checks that Zephyr's system RAM now starts at `0x100000`, above the DDR that only the CPUs
can reach, and that Ethernet works without Zephyr patch `0003`. That patch had placed the
GEM's DMA memory in the OCM. Steps 3 and 4 repeat TC-24 and TC-25 on images linked at the
new base.

The raw evidence is in `docs/verification/evidence/2026-10-25-1941-tc26/`. This page only
refers to it; the evidence itself is not edited. Times are the host's local time (CET,
UTC+1).

## Identification

| Field | Entry |
|---|---|
| Test case | TC-26 System RAM above the CPU-only DDR, as specified at `5343b31` |
| Date, time | 2026-10-25, 19:41 to 19:46 |
| Revisions | zephyr-te0715 `5343b31`, with Zephyr `70b56a29` and workspace patches `0001` and `0002` only (`0003` removed; `environment.txt`). fprime-csp-libparam UDP sources as merged in `478420b`. Linux binaries as for TC-25 (CspLibparamFprimeTest `1cd24aa`) |
| Images | `apps/eth_bringup`: `zephyr.bin` sha256 `d00d70b7...757e9c`. `apps/fprime_csp_bench` with `udp.conf`: `1646ec73...4fc105` |
| Operator | Claude Code ran the steps on SVG's request, on SVG's bench host. No step was manual |

## Assets and configuration

These are the same as in the [TC-25 record](as-run-csp-ethernet-2026-10-23.md):

- direct cable;
- host port `enxa0cec8ebc610` at 100 Mbit/s full duplex, address 192.168.70.1/24;
- board at 192.168.70.2, MAC `02:00:00:07:15:01`, CSP node 6061/8.

Both images were loaded from the running image's shell with `uboot_load.py`. U-Boot ran
`loadx 0x100000`, checked the image with `crc32` and started it with `go 0x100000`.

## Results

Each step is marked **P** (pass) or **F** (fail).

| Step | Check | Observed | Result |
|---|---|---|---|
| 1 | `test_memory_map.py` | 6 of 6 passed (`host/pytest.txt`) | **P** |
| 2 | Section and symbol layout | Both images: lowest allocated section `rom_start` at `0x100000`; none below. `eth_bringup`: `eth_xlnx_gem0_bd_rings` `0x12f000`, `eth_xlnx_gem0_dma_area` `0x138000`. `fprime_csp_bench`: `0x16b000` and `0x174000`. All in DDR, none in the OCM (`host/layout-*.txt`) | **P** |
| 3 | TC-24 on `eth_bringup` | Started at `0x100000` (CRC32 matched); `link up, 100 MBit/s` at 2.016 s; `[ETH_BRINGUP_READY] carrier=on ... ipv4=192.168.70.2`. Check: 100 of 100 at every host payload size, 10 of 10 for each board ping series, no host receive errors, `PASS`. No `Interrupt Status Reg.` error in the load or check console logs | **P** |
| 4 | TC-25 on `fprime_csp_bench` (`udp.conf`) | Started at `0x100000` (CRC32 matched); `[CSP_BENCH_READY] role=server udp=192.168.70.1:9220 node=6061`. Script: `14/14 checks passed`, including client 5 of 5, `led_d4` on and off twice, and a reference `csp_if_udp` ping of 1 ms | **P** |

## Deviations

None.

TC-26 does not rerun the SD card boot (TC-08). That step needs xsdb, which this host
lacks, to write the card, and the card still holds the previous pair of `boot.scr` and
`zephyr.bin`, both at address 0. That pair stays consistent and boots as before. The next
`sd_install.py install` writes both files for `0x100000`, and TC-08 should then be rerun.

## Evidence integrity

| File | sha256 |
|---|---|
| `2026-10-25-1941-tc26/SHA256SUMS` | `ed109b45d7d233be9484c1433f6143d600fa57a2dbc6ee94391b5018f7c19d54` |
| `2026-10-25-1941-tc26/environment.txt` | `16b46821b02362bd03490af8aaa810ff8e4a4426d68f18b0073dd09be88ba94a` |
| `2026-10-25-1941-tc26/host/pytest.txt` | `b52fb6cdb8ed75e5b0f009ee5b1eaa32935c1485ef00b89800bbab7bc46b392a` |
| `2026-10-25-1941-tc26/host/layout-summary.txt` | `060f418b11ea600322ad0916e7932d7cff3cd87b34820ec095701b8e87039949` |
| `2026-10-25-1941-tc26/tc24/load.log` | `4db4ee0e81a9c4861507b30c8fe0adb5612fa219def580e412a9aa88fbdb8551` |
| `2026-10-25-1941-tc26/tc24/check/summary.txt` | `8f95b1fe3c6a1848b421fd4cab332c69364222d3a9e91c39521dbc756c0b594d` |
| `2026-10-25-1941-tc26/tc25/load.log` | `1a4afde3473ad492b4ffa0ea71f4b8aec238787bc8dabacc5b082679343c3c1c` |
| `2026-10-25-1941-tc26/tc25/e2e.log` | `edd03cb6f868c080581fb1b5c06d4bead96d2091b03514f9c5b5179201cba135` |

To check the folder, run `sha256sum -c SHA256SUMS` inside it.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-BSP-004` System RAM only in DDR that every bus master reaches, images loaded there | **Verified** | Board file and both load paths checked. Both images are laid out at and above `0x100000`. Both started from `0x100000` over U-Boot |
| `TE-ETH-002`, `TE-ETH-003`, `TE-ETH-004` (regression) | **Still met** | TC-24 and TC-25 passed on the new memory map without patch `0003` |

## Conclusion

The GEM's DMA works with its rings and buffers in ordinary system RAM. The fault behind
patch `0003` came from the board's memory map, not from the driver: the system RAM
started at DDR address 0. With the system RAM starting at `0x100000`, the TE0715 needs no
change to the Zephyr GEM driver for DMA. This matches the upstream maintainer's view in
[zephyr#123456](https://github.com/zephyrproject-rtos/zephyr/issues/123456).
