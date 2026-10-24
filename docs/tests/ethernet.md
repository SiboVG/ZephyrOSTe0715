# Ethernet link

This is the first step towards CSP over Ethernet: it checks the TE0715's Ethernet
hardware path on its own, from U-Boot, before any Zephyr networking exists. U-Boot's
Zynq Ethernet driver is known to work, so a pass shows that the cable, the PHY on the
module, the TE0701's RJ45 jack and the processor's Ethernet set-up are sound. A
problem found later under Zephyr is then a software problem. This is test case
[TC-23](../verification/test-cases.md#tc-23-ethernet-link-from-u-boot), which verifies
`TE-ETH-001`.

The link runs at **100 Mbit/s full duplex**, CubeSpec's baseline Ethernet speed, on the
bench and on the FlatSat. A 1000 Mbit/s run can be added for information.

What is already known, from the processor set-up and the boot log:

| Item | State |
|---|---|
| Ethernet pins | GEM0 on MIO16–27 (RGMII) and MDIO on MIO52/53, set by the FSBL (`ps7_init.tcl`) |
| Ethernet clock | IO PLL 1000 MHz / 8 = 125 MHz (1000 Mbit/s); U-Boot adapts it to the negotiated speed |
| U-Boot's view | Every boot log prints `ZYNQ GEM: e000b000, mdio bus e000b000, phyaddr 0, interface rgmii-id`, then `Failed to read eth PHY id, err: -2`. Either the PHY is not at address 0, it is still in reset when U-Boot looks, or the warning is harmless. TC-23 finds out: `mii info` lists the address where the PHY answers |

## Equipment

| Item | Details |
|---|---|
| Host Ethernet port | Used only for this test. A USB 3 gigabit Ethernet adapter is the easiest: the host's built-in port stays on the lab network. A 100 Mbit/s port is enough; a gigabit one also allows the optional 1000 Mbit/s run |
| Cable | Cat5e or Cat6. A straight cable is fine; the PHYs swap pairs by themselves. The optional 1000 Mbit/s run needs all four pairs |
| Console | The usual JTAG/UART micro-USB cable ([Connecting to the board](../guide/connect.md)) |
| SD card | Any image that boots through U-Boot, such as the FlatSat image. Nothing on the card is changed |

The CAN transceiver and the Kvaser are not needed.

## 1. Connect

With the TE0701 powered off:

1. Connect the cable from the TE0701's RJ45 jack to the host test port. Do not go
   through a switch or the lab network: the test needs the two ends alone on the link.
2. Connect the JTAG/UART cable as usual.

Find the test port's name. Compare the list before and after plugging in the adapter:

```bash
ip -br link
# enp1s0           UP    54:bf:64:86:eb:cd ...   the built-in port, on the lab LAN
# enx00e04c680001  DOWN  00:e0:4c:68:00:01 ...   the adapter: the test port
```

The examples below use `enx00e04c680001`; use your own name.

## 2. Give the test port its address

The host is 192.168.70.1/24 and the board 192.168.70.2. Check first that
192.168.70.0/24 is not used anywhere on the lab network; pass other addresses with
`--host-ip`, `--board-ip` and `--prefix` if it is.

With NetworkManager (Ubuntu desktop), create a profile once. It keeps the address
across reconnects, never makes this port the default route, and limits the link to
100 Mbit/s full duplex (only that mode is advertised). It replaces the DHCP profile
NetworkManager creates for a new adapter. On a desktop session `nmcli` usually needs
no `sudo`:

```bash
nmcli connection add type ethernet ifname enx00e04c680001 con-name te0715-eth \
    ipv4.method manual ipv4.addresses 192.168.70.1/24 ipv4.never-default yes \
    ipv6.method disabled connection.autoconnect-priority 10 \
    802-3-ethernet.auto-negotiate yes 802-3-ethernet.speed 100 802-3-ethernet.duplex full
nmcli connection up te0715-eth
```

Without NetworkManager:

```bash
sudo ip addr add 192.168.70.1/24 dev enx00e04c680001
sudo ip link set enx00e04c680001 up
sudo ethtool -s enx00e04c680001 speed 100 duplex full autoneg on
```

Check with `ip -br addr show enx00e04c680001` and `ethtool enx00e04c680001`
(advertised: `100baseT/Full` only). The link may already be up while the board runs
its image: its PHY negotiates by itself once powered.

Ubuntu's firewall (ufw) answers pings by default. If the host does not answer during
the test, check `sudo ufw status verbose` and any other firewall on the host.

## 3. Run at 100 Mbit/s

```bash
app/scripts/uboot_eth_check.py --host-if enx00e04c680001 --expect-speed 100 --reboot
```

The script refuses to start, without touching the board, if the test port does not
carry the host address, if another host interface is in the test subnet, or if the
settings do not make sense. Then it:

1. resets the board and stops U-Boot at its prompt. `--reboot` sends `kernel reboot cold`
   to the image's serial shell; without it the script resets the board over JTAG
   (needs `xsdb`). With neither, `--wait-reset 60` waits 60 s for the reset button or
   power-on;
2. sets the board's address in U-Boot's environment, in RAM only. If U-Boot has no MAC
   address, it uses the locally administered `02:00:00:07:15:01` (`--mac` to change).
   Nothing is saved: the script never runs `saveenv` and writes nothing to the card;
3. lists the PHYs on the MDIO bus with `mii info`;
4. pings the host 10 times from U-Boot;
5. reads the PHY's negotiated speed and duplex (Marvell 88E151x, Copper Specific
   Status Register 1);
