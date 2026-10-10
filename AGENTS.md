# Notes for coding agents

This directory is both the Git repository (`app/`, `docs/`, `.github/` and the files
at the root that `.gitignore` whitelists) and a west workspace (`zephyr/`, `modules/`
and `build/` are not part of the repository; do not edit them).

## Before handing off a change

Run, and report the results of:

1. Host scripts: `python -m pytest app/tests/scripts`
2. Firmware unit tests (needs the west workspace):
   `zephyr/scripts/twister -T app/tests -p native_sim/native/64`
3. Static analysis, zero findings (needs the te0715 builds, see
   `docs/getting-started/static-analysis.md`):
   `python3 app/scripts/static_analysis.py --build demo --build demo-spi1 --build can_bringup --build csp_node --build bench`
4. Docs: `mkdocs build --strict` (in a venv with `requirements-docs.txt`)

Anything that cannot run where you are (no Zephyr SDK, no board) is left to CI or
the bench; say so instead of claiming it passed.

## Static analysis

- `app/scripts/static_analysis.py`, `app/scripts/install-cppcheck.sh`,
  `app/scripts/clang-tidy` and `.clang-tidy` (except `HeaderFilterRegex`) are
  byte-identical copies of the shared CubeSpec reference. Do not edit them here.
  Repository settings belong in `static-analysis.toml`.
- Fix findings in the code without changing behaviour. Suppress only on the line,
  with the check id and a reason (`/* NOLINTNEXTLINE(check-id) */` after a comment
  giving the reason, or `/* cppcheck-suppress id ; reason */`); never file- or
  project-wide. List each suppression in the docs page.
- A finding that is a real defect whose fix changes behaviour is reported (and
  added to `docs/known-issues.md`), not silently fixed or suppressed.

## Documentation

The site in `docs/` is published publicly on every push to `main`; keep anything
confidential out of it. When a requirement, test case or test script changes, keep
`docs/verification/requirements.md` and `docs/verification/test-cases.md` (the
verification matrices) and the test guides in `docs/tests/` in sync. Evidence logs
in `docs/verification/evidence/` are never edited.

## Test-first, from the requirement

Develop test-first, and derive tests from what the code must do, not from how it does it:

1. Add or update the requirement (ID, `shall` statement, rationale or parent, method) in this repository's requirements matrix.
2. Design test cases from the requirement and the interface contract (datasheet, ICD, FPP model) without reading the implementation: nominal values computed independently, boundaries, invalid inputs, injected dependency faults, state transitions.
3. Watch the tests fail, implement the minimum to make them pass, then refactor.
4. When coverage shows unexecuted code, add a requirement-derived test, remove dead code, add the missing requirement, or justify the code by analysis. Never add a test only to execute a line.
5. Name the requirement ID in each test, and list the test in the requirement's row.

Coverage target (ECSS category C, CubeSpec): 100% statement coverage, tested or justified, and at least 80% decision coverage. The full procedure is in the CubeSpec workspace `AGENTS.md` (`../../AGENTS.md` in the workspace layout).
