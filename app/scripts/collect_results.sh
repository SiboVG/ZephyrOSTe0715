#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Run every hardware test and store the logs in <workspace>/docs/verification/evidence/<date-time>/,
# with a SHA256SUMS file. Do not edit the logs afterwards; assess them in an as-run record.
#
#   app/scripts/collect_results.sh /path/to/CspBench [can0]
#
# Needs: the TE0715 on the Digilent cable, xsdb, the Kvaser interface UP at
# 1 Mbit/s and wired to the TE0701 Pmod J1 transceiver, the SD card prepared
# with scripts/sd_install.py, and the workspace virtual environment. Ends with
# a standalone SD-card boot, so the board is left running the flatsat image.

set -uo pipefail

bench="${1:?usage: collect_results.sh /path/to/CspBench [can-interface]}"
can="${2:-can0}"
app="$(cd "$(dirname "$0")/.." && pwd)"
ws="$(dirname "$app")"
out="$ws/docs/verification/evidence/$(date +%Y-%m-%d-%H%M)"
mkdir -p "$out"
py="$ws/.venv/bin/python"
export PATH="$ws/.venv/bin:$PATH"
overlay="-x-DEXTRA_DTC_OVERLAY_FILE=$app/boards/te0701-can1.overlay"
status=0

run() {  # name, command...
    local name="$1"; shift
    echo "=== $name"
    if "$@" 2>&1 | tee "$out/$name.txt"; then :; else status=1; fi
}

copy_console() {  # build-root, test-dir-prefix, destination-prefix
    for f in "$1"/"$2"*/console.log; do
        [[ -f "$f" ]] && sed 's/\x1b\[[0-9;?]*[A-Za-z]//g' "$f" > "$out/$3$(basename "$(dirname "$f")").log"
    done
}

{
    echo "date: $(date -Is)"
    echo "app: $(git -C "$app" rev-parse --short HEAD)$(git -C "$app" diff --quiet -- . || echo -dirty)"
    echo "fprime-csp-libparam: $(git -C "$ws/../fprime-csp-libparam" rev-parse --short HEAD 2>/dev/null)"
    echo "CspLibparamFprimeTest: $(git -C "$ws/../CspLibparamFprimeTest" rev-parse --short HEAD 2>/dev/null)"
    echo "fprime: $(git -C "$ws/modules/fprime/fprime" describe --tags --always 2>/dev/null)"
    echo "fprime-zephyr: $(git -C "$ws/modules/fprime/fprime-zephyr" rev-parse --short HEAD 2>/dev/null)"
    echo "libcsp: $(git -C "$ws/modules/lib/libcsp" describe --tags --always 2>/dev/null)"
    echo "libparam: $(git -C "$ws/modules/lib/libparam" describe --tags --always 2>/dev/null)"
    echo "zephyr.bin sha256: $(sha256sum "$app/apps/fprime_csp_bench/build-fprime-automatic-zephyr/zephyr/zephyr.bin" | cut -d' ' -f1)"
    echo "zephyr: $(git -C "$ws/zephyr" describe --tags --always)"
    echo "zephyr (upstream CAN branch): $(git -C "$ws/zephyr-can-main" describe --tags --always 2>/dev/null)"
    echo "sdk: $(cat "$ws/zephyr/SDK_VERSION")"
    ip -details link show "$can" | grep -E 'state|bitrate'
} > "$out/environment.txt"

rm -rf "$ws/build/hw" "$ws/build/hw-main"

# Zephyr test suites, Zephyr v4.4.2 + fixes (the workspace pin)
run zephyr-suites "$py" "$app/scripts/hw_test.py" test \
    tests/kernel/common tests/kernel/timer/timer_api tests/kernel/sched/schedule_api \
    tests/kernel/mem_protect/stackprot tests/drivers/uart/uart_basic_api
run can-suites "$py" "$app/scripts/hw_test.py" test --timeout 150 "$overlay" \
    tests/drivers/can/api tests/drivers/can/timing
copy_console "$ws/build/hw" tests_ ""

# CAN driver on upstream main (branch xlnx-can); main needs CMake >= 3.28
if [[ -d "$ws/zephyr-can-main" ]]; then
    PATH="/usr/bin:$PATH" run can-suites-upstream-main "$py" "$app/scripts/hw_test.py" test \
        --zephyr-base "$ws/zephyr-can-main" --build-root "$ws/build/hw-main" --timeout 150 \
        "$overlay" tests/drivers/can/api tests/drivers/can/timing
    copy_console "$ws/build/hw-main" tests_ "upstream-main-"
fi

# Raw CAN over the real bus
run can-bringup "$py" "$app/scripts/hw_test.py" run "$app/apps/can_bringup" --seconds 4
run can-echo "$py" "$app/scripts/can_echo_test.py" "$can" --count 1000

# F Prime bench server, loaded over JTAG, then booted standalone from the SD card
elf="$app/apps/fprime_csp_bench/build-fprime-automatic-zephyr/zephyr/zephyr.elf"
run fprime-e2e-jtag "$py" "$app/scripts/fprime_e2e.py" --bench "$bench" --can "$can" \
    --elf "$elf" --log "$out/fprime-e2e-jtag-transcript.log"
run fprime-e2e-sd-boot "$py" "$app/scripts/fprime_e2e.py" --bench "$bench" --can "$can" \
    --sd-boot --log "$out/fprime-e2e-sd-boot-transcript.log"

(cd "$out" && sha256sum -- * > SHA256SUMS)
echo "results in $out (status $status)"
exit $status
