# Zephyr Ethernet as-run record 2026-10-23

This record assesses test case
[TC-24](test-cases.md#tc-24-zephyr-ethernet-bring-up), Zephyr's Ethernet on the TE0715
([Ethernet link, Zephyr: TC-24](../tests/ethernet.md#zephyr-tc-24)), run on 2026-10-23.
The first attempt failed; the defects it exposed were diagnosed on the board, fixed,
and TC-24 was run again with its criteria unchanged.

The raw evidence is in two folders under `docs/verification/evidence/`. It is not
edited; this page only refers to it. Times are the host's local time (CEST, UTC+2).

| Folder | Contents |
|---|---|
| `2026-10-23-1409-tc24/` | The failed first attempt (`load.log`) and the diagnostic loads (`diag-load*.log`, with the hashes of the images loaded) |
| `2026-10-23-1652-tc24-run/` | The passing run: `environment.txt`, `load.log` (step 1), `check/` (step 2, the `zephyr_eth_check.py` package) |

## Identification

| Field | Entry |
|---|---|
| Test case | TC-24 Zephyr Ethernet bring-up, as specified at `5c4ae2c` (unchanged since) |
| Attempt 1 | 14:09, image built from `5c4ae2c` |
| Run | 16:52 to 16:54, image built from `e086600` (`zephyr.bin` sha256 `473bcc8b...92ff9`, see `environment.txt`) |
| Operator | Set-up (cable, adapter, the udev rule for the JTAG reset) by S. Van Gool (SVG); loads, diagnosis and runs by Claude Code on SVG's request, on SVG's bench host |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier | The bench's TE0715-05-71I33-L on its TE0701, as in the [TC-23 record](as-run-ethernet-2026-10-23.md) |
| Image | `apps/eth_bringup`: Zephyr `70b56a29` with the workspace's Zephyr patches `0001` to `0003`; 192.168.70.2/24; MAC `02:00:00:07:15:01` (`mac.overlay`) |
| Loading | `uboot_load.py` (XMODEM through U-Boot) from the SD card image's shell; CRC32 of every load checked by U-Boot against the file |
| Host | Ubuntu 26.04 LTS, kernel 7.0.0-34-generic; test port `enxa0cec8ebc610` (RTL8153, `r8152`), NetworkManager profile `te0715-eth`: 192.168.70.1/24, advertising 100baseT/Full only |
| Cable | Direct, TE0701 RJ45 to the adapter, no switch |
| Reset | From 15:19: OpenOCD through the Digilent cable (`support/openocd.cfg`, `te0715_reset`); before that only by hand |

## Attempt 1 and diagnosis

| Time | Load (`2026-10-23-1409-tc24/`) | Observed | Conclusion |
|---|---|---|---|
| 14:09 | `load.log`: `eth_bringup` from `5c4ae2c` | CRC32 matched; after `go 0x0` no output at all; the board stopped answering | Attempt 1: **F** (no `[ETH_BRINGUP_READY]`) |
| – | – | The image routed `printk` and logs through the shell's log backend, which prints nothing until the shell runs: a fault before the shell left no trace | `prj.conf`: logs straight to the UART; `debug.conf`: a trace line per init level |
| 14:18 | `diag-load.log`: debug image | The board was power-cycled by hand during the transfer; XMODEM aborted; the board booted its SD card image | Void (set-up) |
| 14:24 | `diag-load-2.log`: debug image | `post-kernel: before the drivers`, then `DATA ABORT`, `1st Level Translation Fault @ 0xf8000140`, PC in `eth_xlnx_gem_configure_clocks()`; halted | Defect 1: the GEM driver's clock register (SLCR `GEM0_CLK_CTRL`) is accessed unmapped |
| 14:28, 14:44 | `diag-load-3.log`, `diag-load-4.log` | Loaders waiting for a reset by hand; none came | Nothing loaded |
| 15:20 | `diag-load-5.log`: debug image with Zephyr patch `0002` | Boots; `PHY not managed by the driver or no compatible PHY detected, assuming link up at 100 MBit/s`; then `error bit(s) set in Interrupt Status Reg.: 0x00000800` every few seconds | Defect 1 fixed. Defect 2: no `init-mdio-phy` in the board file. Defect 3: `hresp_not_ok`, the GEM's DMA memory (rings at `0x2e000`, buffers at `0x34000`) below DDR `0x80000`, out of the GEM's reach (UG585, table 4-1) |
| 16:47 | `diag-load-6.log`: debug image with patches `0002`, `0003` and `init-mdio-phy` | `link up, 100 MBit/s` from the driver; no interrupt status errors; 5 of 5 informal pings at 56, 470 and 1472 bytes, host receive errors 0 | Defects 2 and 3 fixed |

The changes were committed as `e086600` before the run: the two Zephyr patches,
`init-mdio-phy`, the UART log backend and the reboot on a fatal error in
`eth_bringup`, `debug.conf`, the OpenOCD reset and the documentation. The pass criteria
of TC-24 were not changed.

## Results of the run

Result: **P** pass, **F** fail.

| Step | Check | Observed | Result |
|---|---|---|---|
| 1 | `[ETH_BRINGUP_READY]` with `carrier=on` within 10 s | `link up, 100 MBit/s` at 2.017 s, then `[ETH_BRINGUP_READY] carrier=on mac=02:00:00:07:15:01 ipv4=192.168.70.2` | **P** |
| 2 | Board interface | `net iface`: `oper=UP, admin=UP, carrier=ON`, 192.168.70.2 assigned, MTU 1500 | **P** |
| 2 | Host link | 100 Mbit/s full duplex, carrier up | **P** |
| 2 | Host to board, 56, 469, 470, 471, 981, 982, 983 and 1472 bytes, don't-fragment | 100 of 100 at every size | **P** |
| 2 | Board to host, 4 and 1472 bytes | 10 of 10 each | **P** |
| 2 | Host receive errors | `rx_errors`, `rx_crc_errors`, `rx_frame_errors` 0 before and after; 824 packets received | **P** |
| 2 | Script verdict | `PASS`, exit status 0 | **P** |
| – | Board `net stats` (recorded) | IPv4 and ICMP received 820, sent 820, dropped 0; no IP, ICMP or processing errors | – |

## Deviations

| # | Step | Description | Effect on the result |
|---|---|---|---|
| 1 | All | Attempt 1 failed: the image halted before its banner. The design was corrected (two Zephyr driver patches, the board's PHY management, the image's logging) and TC-24 was repeated on the corrected revision | Attempt 1 is a failure on `5c4ae2c`; the run on `e086600` is assessed against the unchanged criteria |
| 2 | – | The diagnostic images (`debug.conf`) are not the image under test; their loads are diagnosis, not part of TC-24 | None on the run |
| 3 | – | The board was reset by hand twice (one power cycle aborted the 14:18 load) and from 15:19 over JTAG with OpenOCD, which the procedure does not describe for TC-24 | None: the run started from a reset over JTAG and a load as in the procedure |
| 4 | – | A second agent session working on the same task was paused before the run; during the run only this session used the serial port and the test port | None |

## Evidence integrity

| File | sha256 |
|---|---|
| `2026-10-23-1652-tc24-run/SHA256SUMS` | `9ec29616fa3435a1f73552b469fca2bee748847f6fe993d5ae39f7b3b2065a18` |
| `2026-10-23-1652-tc24-run/environment.txt` | `32fc56e094c13d3ca04cc0888fe803038391e70d2a7be673fded940574cd7a9d` |
| `2026-10-23-1652-tc24-run/load.log` | `22086bd8b1dd9fbabc0a6810a0c92d893eb65ec76ca46e8a4ea651703f76de6c` |
| `2026-10-23-1652-tc24-run/check/SHA256SUMS` | `57878fd1db80cefeae1e168251a4859dd3e6a3e637d2d330ce9fbd8979c9b1cf` |
| `2026-10-23-1652-tc24-run/check/summary.txt` | `e028e9734d1149f16e7330a7495a3875f8e4296c668cc42612533950ef73850c` |
| `2026-10-23-1652-tc24-run/check/host-ping.txt` | `79bf23f955e4dfdec26dac72add35e0df2f05f2e7ec4d2737172761f81575fc4` |
| `2026-10-23-1652-tc24-run/check/console.log` | `6102771161f8c4b09f55d614c1e0445ceda0d558320caf3f0e03e0b261714e17` |
| `2026-10-23-1409-tc24/SHA256SUMS` | `c8c7e121507a7470f3a5248f467ba8583c622d64ea7a0da6c71fbc36f598e4ea` |
| `2026-10-23-1409-tc24/load.log` (attempt 1) | `256af3c093b77c656739f148d77d947325cb89046494502804cc556c4d252396` |
| `2026-10-23-1409-tc24/diag-load-2.log` (the fault) | `d1fa650a1a59b09b65a68e916ccd41cdf8435b656b84381074fb992f6881997e` |
| `2026-10-23-1409-tc24/diag-load-5.log` | `2a27d04c12f993fd717e7e637849389743e85d6644e6dcbd129332319ee6f707` |
| `2026-10-23-1409-tc24/diag-load-6.log` | `7e5352938c860aaed65e995a703faaa7c5f2cfee8dbfc4246a156af82875bf89` |

Check each folder with `sha256sum -c SHA256SUMS` inside it.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-ETH-002` Zephyr Ethernet at 100 Mbit/s full duplex, echo both ways up to the MTU, across the 512-byte buffer boundaries, no loss or host receive errors | **Verified** | On `e086600`; attempt 1 on `5c4ae2c` failed (deviation 1) |

## Conclusion

Zephyr's Ethernet works on the TE0715 at the 100 Mbit/s baseline. Every frame size
class from 98 to 1514 bytes crossed the link both ways without loss, and the board's
own counters show no drop or error. It took two fixes to Zephyr's Xilinx GEM driver,
kept as workspace patches: the driver's clock register is now mapped (upstream fixed
this in a larger rework), and on the Zynq-7000 its DMA memory is in the OCM, the
only memory below DDR address `0x80000` the controller can reach (still unfixed on
upstream `main`). The board file now lets the driver manage the PHY.

Open for the next step: the image uses a locally administered MAC address; the
module's own address is in U-Boot's environment and not yet available to Zephyr.
