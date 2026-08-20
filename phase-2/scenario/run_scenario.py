#!/usr/bin/env python3
"""Scenario runner for the three agents.

Two modes:

  --mode chained      run each agent's full pipeline, passing the upstream
                      envelope into the downstream stage for real
  --mode independent  run each agent's ENTIRE eval suite with the OTHER TWO
                      PHYSICALLY REMOVED from the tree

This runner is the ONLY place that knows about more than one agent.
The agents themselves never reference each other.

WHAT CHANGED AND WHY
--------------------
The independence mode used to run a single parser script per agent. A tree with
every `context/`, every validator, `load_rules.py`, every `run_evals.py` and
every golden file deleted still printed `independence PASS`. It now runs the
agent's whole suite, so the claim costs something to make.

The chained mode used to print "Envelopes passed forward" while passing
nothing: the `extra` parameter was dead code. Each stage now feeds its real
envelope into the next via the flag that consumes it (`--parsed`, `--diff`,
`--ledger`), and the envelope shape is asserted rather than assumed.

Usage: python run_scenario.py [--mode chained|independent|both]
Exit:  0 all passed / 1 one or more failures
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
TODAY = "2026-08-06"

# (agent, producer script, fixture, consumer script, consumer input,
#  flag that carries the envelope, description)
PIPELINES = [
    ("jira-scribe", "scripts/parse_input.py", FIX / "01-refinement.txt",
     "scripts/validate_output.py", "evals/inputs/valid-refusal.md", "--parsed",
     "Refinement transcript -> refusal -> refusal document validated"),
    ("code-sentinel", "scripts/parse_diff.py", FIX / "02-permissions.diff",
     "scripts/validate_findings.py", "evals/inputs/valid-review.md", "--diff",
     "Diff -> reviewable surface -> review validated for recall"),
    ("release-archivist", "scripts/classify.py", FIX / "03-sprint42.log",
     "scripts/validate_output.py", "evals/inputs/valid-notes.md", "--ledger",
     "Sprint log -> coverage ledger -> notes checked against it"),
]

ENVELOPE_STATUSES = {"ok", "insufficient_input", "no_output_required"}


def produce(agent_root: pathlib.Path, agent: str, script: str,
            fixture: pathlib.Path) -> dict:
    cmd = [sys.executable, str(agent_root / agent / script), str(fixture)]
    if agent == "release-archivist":
        cmd.append("--json")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode not in (0, 1):
        return {"status": "crash", "stderr": p.stderr[-400:]}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"status": "unparseable", "stdout": p.stdout[-400:]}


def consume(agent_root: pathlib.Path, agent: str, script: str, target: str,
            flag: str, envelope_path: pathlib.Path) -> tuple[int, str]:
    cmd = [sys.executable, str(agent_root / agent / script),
           str(agent_root / agent / target), flag, str(envelope_path)]
    if agent == "code-sentinel":
        cmd += ["--today", TODAY]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip().splitlines()[-1:][0] \
        if (p.stdout or p.stderr) else ""


def envelope_problems(agent: str, env: dict) -> list[str]:
    """The interchange convention, asserted instead of assumed."""
    errs = []
    if env.get("agent") != agent:
        errs.append(f"envelope agent={env.get('agent')!r}, expected {agent!r}")
    if not env.get("version"):
        errs.append("envelope has no version")
    if env.get("status") not in ENVELOPE_STATUSES:
        errs.append(f"status {env.get('status')!r} outside the closed set "
                    f"{sorted(ENVELOPE_STATUSES)}")
    cov = env.get("coverage")
    if cov and "items_in" in cov and "items_accounted" in cov:
        if cov["items_in"] != cov["items_accounted"]:
            errs.append(f"coverage does not reconcile: {cov['items_in']} != "
                        f"{cov['items_accounted']}")
    return errs


def summarise(agent: str, env: dict) -> str:
    s = env.get("status", "?")
    if agent == "jira-scribe":
        return (f"status={s} missing={env.get('missing_fields') or 'none'} "
                f"segments={env.get('stats', {}).get('segments', '?')} "
                f"reversals={len(env.get('reversals', []))}")
    if agent == "code-sentinel":
        c, t = env.get("coverage", {}), env.get("test_expectation", {})
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
    print("Each stage's envelope is written to disk and passed into the next\n"
          "stage through the flag that consumes it.\n")
    envelopes, ok = {}, True
    tmp = tempfile.TemporaryDirectory()
    for agent, prod, fixture, cons, target, flag, desc in PIPELINES:
        env = produce(ROOT, agent, prod, fixture)
        # insufficient_input is a SUCCESSFUL run: the agent correctly refused.
        good = env.get("status") in ("ok", "insufficient_input")
        problems = envelope_problems(agent, env) if good else ["did not produce "
                                                              "an envelope"]
        path = pathlib.Path(tmp.name) / f"{agent}.json"
        path.write_text(json.dumps(env), encoding="utf-8")

        code, last = consume(ROOT, agent, cons, target, flag, path)
        if code != 0:
            problems.append(f"downstream {pathlib.Path(cons).name} exited "
                            f"{code}: {last}")
        stage_ok = good and not problems
        ok &= stage_ok
        print(f"  [{'OK ' if stage_ok else 'FAIL'}] {agent:<19} {desc}")
        print(f"         {summarise(agent, env)}")
        print(f"         envelope -> {flag} {pathlib.Path(cons).name}: "
              f"exit {code}")
        for p in problems:
            print(f"         ! {p}")
        envelopes[agent] = env

    # The cross-agent check the runner (not the agents) performs.
    sc = envelopes.get("code-sentinel", {}).get("test_expectation", {})
    if sc and not sc.get("expectation_met"):
        print(f"\n  chain insight: {sc['new_branches']} new branch(es) with no "
              "test file touched -> L2-TEST-01 candidate")
    tmp.cleanup()
    return ok


def independent() -> bool:
    print("\n=== INDEPENDENCE TEST — the other two agents are DELETED ===")
    print("Each agent's FULL eval suite must pass alone, unmodified.\n")
    ok = True
    for agent, *_ in PIPELINES:
        with tempfile.TemporaryDirectory() as tmp:
            iso = pathlib.Path(tmp) / "isolated"
            iso.mkdir()
            shutil.copytree(ROOT / agent, iso / agent)
            others = [a for a, *_ in PIPELINES if a != agent]
            p = subprocess.run(
                [sys.executable, str(iso / agent / "scripts" / "run_evals.py")],
                capture_output=True, text=True, cwd=iso / agent)
            good = p.returncode == 0
            ok &= good
            tail = (p.stdout.strip().splitlines() or ["(no output)"])[-1]
            print(f"  [{'OK ' if good else 'FAIL'}] {agent:<19} "
                  f"ran with {', '.join(others)} removed")
            print(f"         {tail}")
            if not good:
                for line in p.stdout.splitlines():
                    if "FAIL" in line:
                        print(f"         {line.strip()}")
                if p.stderr.strip():
                    print(f"         {p.stderr.strip()[-300:]}")
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