6. compares the host port's receive counters before and after.

To watch the traffic, run this in a second terminal before starting the script:

```bash
sudo tcpdump -eni enx00e04c680001 arp or icmp
```

It shows the board's ARP request (with its MAC address), the host's reply, and the
10 echo requests and replies.

A passing run ends like this:

```text
board MAC: fc:0f:e7:e6:16:e8 (environment)
U-Boot: U-Boot 2022.01 (Apr 04 2022 - 07:53:54 +0000)
U-Boot: ZYNQ GEM: e000b000, mdio bus e000b000, phyaddr 0, interface rgmii-id
PHY 0x00: OUI 0x5043 model 0x1d rev 1 (Marvell 88E151x)
pings: ..........
...
PASS  pings answered: 10 of 10
PASS  host carrier after the pings: up
PASS  host received the traffic: 20 packets received on enx00e04c680001
PASS  no host receive errors: none
PASS  full duplex at the expected speed: host 100 Mbit/s full duplex (expected 100 full); PHY 100 Mbit/s full duplex, link up
PASS
evidence: eth-check-20261023-141502/; the board is at the U-Boot prompt: reset or power-cycle it
```

The TE0715 on this bench has its PHY, a Marvell 88E151x, at address 0, and U-Boot
takes the MAC address `fc:0f:e7:e6:16:e8` from its environment. U-Boot's
`Failed to read eth PHY id` warning is therefore harmless.

## 4. Optional: 1000 Mbit/s

For information only, not required by `TE-ETH-001`. Let the port advertise
1000 Mbit/s, run with `--expect-speed 1000`, and set it back to the baseline:

```bash
nmcli connection modify te0715-eth 802-3-ethernet.speed 1000
nmcli connection up te0715-eth
app/scripts/uboot_eth_check.py --host-if enx00e04c680001 --expect-speed 1000 --reboot
nmcli connection modify te0715-eth 802-3-ethernet.speed 100
nmcli connection up te0715-eth
```

## 5. Finish

