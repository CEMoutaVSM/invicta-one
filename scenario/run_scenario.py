#!/usr/bin/env python3
"""Scenario runner for the three agents.

Two modes:

  --mode chained      run all three in sequence, passing envelopes forward
  --mode independent  run each one with the OTHER TWO PHYSICALLY REMOVED
                      from the tree, to prove no hidden coupling exists

This runner is the ONLY place that knows about more than one agent.
The agents themselves never reference each other.

Usage: python run_scenario.py [--mode chained|independent|both]
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "scenario" / "fixtures"

STAGES = [
    ("jira-scribe", "scripts/parse_input.py", FIX / "01-refinement.txt",
     "Refinement transcript -> story extraction"),
    ("code-sentinel", "scripts/parse_diff.py", FIX / "02-permissions.diff",
     "Diff -> reviewable surface"),
    ("release-archivist", "scripts/classify.py", FIX / "03-sprint42.log",
     "Sprint log -> coverage ledger"),
]


def run(agent_root: pathlib.Path, agent: str, script: str,
        fixture: pathlib.Path, extra: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(agent_root / agent / script), str(fixture)]
    if extra:
        cmd += extra
    if agent == "release-archivist":
        cmd.append("--json")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode not in (0, 1):
        return {"status": "crash", "stderr": p.stderr[-400:]}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"status": "unparseable", "stdout": p.stdout[-400:]}


def summarise(agent: str, env: dict) -> str:
    s = env.get("status", "?")
    if agent == "jira-scribe":
        miss = env.get("missing_fields", [])
        return (f"status={s} missing={miss or 'none'} "
                f"segments={env.get('stats', {}).get('segments', '?')} "
                f"reversals={len(env.get('reversals', []))}")
    if agent == "code-sentinel":
        c = env.get("coverage", {})
        t = env.get("test_expectation", {})
        return (f"status={s} files={c.get('files_changed')} "
                f"reviewable={c.get('reviewable')} skipped={c.get('skipped')} "
                f"new_branches={t.get('new_branches')} "
                f"tests_added={'yes' if t.get('test_files_touched') else 'NO'}")
    c = env.get("coverage", {})
    return (f"status={s} in={c.get('items_in')} pub={c.get('published')} "
            f"internal={c.get('internal')} suppressed={c.get('suppressed')} "
            f"reconciles={'YES' if c.get('reconciles') else 'NO'}")


def chained() -> bool:
    print("\n=== COMPOSITION TEST — chained ===")
    print("Envelopes passed forward. Each stage adds context to the next.\n")
    envelopes, ok = {}, True
    for agent, script, fixture, desc in STAGES:
        env = run(ROOT, agent, script, fixture)
        # insufficient_input is a SUCCESSFUL run: the agent correctly refused.
        good = env.get("status") in ("ok", "insufficient_input")
        ok &= good
        print(f"  [{'OK ' if good else 'FAIL'}] {agent:<19} {desc}")
        print(f"         {summarise(agent, env)}")
        if upstream := list(envelopes):
            print(f"         upstream context available: {', '.join(upstream)}")
        envelopes[agent] = env

    # The cross-agent check the runner (not the agents) performs.
    sc = envelopes.get("code-sentinel", {}).get("test_expectation", {})
    if sc and not sc.get("expectation_met"):
        print(f"\n  ! chain insight: {sc['new_branches']} new branch(es) with no "
              "test file touched -> L2-TEST-01 candidate")
    return ok


def independent() -> bool:
    print("\n=== INDEPENDENCE TEST — the other two agents are DELETED ===")
    print("Each agent must pass alone, unmodified.\n")
    ok = True
    for agent, script, fixture, _ in STAGES:
        with tempfile.TemporaryDirectory() as tmp:
            iso = pathlib.Path(tmp) / "isolated"
            iso.mkdir()
            shutil.copytree(ROOT / agent, iso / agent)
            others = [a for a, *_ in STAGES if a != agent]
            env = run(iso, agent, script, fixture)
            good = env.get("status") in ("ok", "insufficient_input")
            ok &= good
            print(f"  [{'OK ' if good else 'FAIL'}] {agent:<19} "
                  f"ran with {', '.join(others)} removed")
            print(f"         {summarise(agent, env)}")
            if not good:
                print(f"         {env}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both",
                    choices=["chained", "independent", "both"])
    a = ap.parse_args()

    results = []
    if a.mode in ("chained", "both"):
        results.append(("composition", chained()))
    if a.mode in ("independent", "both"):
        results.append(("independence", independent()))

    print("\n" + "=" * 58)
    for name, passed in results:
        print(f"  {name:<14} {'PASS' if passed else 'FAIL'}")
    print("=" * 58)
    return 0 if all(p for _, p in results) else 1


if __name__ == "__main__":
    sys.exit(main())
