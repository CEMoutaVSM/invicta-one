#!/usr/bin/env python3
"""Regenerate the end-to-end traces in demo/.

`verify.sh` exercises the deterministic layer. It never runs a model, so it
cannot show an agent working end to end: messy input, the script's output, the
artefact the model produced, and the validator's verdict on it. That is what
these traces are for, and they are the only evidence in the repository of the
whole loop.

They rot the moment a contract changes, and they did: the archivist trace was
committed with a stored verdict of PASS while the notes it contained failed
validation with seven violations, because per-entry `src:N` attribution had been
introduced afterwards. A stale trace claiming success is worse than no trace.

So the verdicts are never written by hand. This script re-runs every step and
records what actually happened; if an artefact no longer satisfies its contract
the file says so, loudly, and this script exits 1.

Usage:  python demo/refresh.py [--check|--self-test]
        --check      fail if the committed traces are not what the code makes
        --self-test  feed the recorder a broken artefact; it must say so
Exit:   0 every trace validates / 1 at least one does not
"""
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PY = sys.executable

# (folder, raw input, parser + args, the artefact a model produced, validator flag)
TRACES = [
    ("release-archivist", "evals/inputs/03-sprint42.log", "1-input.log",
     ["scripts/classify.py", "{input}", "--json"], "2-ledger.json",
     "evals/inputs/valid-notes.md", "3-notes.md",
     ["scripts/validate_output.py", "{artefact}", "--ledger", "{parsed}"]),
    ("jira-scribe", "evals/inputs/02-braindump.txt", "1-input.txt",
     ["scripts/parse_input.py", "{input}"], "2-parsed.json",
     "evals/inputs/valid-story.md", "3-story.md",
     ["scripts/validate_output.py", "{artefact}", "--parsed", "{parsed}"]),
    ("code-sentinel", "evals/inputs/02-permissions.diff", "1-input.diff",
     ["scripts/parse_diff.py", "{input}"], "2-parsed.json",
     "evals/inputs/valid-review.md", "3-review.md",
     ["scripts/validate_findings.py", "{artefact}", "--diff", "{parsed}",
      "--today", "2026-08-06"]),
]


def run(agent: str, args: list[str]) -> tuple[int, str]:
    p = subprocess.run([PY, *[str(a) for a in args]],
                       capture_output=True, text=True, cwd=REPO / agent)
    return p.returncode, p.stdout + p.stderr


def record(trace, out: pathlib.Path, artefact: pathlib.Path | None = None):
    """Run one trace and write its files. The single place a verdict is set.

    `--self-test` drives this same function with a broken artefact, so the
    recorder cannot be reduced to printing PASS without the self-test noticing.
    """
    (agent, src_in, name_in, parse_cmd, name_parsed,
     src_art, name_art, val_cmd) = trace
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / agent / src_in, out / name_in)
    shutil.copy(artefact or (REPO / agent / src_art), out / name_art)

    cmd = [a.replace("{input}", str(out / name_in)) for a in parse_cmd]
    _, parsed = run(agent, cmd)
    (out / name_parsed).write_text(parsed, encoding="utf-8")
    # The human-readable form of the same run. It used to be written once
    # by hand and then contradicted the JSON beside it for two rounds.
    readable = name_parsed.replace("-ledger.json", "-classified.txt")
    human = out / readable
    if human.name != name_parsed:
        _, table = run(agent, [c for c in cmd if c != "--json"])
        human.write_text(table, encoding="utf-8")

    cmd = [a.replace("{artefact}", str(out / name_art))
            .replace("{parsed}", str(out / name_parsed)) for a in val_cmd]
    code, verdict = run(agent, cmd)
    (out / "4-verdict.txt").write_text(
        verdict if verdict.strip() else "(no output)" + chr(10),
        encoding="utf-8")
    return code, verdict


def self_test() -> int:
    """Break an artefact on purpose; the recorder must report it."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for trace in TRACES:
            agent, *_ , src_art, name_art, _ = trace
            good = (REPO / agent / src_art).read_text(encoding="utf-8")
            # Truncate it. Every one of the three contracts requires
            # structure further down - a coverage comment, a verdict, an
            # acceptance-criteria section - so a stump fails all of them.
            broken = chr(10).join(good.splitlines()[:3]) + chr(10)
            bad = pathlib.Path(tmp) / f"broken-{name_art}"
            bad.write_text(broken, encoding="utf-8")
            code, verdict = record(trace, pathlib.Path(tmp) / agent, bad)
            print(f"  {agent:<20} broken artefact -> "
                  f"{'REPORTED' if code != 0 else 'PASSED, which is the bug'}")
            ok &= code != 0
    print(("" if ok else "!! ") + ("the recorder still detects a broken artefact"
                                    if ok else "SELF-TEST FAILED: the recorder passed"
                                    " an artefact it should reject"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    check = "--check" in sys.argv
    failed, stale = [], []
    for trace in TRACES:
        agent = trace[0]
        out = HERE / agent
        before = {f.name: f.read_bytes() for f in out.iterdir()} \
            if out.exists() else {}
        code, verdict = record(trace, out)
        after = {f.name: f.read_bytes() for f in out.iterdir()}
        if check and before != after:
            stale.append(agent)
            for name in sorted(set(before) | set(after)):
                if before.get(name) != after.get(name):
                    stale.append(f"    {agent}/{name}")
        state = "validates" if code == 0 else f"FAILS (exit {code})"
        print(f"  {agent:<20} {state}")
        if code != 0:
            failed.append(agent)
            print("      " + verdict.strip().replace(chr(10), chr(10) + "      ")[:400])

    if failed:
        print(f"{chr(10)}{len(failed)} trace(s) no longer satisfy their contract: "
              f"{', '.join(failed)}")
        print("Fix the artefact, or the contract, before committing these.")
        return 1
    if stale:
        # Not a contract failure - a bookkeeping one. The committed trace is
        # not what the code produces today, which is the defect this script
        # was written to prevent and could not previously report.
        print(f"{chr(10)}the committed traces are stale:")
        for s in stale:
            print(f"    {s}" if not s.startswith("    ") else s)
        print("Run `python demo/refresh.py` and commit the result.")
        return 1
    print(chr(10) + "every trace validates end to end")
    return 0

if __name__ == "__main__":
    sys.exit(main())
