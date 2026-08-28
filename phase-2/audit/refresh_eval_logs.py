#!/usr/bin/env python3
"""Regenerate the Eval Log table in every SKILL.md from the runners.

Each SKILL.md claims its table is "generated from the runner, so it cannot
describe a case the suite does not run". That sentence was true when written and
then quietly became the only falsifiable-and-false claim in the submission: the
generator lived outside version control, was lost, and the tables drifted — a
recorded digest that no longer reproduced, under a sentence promising it could
not drift.

This is that generator, in the repository this time. `run_audit.py` checks its
output against a fresh run, so the claim is now enforced rather than asserted.

Usage:  python audit/refresh_eval_logs.py [--check]
        --check  report drift and exit 1 without writing
Exit:   0 tables match the runners / 1 drift found (or written, with --check)
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENTS = ("release-archivist", "jira-scribe", "code-sentinel")

HEADER = ("| # | Case | Runs | Output digest | Golden-gated | Result |\n"
          "|---|---|---|---|---|---|\n")
ROW = re.compile(r"^\|\s*\d+\s*\|", re.M)


def rows_for(agent: str) -> tuple[list[str], str]:
    """Run the suite and turn its output into table rows."""
    p = subprocess.run([sys.executable, str(ROOT / agent / "scripts/run_evals.py")],
                       capture_output=True, text=True, cwd=ROOT / agent)
    out = p.stdout
    rows, n = [], 0
    for line in out.splitlines():
        m = re.match(r"\s+ok\s+(.+?)\s+\[([0-9a-f]{8}) x3\](\s+\[golden ok\])?$", line)
        if m:
            n += 1
            rows.append(f"| {n} | `{m.group(1)}` | 3 | `{m.group(2)}` x3 | "
                        f"{'yes' if m.group(3) else chr(8212)} | PASS |")
            continue
        # the suppression case reports a golden comparison with no digest
        if "x3]" in line:
            continue
        m = re.match(r"\s+ok\s+(.+?)\s+\[golden ok\]$", line)
        if m:
            n += 1
            rows.append(f"| {n} | `{m.group(1)}` | 3 | deterministic | yes | PASS |")
    total = re.search(r"(\d+)/(\d+) passed", out)
    return rows, (total.group(0) if total else "see runner")


def table_in(skill: str) -> list[str]:
    return [l.strip() for l in skill.splitlines() if ROW.match(l)]


def main() -> int:
    check = "--check" in sys.argv
    drifted = []

    for agent in AGENTS:
        p = ROOT / agent / "SKILL.md"
        skill = p.read_text(encoding="utf-8")
        rows, total = rows_for(agent)
        current = table_in(skill)

        if current == rows:
            print(f"  {agent:<20} {len(rows)} rows, matches the runner")
            continue

        drifted.append(agent)
        print(f"  {agent:<20} DRIFT: {len(current)} row(s) recorded, "
              f"{len(rows)} produced")
        for a, b in zip(current, rows):
            if a != b:
                print(f"      recorded: {a[:96]}")
                print(f"      actual  : {b[:96]}")
                break
        if check:
            continue

        i = skill.index("## Eval Log")
        head, tail = skill[:i], skill[i:]
        # replace the table block, keep every paragraph around it
        start = tail.find("| # | Case")
        if start < 0:
            print(f"      !! no table found in {agent}/SKILL.md")
            continue
        end = start
        for line in tail[start:].splitlines(keepends=True):
            if line.startswith("|"):
                end += len(line)
            elif end > start:
                break
            else:
                end += len(line)
        tail = tail[:start] + HEADER + "\n".join(rows) + "\n" + tail[end:]
        tail = re.sub(r"\*\*\d+/\d+ passed\.\*\*", f"**{total}.**", tail)
        p.write_text(head + tail, encoding="utf-8")
        print(f"      rewritten: {len(rows)} rows, {total}")

    if drifted and check:
        print(f"\n{len(drifted)} Eval Log(s) do not match the runner: "
              f"{', '.join(drifted)}")
        print("Run `python audit/refresh_eval_logs.py` to regenerate them.")
        return 1
    if drifted:
        print(f"\nregenerated {len(drifted)} Eval Log(s)")
        return 1
    print("\nevery Eval Log matches its runner")
    return 0


if __name__ == "__main__":
    sys.exit(main())