The script leaves the board at the U-Boot prompt. Type `reset` there, or reset or
power-cycle the board, to boot its image again. Record the runs in an as-run record; each run's evidence directory holds `console.log` (everything U-Boot printed),
`summary.txt` (settings, PHY, MAC, counters, criteria) and `SHA256SUMS`. The pass
criteria are fixed in [TC-23](../verification/test-cases.md#tc-23-ethernet-link-from-u-boot);
do not change them after a run.

## Reading a failure

| What `summary.txt` shows | Look at |
|---|---|
| `PHY: none listed by mii info` and no pings answered | The cable and the jack's link LEDs; whether the PHY is held in reset; the U-Boot banner. If U-Boot has no `mii` command, the pings and the host side still decide the test |
| A PHY at another address than 0 | Expected if U-Boot's warning was the address: record it, Zephyr will need it (or its address auto-detection) |
| A PHY that is not a Marvell 88E151x | Record the identity: Zephyr's Xilinx GEM driver only manages the Marvell 88E1111 and 88E151x and the TI TLK105 and DP83822 itself |
| Host carrier down after the pings | Cable, jack, adapter; `ethtool enx00e04c680001` on the host |
| Pings lost and `rx_crc_errors` or `rx_frame_errors` rising | Frames corrupted on the way from the board: the cable, or RGMII timing between the processor and the PHY (much more critical at 1000 Mbit/s) |
| Pings lost, no receive errors, few packets received | The host did not get the board's frames: the address on the test port, the firewall, the cable |
| Pings answered but `host received the traffic` fails | The replies left through another interface: check the host's addresses and routes (`ip route get 192.168.70.2`) |
| A speed other than expected | The host port's advertised modes (`ethtool enx00e04c680001`); for 1000 Mbit/s, a cable with all four pairs and a gigabit adapter |

## Zephyr: TC-24

[TC-24](../verification/test-cases.md#tc-24-zephyr-ethernet-bring-up) verifies
`TE-ETH-002`: Zephyr's own Ethernet driver on the same link, with the same cabling and
host port (100 Mbit/s full duplex). The image is `apps/eth_bringup`. It has the board's
GEM0 settings (`te0715.dts`: PHY at address 0, MDC at 2.31 MHz, 100 Mbit/s), the static
address 192.168.70.2/24, the locally administered MAC address `02:00:00:07:15:01`
(`app/boards/te0715-mac.overlay`), and the network and kernel shells.

The board's Ethernet needs two Zephyr patches, applied by `west patch apply`: `0002`
maps the driver's clock register, without which the image halts at boot, and `0003`
puts its DMA memory in the OCM, the only memory below DDR address `0x80000` the
controller can reach. The board file lets the driver manage the PHY (`init-mdio-phy`).
Build the image:

```bash
west build -b te0715 app/apps/eth_bringup -d build/eth_bringup
```

If an image stops before its banner, build it with `debug.conf`: it prints a line at
each initialization level and logs immediately, so a fault during driver
initialization shows (`-- -DEXTRA_CONF_FILE=debug.conf`). The image reboots the board
after a fatal error, so the board comes back to its SD card image instead of halting.

Load it over JTAG as usual, or, without `xsdb`, through U-Boot from the running image's
shell. If no image with a shell runs, reset the board first ([Resetting with
OpenOCD](../guide/boot.md#resetting-with-openocd)). `uboot_load.py` reboots the board, sends the image with XMODEM and starts it
(needs `pip install pyserial xmodem`):

```bash
app/scripts/uboot_load.py --port /dev/serial/by-id/usb-Digilent_*-if01-port0 \
    --bin build/eth_bringup/zephyr/zephyr.bin --log load.log \
    --until "[ETH_BRINGUP_READY] carrier=on"
```

The image waits up to 10 s for the link and then prints one line:

```text
[ETH_BRINGUP_READY] carrier=on mac=02:00:00:07:15:01 ipv4=192.168.70.2 waited_ms=...
```

With `carrier=off` the load step fails: check the cable and the host port first.
Then run the check, with the board's shell free (no other program on the serial port):

```bash
app/scripts/zephyr_eth_check.py --host-if enx00e04c680001
```

It reads `net iface` on the board, pings the board from the host 100 times at each
payload size (56, 469 to 471, 981 to 983 and 1472 bytes, with the don't-fragment flag:
frames on either side of one and two 512-byte driver buffers, and the largest frame),
pings the host from the board's shell 10 times with 4 and with 1472 bytes, keeps
`net stats`, and compares the host port's counters. It writes `console.log`,
`host-ping.txt`, `summary.txt` and `SHA256SUMS`, and ends with `PASS` or `FAIL`.

Keep `load.log` with the package: it holds the boot and the `[ETH_BRINGUP_READY]` line.
The image stays in RAM only; reset the board to boot its SD card image again.

## CSP and libparam over Ethernet: TC-25

[TC-25](../verification/test-cases.md#tc-25-csp-and-libparam-over-ethernet) verifies
`TE-ETH-003` and `TE-ETH-004`: the F Prime CSP bench server (`apps/fprime_csp_bench`)
built with `udp.conf` carries CSP over UDP (fprime-csp-libparam's `UdpTransport`, the
datagram format of csh's `csp add udp`) instead of CAN. The Linux side is the bench's
`CspBench --udp` and, for an independent implementation of the format, `CspPingClient
--udp`, which is plain libcsp with libcsp's own `csp_if_udp`. Build both (CspLibparamFprimeTest)
and the image ([Building and running](../getting-started/build-and-run.md)), load the image
and wait for the server, which starts on its default node 6061 after the 10 s window:

```bash
app/scripts/uboot_load.py --port /dev/serial/by-id/usb-Digilent_*-if01-port0 \
    --bin app/apps/fprime_csp_bench/build-fprime-udp/zephyr/zephyr.bin --log load.log \
    --until "[CSP_BENCH_READY]"
app/scripts/fprime_e2e.py --attach --udp 192.168.70.2 \
    --bench <CspBench> --reference <CspPingClient> --log e2e.log
```

`--attach` uses the server that is already running (no JTAG). The script runs the
CspBench client test against the board (parameter 200, then `led_d4`), pings it from
plain libcsp, starts a Linux CspBench server (node 102) and runs the TC-07 shell checks
from the board. Every check prints `PASS` or `FAIL`.

## Next steps

Once TC-25 passes, the FlatSat follows: either the EGSE router reaches the TE0715 with
`csp add udp`, or this host routes between its UDP link and the lab's ZMQ hub. Its
requirements and test cases are added before that work starts.
