# Configuration

## The CSP node: `te0715.txt` on the SD card

The node and network prefix come, in this order of precedence, from:

| Source | Lasts | Banner and `bench info` say |
|---|---|---|
| `bench start <node> [prefix]` typed within 10 s of boot | this boot only | `bench start` |
| `te0715.txt` on the SD card | until the file changes | `te0715.txt` |
| The image's Kconfig defaults (node 6061, prefix 8) | – | `default` |

`te0715.txt` is a plain text file in the SD card's FAT partition, next to
`zephyr.bin`, with one setting per line:

```text
# TE0715 at the FlatSat
csp_node=6062
csp_prefix=8
```

Both settings are optional; `#` starts a comment, and Windows line ends are fine. A
file that is not exactly understood is refused as a whole (for example a typo such
as `csp_nod=`, or node 0): the board then starts on the defaults and says why:

```text
*** te0715.txt: line 1 not understood; using the defaults ***
```

To change the file:

- **With the card in any computer:** edit or create `te0715.txt` with a text editor.
- **Over JTAG, card in the board:** `app/scripts/sd_install.py config --node 6062`
  (add `--prefix 8` if needed); `sd_install.py config --defaults` writes a file
  without settings.

How it works: Zephyr has no driver for the Zynq's SD card, so `boot.scr` (U-Boot)
reads the file and leaves it in RAM at `0x0f000000` for the application
(`CONFIG_APP_BOOT_CONFIG_ADDR`, `bench_config.h`). The application clears it after
reading, so an image loaded over JTAG afterwards does not pick up an old file. A
JTAG load therefore always starts on the defaults.

## Settings that need a rebuild

The F Prime application's options are Kconfig settings. Change them in
`app/apps/fprime_csp_bench/prj.conf` (add a line such as `CONFIG_APP_CSP_NODE=6062`),
then rebuild and reinstall the image.

| Option | Meaning | Default |
|---|---|---|
| `CONFIG_APP_CSP_NODE` | Default CSP node | 6061 |
| `CONFIG_APP_CSP_NETMASK` | Default network prefix length | 8 |
| `CONFIG_APP_START_WINDOW_S` | Length of the start window in seconds | 10 |
| `CONFIG_APP_CSP_ROUTER_PRIORITY` | F Prime priority of the CSP router task (Zephyr priority 99 minus this) | 45 |
| `CONFIG_APP_BOOT_CONFIG_ADDR` | Where `boot.scr` leaves `te0715.txt`; must match `app/boot/boot.cmd` | `0x0f000000` |

The node 6061 was chosen to lie in the lab51 EGSE router's CAN subnet `6016/8`
(nodes 6016 to 6079), next to the Ubuntu test host 6060. Confirm with the FlatSat
owner which node may be used.

Other settings are fixed in the source:

| Setting | Value | Where |
|---|---|---|
| CAN bitrate | 1 Mbit/s | `app/boards/te0701-can1.overlay` (`bitrate`) |
| Served parameter `bench_integer` | ID 200, `u32`, initial `0x12345678` | `app/apps/fprime_csp_bench/Main.cpp` |
| Served parameter `led_d4` | ID 201, `u8`, initial 0 (LED off) | `app/apps/fprime_csp_bench/shell_cmds.c` (`LED_PARAM_ID`) |
| Parameter list service | port 12 (libparam default) | libparam `vmem_server_loop` |
| CSP version | 2 | fprime-csp-libparam `StackConfig` |
| libparam protocol version and port | 2, port 10 | libparam |
| Console | UART0, 115200 8N1 | board devicetree |
