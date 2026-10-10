#!/usr/bin/env python3
"""Run the CubeSpec static-analysis gate: cppcheck and clang-tidy.

Every C/C++ repository in the CubeSpec flight-software workspace vendors an
identical copy of this script. The workspace keeps the reference copy in
tools/static-analysis/ and tools/static-analysis/check_drift.py fails when a
repository copy differs from it. Repository specifics live in the repository's
static-analysis.toml:

    [[build]]
    name = "host"                       # selected with --build
    dir = "build-static"                # holds compile_commands.json
    configure = ["cmake", "-S", ...]    # optional; run unless --no-configure
    include = ["Lib/**"]                # first-party sources to analyse
    exclude = ["**/test/**"]            # optional
    suppress_paths = ["lib/*"]          # optional; repo paths whose cppcheck findings are not counted
    strip_flags = ["-fno-tree-*"]       # optional; compiler flags clang does not accept
    clang_tidy_extra_args = []          # optional; e.g. ["--target=arm-none-eabi"]
    cppcheck_args = []                  # optional; e.g. ["-DCONFIG_FOO=1"]

An optional top-level `local_builds = ["host"]` (placed before the first
[[build]]) names the builds analysed by default outside CI; CI analyses every
build unless --build is given.

The script filters each build's compile_commands.json to the first-party
translation units, runs both analysers on exactly that set, prints (and
optionally records) the tool versions, file list and findings, and exits
non-zero on any finding. The rule sets are the repository's .clang-tidy and the
CPPCHECK_ARGS below; suppressions are only allowed inline with a reason.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import fnmatch
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

CLANG_TIDY_VERSION = "22.1.8"
CPPCHECK_VERSION = "2.22.0"

# Workspace rule set for cppcheck. Style findings are part of the gate.
CPPCHECK_ARGS = [
    "--enable=warning,style,performance,portability",
    "--inline-suppr",
    "--error-exitcode=1",
    "--library=posix",
    "--check-level=exhaustive",
    "--suppress=missingIncludeSystem",
    "--suppress=unmatchedSuppression",
    "--suppress=checkersReport",
    "--template={file}:{line}:{column}: {severity}: {message} [{id}]",
]

CONFIG_NAME = "static-analysis.toml"


def find_config(start: Path) -> Path:
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise SystemExit(f"error: no {CONFIG_NAME} found in {start} or its parents")


def run_text(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout + result.stderr).strip()


def version_in(text: str) -> str:
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else "unknown"


def resolve_clang_tidy() -> list[str]:
    """Return the clang-tidy command: $CLANG_TIDY, the pinned PyPI wheel, or PATH."""
    if os.environ.get("CLANG_TIDY"):
        return shlex.split(os.environ["CLANG_TIDY"])
    if shutil.which("uvx"):
        located = subprocess.run(
            ["uvx", "--from", f"clang-tidy=={CLANG_TIDY_VERSION}", "sh", "-c", "command -v clang-tidy"],
            capture_output=True, text=True, check=False,
        )
        if located.returncode == 0 and located.stdout.strip():
            return [located.stdout.strip().splitlines()[-1]]
    if shutil.which("clang-tidy"):
        return ["clang-tidy"]
    raise SystemExit(
        f"error: clang-tidy not found; install uv (uvx) or `pipx install clang-tidy=={CLANG_TIDY_VERSION}`"
    )


def resolve_cppcheck() -> list[str]:
    if os.environ.get("CPPCHECK"):
        return shlex.split(os.environ["CPPCHECK"])
    if shutil.which("cppcheck"):
        return ["cppcheck"]
    raise SystemExit(f"error: cppcheck not found; install cppcheck {CPPCHECK_VERSION}")


def check_version(tool: str, found: str, pinned: str, out: list[str]) -> bool:
    if found == pinned:
        return True
    message = f"{tool} {found} does not match the pinned {pinned}"
    if os.environ.get("CI"):
        out.append(f"error: {message}")
        return False
    out.append(f"warning: {message}; results may differ from CI")
    return True


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def entry_file(entry: dict) -> Path:
    file = Path(entry["file"])
    if not file.is_absolute():
        file = Path(entry["directory"]) / file
    return Path(os.path.normpath(file))


def entry_arguments(entry: dict) -> list[str]:
    if "arguments" in entry:
        return list(entry["arguments"])
    return shlex.split(entry["command"])


def strip_arguments(arguments: list[str], patterns: list[str]) -> list[str]:
    return [argument for argument in arguments if not matches(argument, patterns)]


def filtered_database(root: Path, build: dict) -> tuple[Path, list[str]]:
    """Write <dir>/static-analysis/compile_commands.json with first-party entries only."""
    build_dir = root / build["dir"]
    database = build_dir / "compile_commands.json"
    if not database.is_file():
        raise SystemExit(f"error: {database} is missing; configure the build first")
    include = build.get("include", [])
    exclude = build.get("exclude", []) + ["**/*Ac.cpp", "**/*Ac.c"]
    strip = build.get("strip_flags", [])
    selected: dict[str, dict] = {}
    for entry in json.loads(database.read_text(encoding="utf-8")):
        file = entry_file(entry)
        try:
            relative = file.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        if not matches(relative, include) or matches(relative, exclude):
            continue
        selected.setdefault(relative, {
            "directory": entry["directory"],
            "file": str(file),
            "arguments": strip_arguments(entry_arguments(entry), strip),
        })
    if not selected:
        raise SystemExit(f"error: build '{build['name']}' selected no translation units from {database}")
    output_dir = build_dir / "static-analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "compile_commands.json"
    output.write_text(json.dumps(list(selected.values()), indent=2) + "\n", encoding="utf-8")
    return output_dir, sorted(selected)


def darwin_sysroot_args() -> list[str]:
    if platform.system() != "Darwin":
        return []
    sdk = run_text(["xcrun", "--show-sdk-path"])
    return [f"--extra-arg=-isysroot{sdk}"] if sdk else []


def run_clang_tidy(command: list[str], root: Path, database_dir: Path, files: list[str], build: dict,
                   jobs: int) -> tuple[int, list[str]]:
    extra = [f"--extra-arg={argument}" for argument in build.get("clang_tidy_extra_args", [])]
    extra += ["--extra-arg=-Wno-unknown-warning-option"] + darwin_sysroot_args()

    def one(relative: str) -> tuple[str, int, str]:
        result = subprocess.run(
            [*command, "--quiet", f"-p={database_dir}", *extra, str(root / relative)],
            cwd=root, capture_output=True, text=True, check=False,
        )
        lines = [line for line in (result.stdout + result.stderr).splitlines()
                 if not re.match(r"^\d+ warnings? (and \d+ errors? )?generated\.$", line)
                 and not line.startswith("Suppressed ")
                 and not line.startswith("Use -header-filter")]
        return relative, result.returncode, "\n".join(lines).strip()

    findings = 0
    log: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for relative, status, output in pool.map(one, files):
            reported = len(re.findall(r": (?:warning|error): ", output))
            if status != 0 or reported:
                findings += max(reported, 1)
                log.append(f"--- {relative}\n{output}")
    return findings, log


# cppcheck ids meaning a translation unit (or part of it) was not analysed.
# They count as findings wherever they occur, including vendored headers,
# because a skipped file would otherwise pass silently.
CPPCHECK_INTEGRITY_IDS = {
    "preprocessorErrorDirective", "syntaxError", "unknownMacro", "internalError",
    "internalAstError", "cppcheckError", "instantiationError", "templateRecursion",
    "directiveAsMacroParameter",
}
CPPCHECK_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+): (?P<severity>\w+): .*\[(?P<id>\w+)\]$")


def first_party(path: str, root: Path, build: dict) -> bool:
    """True when a reported file is the repository's own code (not vendored, generated or outside)."""
    file = Path(path)
    if not file.is_absolute():
        file = root / file
    try:
        relative = file.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    if relative.startswith(build["dir"].rstrip("/") + "/"):
        return False
    return not matches(relative, build.get("suppress_paths", []))


