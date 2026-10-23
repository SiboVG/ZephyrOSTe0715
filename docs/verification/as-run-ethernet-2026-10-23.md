# Ethernet link as-run record 2026-10-23

This record assesses test case
[TC-23](test-cases.md#tc-23-ethernet-link-from-u-boot), the
[Ethernet link](../tests/ethernet.md) check from U-Boot, run on 2026-10-23.

The raw evidence is in `docs/verification/evidence/2026-10-23-1326-tc23/`, one
`uboot_eth_check.py` package per run. It is not edited; this page only refers to it.
Times are the host's local time (CEST, UTC+2), as in the logs.

## Identification

| Field | Entry |
|---|---|
| Test case | TC-23 Ethernet link from U-Boot |
| Procedure and script | `docs/tests/ethernet.md` and `app/scripts/uboot_eth_check.py` at `35b3ba4`; TC-23 amended before run 2 (deviation 1) |
| Date, time | 2026-10-23: run 1 at 13:26, run 2 at 13:28 |
| Operator | Set-up (cable, adapter) by S. Van Gool (SVG); runs executed by Claude Code on SVG's request, on SVG's bench host |

## Assets and configuration

| Item | Entry |
|---|---|
| TE0715 module / carrier | The bench's TE0715-05-71I33-L on its TE0701 (the asset set of [Requirements](requirements.md)) |
| Boot | SD card: FSBL and U-Boot 2022.01 (Apr 04 2022) from `BOOT.BIN`; the Zephyr image on the card (`v4.4.2-6-g70b56a29cd74`) only runs between the runs |
| Host | Ubuntu 26.04 LTS, kernel 7.0.0-34-generic |
| Host test port | `enxa0cec8ebc610`: USB 3 Realtek RTL8153 gigabit adapter, driver `r8152`, firmware `rtl8153a-4 v3 06/12/25`, MAC `a0:ce:c8:eb:c6:10`; NetworkManager profile `te0715-eth`, 192.168.70.1/24, no default route, IPv6 off |
| Cable | Direct, TE0701 RJ45 to the adapter, no switch |
| Board address | 192.168.70.2/24, set in U-Boot's environment in RAM only |
| Board MAC | `fc:0f:e7:e6:16:e8`, from U-Boot's environment (not set by the script) |
| Reset | `--reboot`: `kernel reboot cold` on the image's shell (no `xsdb` on this host) |
| Host firewall | ufw, firewalld and nftables inactive; `icmp_echo_ignore_all = 0` |

## Results

Result: **P** pass, **F** fail, **NR** not run, **Info** run for information, no verdict.

| Run | Check | Observed | Result |
|---|---|---|---|
| 2 (100 Mbit/s) | Host port advertisement | `ethtool`: advertised `100baseT/Full` only; link 100 Mbit/s full before the run | **P** |
| 2 | Pings | 10 of 10 `host 192.168.70.1 is alive` | **P** |
| 2 | Host carrier after the pings | up | **P** |
| 2 | Host traffic | 20 packets received on the test port during the run | **P** |
| 2 | Host receive errors | `rx_errors`, `rx_crc_errors`, `rx_frame_errors` 0 before and after | **P** |
| 2 | Speed and duplex | Host 100 Mbit/s full; PHY Copper Specific Status 1 `0x6C08`: 100 Mbit/s, full duplex, resolved, link up | **P** |
| 2 | Script verdict | `PASS`, exit status 0 | **P** |
| 1 (1000 Mbit/s) | All of the above at 1000 Mbit/s | 10 of 10 pings; host 1000 Mbit/s full; PHY `0xAC48`: 1000 Mbit/s, full duplex, resolved, link up; 20 packets received; no receive errors; `PASS` | **Info** (**P** against TC-23 as of `35b3ba4`) |

Recorded in both runs:

| Item | Observed |
|---|---|
| PHY | `mii info`: address 0x00, OUI 0x5043, model 0x1D, revision 1: a Marvell 88E151x |
| U-Boot banner | `ZYNQ GEM: e000b000, mdio bus e000b000, phyaddr 0, interface rgmii-id`, then `Failed to read eth PHY id, err: -2`, then `eth0: ethernet@e000b000` |
| `mii info` link fields | `10baseT, HDX`, read before the first ping, when U-Boot has not started the link yet. The status read after the pings shows the negotiated link |

## Deviations

| # | Step | Description | Effect on the result |
|---|---|---|---|
| 1 | Procedure | TC-23 at `35b3ba4` required two runs, 1000 Mbit/s (step 1) and 100 Mbit/s (step 2). After run 1, the project set 100 Mbit/s full duplex as CubeSpec's baseline Ethernet speed, also on the FlatSat (SVG, 2026-10-23). `TE-ETH-001` and TC-23 were amended before run 2: the 100 Mbit/s run is required, a 1000 Mbit/s run is for information. The criteria of the 100 Mbit/s run are those of step 2 at `35b3ba4`, unchanged | None: run 2 is assessed against unchanged criteria; run 1 passed its original criteria and is kept as information |
| 2 | Run 2 | The host port was limited to 100 Mbit/s with the NetworkManager profile (`802-3-ethernet.auto-negotiate yes`, `speed 100`, `duplex full`) instead of `ethtool`, which needs root. `ethtool` confirmed that only `100baseT/Full` was advertised | None |
| 3 | – | The optional `tcpdump` capture was not made (needs root) | None: the host counters and U-Boot's ping results decide the criteria |

## Evidence integrity

| File | sha256 |
|---|---|
| `2026-10-23-1326-tc23/run2-100mbit/SHA256SUMS` | `d64f626828f8d180dbf80b2f76d4db98fc543c4a342f16799013783e5ae79e3d` |
| `2026-10-23-1326-tc23/run2-100mbit/console.log` | `0b8eb1dacc822a8af837eaed2c0476ce965d529e4f2a6a48fd0f07615f3896b7` |
| `2026-10-23-1326-tc23/run2-100mbit/summary.txt` | `51590cda78605cd6c3b467d131b4e832b325a0e21b56b0ec255470e199c43af7` |
| `2026-10-23-1326-tc23/run1-1000mbit/SHA256SUMS` | `efaf23d6e0c66c574b25643a03b73b27b48a0f5d8bac29659978383497ce6eea` |
| `2026-10-23-1326-tc23/run1-1000mbit/console.log` | `aa6fd0d14aa4d612ccdce283b18fcd9270915f6e1c53f02f3c7378db108103a5` |
| `2026-10-23-1326-tc23/run1-1000mbit/summary.txt` | `14d2e70034246ae28427c20242b7f5972a6dd717da7969663d931011286acaca` |

Check each run's folder with `sha256sum -c SHA256SUMS` inside it.

## Assessment

| Requirement | Result | Remark |
|---|---|---|
| `TE-ETH-001` Ethernet path at 100 Mbit/s full duplex | **Verified** | Run 2: frames both ways (ARP and ICMP echo), 100 Mbit/s full duplex on both ends, no host receive errors. Run 1 shows the same path clean at 1000 Mbit/s |

## Conclusion

The TE0715's Ethernet hardware path works: the PHY is a Marvell 88E151x at MDIO
address 0, and the link carries traffic without errors at 100 Mbit/s, the baseline,
and also at 1000 Mbit/s. U-Boot's `Failed to read eth PHY id` warning is harmless:
the PHY is at the address U-Boot uses. `TE-ETH-001` is verified.

For the Zephyr side this fixes:

- **Speed:** 100 Mbit/s, which is also the `link-speed` default of Zephyr's Zynq-7000
  devicetree for the GEM.
- **PHY:** an 88E151x, which Zephyr's Xilinx GEM driver manages itself; at address 0,
  or found by its address auto-detection.
- **MAC address:** the board's MAC address lives in U-Boot's environment
  (`fc:0f:e7:e6:16:e8`). Zephyr, started with `go`, does not see that environment, so
  the Zephyr image needs its own way to obtain it.
