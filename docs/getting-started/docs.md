# Building these docs

The documentation is written in Markdown and built with
[MkDocs](https://www.mkdocs.org/) and the Material theme, like the documentation of
CspLibparamFprimeTest and fprime-csp-libparam.

The published copy is at <https://sibovg.github.io/ZephyrOSTe0715/>. The `Docs`
workflow (`.github/workflows/docs.yml`) builds it with `--strict` on every push and
pull request, and deploys it to GitHub Pages from `main`. The site is public even
though the repository is private, so keep anything confidential out of `docs/`.

To work on the docs locally:

```bash
cd ZephyrOSTe0715
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve
```

Open <http://127.0.0.1:8000>; the page reloads when a file changes.

Before committing changes, check that every page, link and anchor resolves:

```bash
.venv-docs/bin/mkdocs build --strict
```

This also writes a static copy of the site to `site/`. The static copy works
without a server, which is useful in the lab: copy `site/` to a laptop and open
`site/index.html`.

## Where things are

| Path | Contents |
|---|---|
| `mkdocs.yml` | Site configuration and navigation |
| `docs/getting-started/` | Setting up and building |
| `docs/guide/` | Using the board |
| `docs/architecture/` | Design |
| `docs/tests/` | Test procedures |
| `docs/verification/` | Requirements, test case specifications, as-run records |
| `docs/verification/evidence/<date>/` | Raw logs of a test run, with `SHA256SUMS` |

## Recording a new test run

`app/scripts/collect_results.sh` runs all bench tests and stores the raw logs in
`docs/verification/evidence/<date>/`. Do not edit raw logs. Write the assessment in
a new as-run record that refers to the log files and their checksums; see the
[as-run record of 2026-09-23](../verification/as-run-2026-09-23.md) as an example.

!!! note "Version control"
    The docs are in the same repository as `app/`
    ([SiboVG/ZephyrOSTe0715](https://github.com/SiboVG/ZephyrOSTe0715)), so a
    change to the code and its documentation can be one commit. Commit the evidence
    folder of a run together with its as-run record.
