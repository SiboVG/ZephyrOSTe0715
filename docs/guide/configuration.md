# Configuration

## Settings that can be changed at boot

| Setting | How | Default |
|---|---|---|
| CSP node and network prefix | `bench start <node> [prefix]` within 10 s of boot | 6061, prefix 8 |

The choice is not stored: after a restart the default applies again.

## Settings that need a rebuild

The F Prime application's options are Kconfig settings. Change them in
`app/apps/fprime_csp_bench/prj.conf` (add a line such as `CONFIG_APP_CSP_NODE=6062`),
then rebuild and reinstall the image.

| Option | Meaning | Default |
|---|---|---|
| `CONFIG_APP_CSP_NODE` | Default CSP node | 6061 |
| `CONFIG_APP_CSP_NETMASK` | Default network prefix length | 8 |
| `CONFIG_APP_START_WINDOW_S` | Length of the start window in seconds | 10 |

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
