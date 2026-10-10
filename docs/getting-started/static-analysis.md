# Static analysis

The C code of this repository goes through a static-analysis gate:
[cppcheck](https://cppcheck.sourceforge.io/) and
[clang-tidy](https://clang.llvm.org/extra/clang-tidy/) must report **zero findings**.
The gate is the same in every CubeSpec flight-software repository: the runner
`app/scripts/static_analysis.py`, the rule set `.clang-tidy` and the helper scripts
next to the runner are byte-identical copies of a shared reference. Only
`static-analysis.toml` (which builds to analyse) and the `HeaderFilterRegex` line of
`.clang-tidy` are specific to this repository.

| Tool | Version | Rules |
|---|---|---|
| cppcheck | 2.22.0 | `--enable=warning,style,performance,portability`, exhaustive checking, `--library=posix` and `--library=zephyr` |
| clang-tidy | 22.1.8 (LLVM) | `.clang-tidy`: `clang-analyzer-*`, `bugprone-*`, `cert-*`, `misc-*`, `performance-*`, `portability-*`, with the exceptions listed in the file; every warning is an error |

In CI (`CI=true`) the runner refuses other tool versions; locally it warns.

## What is analysed

The runner takes the `compile_commands.json` that `west build` writes and keeps only
the first-party translation units. One build per application that CI builds for the
`te0715`:

| Build | Directory | First-party sources |
|---|---|---|
| `demo` | `build/demo` | `app/src/main.c`, `app/boards/trenz/te0715/board.c` |
| `demo-spi1` | `build/demo-spi1` | the same with SPI1 enabled (`board.c`'s SPI clock and pin set-up) |
| `can_bringup` | `build/can_bringup` | `app/apps/can_bringup/src/main.c`, `board.c` |
| `csp_node` | `build/csp_node` | `app/apps/csp_node/src/main.c`, `board.c` |
| `bench` | `build/bench` | `app/apps/fprime_csp_bench/bench_value.c` and `bench_config.c`, through the unit-test build that shares them; the tests themselves (`app/tests/`) are not analysed |

Zephyr, `modules/` and the generated headers in `build/` are not analysed. Their
findings are not counted, but an error that stops cppcheck from analysing a file
(an `#error`, a parse failure) is counted wherever it occurs, so a translation unit
cannot be skipped silently.

**Not analysed:** the F Prime applications (`app/apps/fprime_*_bench/`,
`app/fprime-bench/`), because CI does not build them (they need F Prime and the
library checkouts next to the workspace). The parsers `bench_value.c` and
`bench_config.c` are the exception, through the unit-test build.

### How the cross build is analysed

The compile commands are those of the Zephyr SDK's `arm-zephyr-eabi-gcc`, which
neither tool understands completely. `static-analysis.toml` handles that per build:

- clang-tidy parses the commands as clang for `--target=arm-none-eabi`, without the
  GCC-only options `-fno-reorder-functions` and `-mfp16-format=*`, and treats the
  `<zephyr/...>` headers as system headers (`--system-header-prefix=zephyr/`), so
  that Zephyr's own include cycles and macros are not reported against our code.
- cppcheck gets the compiler's predefined macros
  (`app/static-analysis/arm-zephyr-eabi-gcc-predefined.h`; regenerate it after a
  Zephyr SDK update with the command at its top), the build's Kconfig
  `autoconf.h` and Zephyr's `zephyr_stdint.h`, which the compile commands pass with
  `-imacros`. It also defines `CONFIG_KERNEL_VM_USE_CUSTOM_MEM_RANGE_CHECK`: with
  `CONFIG_MMU`, Zephyr's `k_mem_phys_addr()` has preprocessor directives inside a
  macro argument, which cppcheck cannot expand, and it would then skip the whole
  file. The define only selects the other branch of that Zephyr inline function.

## Running it

The gate needs the builds, so it runs where `west build` works (the development PC,
CI, or a Linux container with the Zephyr SDK). With the builds of
[Building and running](build-and-run.md) in place:

```bash
# cppcheck 2.22.0: built from source into ~/.local/cppcheck-2.22.0
sh app/scripts/install-cppcheck.sh && export PATH=$HOME/.local/cppcheck-2.22.0/bin:$PATH
# clang-tidy 22.1.8: through uvx (uv), or: pipx install clang-tidy==22.1.8

# configure (west build) and analyse one build, or name several with --build
python3 app/scripts/static_analysis.py --build demo
# all builds, reusing existing builds, as CI does
python3 app/scripts/static_analysis.py --no-configure --build demo --build demo-spi1 \
    --build can_bringup --build csp_node --build bench
```

Without `--build`, outside CI, the runner analyses only the builds listed in
`local_builds` in `static-analysis.toml`; none are listed, because none of them
build on a Mac without the Zephyr SDK. `--report <file>` also writes the report
(tool versions, file list, findings) to a file.

In CI, the *Build for the TE0715* job of `.github/workflows/tests.yml` runs the gate
on its builds after building them, and uploads the report as the
`static-analysis-report` artifact.

### In VS Code

`.vscode/` recommends the C/C++ extension and points it at the pinned clang-tidy
(`app/scripts/clang-tidy`), so the editor shows the same clang-tidy findings as the
gate. It reads the filtered `build/demo/static-analysis/compile_commands.json`, which
the gate writes for the `demo` build. The task *Static analysis (cppcheck +
clang-tidy)* runs the whole gate and lists the findings in the Problems panel.

## Suppressions

A finding is fixed in the code. A finding that is wrong for a specific line may be
suppressed on that line only, naming the check and giving the reason:

```c
/* NOLINTNEXTLINE(misc-misplaced-const): Zephyr's K_THREAD_DEFINE declares a const k_tid_t on purpose */
K_THREAD_DEFINE(router, ...);
```

and for cppcheck `/* cppcheck-suppress <id> ; <reason> */` on the line before.
Suppressions are rare; there are no file-wide or project-wide ones. The current
suppressions:

| Location | Check | Reason |
|---|---|---|
| `app/apps/csp_node/src/main.c`, `K_THREAD_DEFINE(router, ...)` | `misc-misplaced-const` | Zephyr's macro declares the thread id as a `const k_tid_t`, a constant pointer, on purpose |

If a finding points at a real defect whose fix would change the behaviour, it is
recorded in [Known issues](../known-issues.md) and fixed as a change of its own, not
hidden behind a suppression.
