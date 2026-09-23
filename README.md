# TE0715 Zephyr bring-up workspace

This is the west workspace for running Zephyr, CAN, libcsp/libparam and F Prime on
the Trenz TE0715-05-71I33-L (AMD Zynq-7030) on a TE0701 carrier. The documentation
for everything in it lives in `docs/` and is built with MkDocs.

## What is where

| Path | What it is |
|---|---|
| `docs/`, `mkdocs.yml` | This documentation (user guide, architecture, test guides, verification records) |
| `app/` | The application repository: west manifest, `te0715` board, applications, scripts, patches |
| `zephyr/` | Zephyr (SiboVG fork, branch `te0715-can-v4.4.2`) |
| `zephyr-main/`, `zephyr-can-main/` | Worktrees of the upstream-`main` branches for the Zephyr PRs (`xuartps-fixes`, `xlnx-can`) |
| `modules/` | libcsp, libparam, F Prime, fprime-zephyr, CMSIS (managed by west) |
| `.venv/` | Python environment with west, the Zephyr tools and the F Prime tools |

The F Prime application also uses two checkouts next to this workspace:
`../fprime-csp-libparam` (branch `zephyr-can-transport`) and
`../CspLibparamFprimeTest` (branch `zephyr-transport`).

## Read the documentation

```bash
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve            # open http://127.0.0.1:8000
```

`mkdocs build --strict` checks all pages and links and writes a static copy to
`site/`, which can be opened without a server (for example on a laptop in the lab).

Good starting points:

- `docs/getting-started/` to set up the workspace and build the applications;
- `docs/guide/` to connect to the board and use its serial shell;
- `docs/tests/flatsat.md` for the FlatSat test procedure;
- `docs/verification/` for the requirements, test cases and as-run records.

## Repository layout

This directory is both the Git repository (github.com/SiboVG/ZephyrOSTe0715) and the
west workspace. The repository holds `app/`, `docs/` and the files next to them;
`.gitignore` excludes everything west and the builds create (`zephyr/`, `modules/`,
`build/`, the virtual environments). To set up a new workspace:

```bash
git clone git@github.com:SiboVG/ZephyrOSTe0715.git && cd ZephyrOSTe0715
uv venv .venv && source .venv/bin/activate && uv pip install west
west init -l app && west update
```

and continue with `docs/getting-started/install.md`.