def run_cppcheck(command: list[str], root: Path, database_dir: Path, build: dict,
                 jobs: int) -> tuple[int, list[str]]:
    """Run cppcheck and count first-party findings plus analysis-integrity errors anywhere.

    Findings in vendored, generated or out-of-tree files are filtered here by
    location rather than with --suppress, so that an #error or parse failure in
    such a file (which makes cppcheck skip the translation unit) is still reported.
    """
    cache = database_dir / "cppcheck-cache"
    cache.mkdir(exist_ok=True)
    result = subprocess.run(
        [*command, *CPPCHECK_ARGS, *build.get("cppcheck_args", []),
         f"--cppcheck-build-dir={cache}", f"-j{jobs}", "--quiet",
         f"--project={database_dir / 'compile_commands.json'}"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    reported: list[str] = []
    ignored = 0
    other: list[str] = []
    for line in (result.stdout + result.stderr).splitlines():
        if not line.strip():
            continue
        match = CPPCHECK_LINE.match(line)
        if not match:
            other.append(line)
            continue
        if match["id"] in CPPCHECK_INTEGRITY_IDS or first_party(match["file"], root, build):
            reported.append(line)
        else:
            ignored += 1
    lines = reported + other
    if ignored:
        lines.append(f"({ignored} finding(s) in vendored, generated or out-of-tree files not counted)")
    findings = len(reported)
    if findings == 0 and other:
        findings = 1  # unparsed cppcheck output (e.g. a tool error) fails the gate
    return findings, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, help=f"path to {CONFIG_NAME} (default: search upward from cwd)")
    parser.add_argument("--build", action="append", help="analyse only the named build (repeatable)")
    parser.add_argument("--no-configure", action="store_true", help="reuse existing compile_commands.json")
    parser.add_argument("--report", type=Path, help="also write the full report to this file")
    parser.add_argument("--list", action="store_true", help="list the configured builds and exit")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    arguments = parser.parse_args()

    config_path = (arguments.config or find_config(Path.cwd())).resolve()
    root = config_path.parent
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    builds = config.get("build", [])
    if arguments.list:
        for build in builds:
            print(f"{build['name']}: {build['dir']}")
        return 0
    if arguments.build:
        unknown = set(arguments.build) - {build["name"] for build in builds}
        if unknown:
            raise SystemExit(f"error: unknown build(s): {', '.join(sorted(unknown))}")
        builds = [build for build in builds if build["name"] in arguments.build]
    elif "local_builds" in config and not os.environ.get("CI"):
        local = config["local_builds"]
        skipped = [build["name"] for build in builds if build["name"] not in local]
        builds = [build for build in builds if build["name"] in local]
        if skipped:
            print(f"note: not analysing {', '.join(skipped)} on this host (not in local_builds); "
                  "CI analyses them, or name them with --build", file=sys.stderr)

    out: list[str] = []
    clang_tidy = resolve_clang_tidy()
    cppcheck = resolve_cppcheck()
    clang_tidy_version = version_in(run_text([*clang_tidy, "--version"]).split("LLVM version", 1)[-1])
    cppcheck_version = version_in(run_text([*cppcheck, "--version"]))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    out.append("# Static analysis: cppcheck + clang-tidy (zero-finding gate)")
    out.append(f"# Recorded {stamp} on {platform.system()} {platform.machine()}")
    out.append(f"cppcheck: {cppcheck_version} (pinned {CPPCHECK_VERSION}); rules: {' '.join(CPPCHECK_ARGS[:5])}")
    out.append(f"clang-tidy: LLVM {clang_tidy_version} (pinned {CLANG_TIDY_VERSION}); rules: .clang-tidy")
    versions_ok = check_version("cppcheck", cppcheck_version, CPPCHECK_VERSION, out)
    versions_ok &= check_version("clang-tidy", clang_tidy_version, CLANG_TIDY_VERSION, out)

    total = 0
    for build in builds:
        out.append("")
        out.append(f"## build: {build['name']} ({build['dir']})")
        if build.get("configure") and not arguments.no_configure:
            configure = subprocess.run(build["configure"], cwd=root, capture_output=True, text=True, check=False)
            if configure.returncode != 0:
                print("\n".join(out))
                print(configure.stdout + configure.stderr, file=sys.stderr)
                raise SystemExit(f"error: configuring build '{build['name']}' failed")
        database_dir, files = filtered_database(root, build)
        out.append(f"translation units ({len(files)}):")
        out.extend(f"  {file}" for file in files)
        cppcheck_findings, cppcheck_log = run_cppcheck(cppcheck, root, database_dir, build, arguments.jobs)
        out.append(f"cppcheck findings: {cppcheck_findings}")
        out.extend(f"  {line}" for line in cppcheck_log)
        tidy_findings, tidy_log = run_clang_tidy(clang_tidy, root, database_dir, files, build, arguments.jobs)
        out.append(f"clang-tidy findings: {tidy_findings}")
        out.extend(tidy_log)
        total += cppcheck_findings + tidy_findings

    out.append("")
    passed = total == 0 and versions_ok
    out.append(f"result: {'PASS' if passed else 'FAIL'} ({total} finding(s))")
    report = ("\n".join(out) + "\n").replace(str(root) + "/", "")
    sys.stdout.write(report)
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(report, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
