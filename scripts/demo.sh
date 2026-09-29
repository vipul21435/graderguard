#!/bin/sh
# Audit the three bundled sample tasks offline and check each verdict.
# Expected: the exit-code-only and hardcodable graders have holes (exit 1) and the robust
# grader has none (exit 0). Markdown and JSON reports land in $REPORT_DIR (default ./reports).
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${REPORT_DIR:-reports}
mkdir -p "$OUT"
start=$(date +%s)
failures=0

check() {
    task=$1
    want=$2
    graderguard audit "$ROOT/examples/tasks/$task" --quiet \
        --out "$OUT/$task.md" --out "$OUT/$task.json"
    got=$?
    if [ "$got" -ne "$want" ]; then
        echo "UNEXPECTED: $task exited $got, expected $want" >&2
        failures=$((failures + 1))
    fi
}

check exit-code-only 1
check hardcodable 1
check robust 0

elapsed=$(( $(date +%s) - start ))
if [ "$failures" -ne 0 ]; then
    echo "demo FAILED: $failures sample verdict(s) differ from the expected ones" >&2
    exit 1
fi
echo "demo OK: 3/3 sample verdicts as expected in ${elapsed}s; reports in $OUT/"
