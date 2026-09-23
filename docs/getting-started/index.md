# The workspace

Everything is organised as a Zephyr **west workspace**: one directory that holds
Zephyr itself, the extra modules this project needs, and the project's own
repository. West reads the list of projects and their exact revisions from a
*manifest*, `app/west.yml`, so the same workspace can be recreated anywhere.

## Directory layout

```text
Sandbox/
├── ZephyrOSTe0715/              the west workspace
│   ├── app/                     project repository (manifest, board, apps, scripts)
│   ├── docs/, mkdocs.yml        this documentation
│   ├── zephyr/                  Zephyr, SiboVG fork, branch te0715-can-v4.4.2
│   ├── zephyr-main/             worktree: UART fixes on upstream main (PR branch)
│   ├── zephyr-can-main/         worktree: CAN driver on upstream main (PR branch)
│   ├── modules/
│   │   ├── lib/libcsp/          Space Inventor libcsp csh/2.10
│   │   ├── lib/libparam/        Space Inventor libparam csh/2.10
│   │   ├── fprime/fprime/       F Prime
│   │   ├── fprime/fprime-zephyr/  F Prime's Zephyr platform support
│   │   └── hal/cmsis*/          ARM CMSIS headers
│   └── .venv/                   Python environment
├── fprime-csp-libparam/         reusable F Prime CSP/libparam library
└── CspLibparamFprimeTest/       Linux acceptance bench (also used as the CAN test peer)
```

The two F Prime repositories next to the workspace are used as they are by the
Linux bench. The TE0715 F Prime application builds the same code, so they must be
checked out on the branches that add Zephyr support (see below).

## What is in `app/`

| Path | Contents |
|---|---|
| `west.yml` | The manifest: which Zephyr, libcsp, libparam, F Prime and fprime-zephyr revisions to use |
| `boards/trenz/te0715/` | The `te0715` board: devicetree, pin configuration, CAN clock setup, JTAG loading |
| `boards/te0715.overlay`, `boards/te0701-can1.overlay` | Carrier-specific additions: the Pmod GPIO, and CAN1 on Pmod J1 |
| `src/` | LED and GPIO demo (the default application) |
| `apps/can_bringup/` | Raw CAN test application |
| `apps/csp_node/` | Plain libcsp/libparam node without F Prime |
| `apps/fprime_csp_bench/` | The F Prime application (the image used on the FlatSat) |
| `zephyr/` | Makes `app/` a Zephyr module: board root, libparam build, patches |
| `boot/` | U-Boot script for booting Zephyr from the SD card |
| `scripts/` | Test tools, SD card installer, serial console |

## Repositories and branches

| Repository | Branch | Why this branch |
|---|---|---|
| [SiboVG/ZephyrOSTe0715](https://github.com/SiboVG/ZephyrOSTe0715) (private) | `main` | This repository: `app/` and the documentation. The workspace root is the repository; west's projects next to `app/` are ignored |
| [SiboVG/zephyr](https://github.com/SiboVG/zephyr) | `te0715-can-v4.4.2` | Zephyr v4.4.2 with the UART fixes and the CAN driver; pinned in `west.yml` |
| | `xuartps-fixes` | The UART fixes on upstream `main`; [PR #119996](https://github.com/zephyrproject-rtos/zephyr/pull/119996) |
| | `xlnx-can` | The CAN driver on upstream `main`, independent of the UART fixes; [PR #120163](https://github.com/zephyrproject-rtos/zephyr/pull/120163) |
| [SiboVG/fprime-csp-libparam](https://github.com/SiboVG/fprime-csp-libparam) | `main` | Adds `ZephyrCanTransport` |
| [SiboVG/CspLibparamFprimeTest](https://github.com/SiboVG/CspLibparamFprimeTest) | `main` | Lets the `CspLibparam` component use the Zephyr transport |

Next: [Installing the tools](install.md).
