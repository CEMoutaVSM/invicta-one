#!/usr/bin/env bash
# Full verification. Run after every change.
set -uo pipefail
cd "$(dirname "$0")"
fail=0
echo "=== per-agent evals ==="
for a in jira-scribe code-sentinel release-archivist; do
  (cd "$a" && python3 scripts/run_evals.py | tail -1 | sed "s|^|  $a: |") || fail=1
done
echo; echo "=== composition + independence ==="
python3 scenario/run_scenario.py | tail -4 || fail=1
echo; echo "=== compliance audit ==="
python3 audit/run_audit.py || fail=1
echo
[ "$fail" = 0 ] && echo "ALL GREEN" || echo "FAILURES PRESENT"
exit $fail
