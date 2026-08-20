#!/usr/bin/env bash
# Full verification. Run after every change.
#
# The previous version piped each eval run through `tail | sed` and then tested
# `||` against the exit status of *sed*, which is always 0. A failing agent
# could not turn this script red. Exit codes are now captured directly.
set -uo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
fail=0

echo "=== per-agent evals ==="
for a in jira-scribe code-sentinel release-archivist; do
  out=$( cd "$a" && "$PY" scripts/run_evals.py 2>&1 ); rc=$?
  printf '  %-19s %s\n' "$a:" "$(printf '%s\n' "$out" | tail -1)"
  if [ "$rc" -ne 0 ]; then
    fail=1
    printf '%s\n' "$out" | grep -E 'FAIL' | sed 's/^/      /'
  fi
done

echo; echo "=== composition + independence ==="
out=$( "$PY" scenario/run_scenario.py 2>&1 ); rc=$?
printf '%s\n' "$out" | tail -5
if [ "$rc" -ne 0 ]; then
  fail=1
  printf '%s\n' "$out" | grep -E 'FAIL|^\s+!' | sed 's/^/  /'
fi

echo; echo "=== compliance audit ==="
"$PY" audit/run_audit.py || fail=1

echo
if [ "$fail" = 0 ]; then echo "ALL GREEN"; else echo "FAILURES PRESENT"; fi
exit $fail
