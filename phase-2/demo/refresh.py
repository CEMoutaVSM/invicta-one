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

Usage:  python demo/refresh.py
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


def main() -> int:
    failed = []
    for (agent, src_in, name_in, parse_cmd, name_parsed,
         src_art, name_art, val_cmd) in TRACES:
        out = HERE / agent
        out.mkdir(parents=True, exist_ok=True)

        shutil.copy(REPO / agent / src_in, out / name_in)
        shutil.copy(REPO / agent / src_art, out / name_art)

        cmd = [a.replace("{input}", str(out / name_in)) for a in parse_cmd]
        code, parsed = run(agent, cmd)
        (out / name_parsed).write_text(parsed, encoding="utf-8")

        cmd = [a.replace("{artefact}", str(out / name_art))
                .replace("{parsed}", str(out / name_parsed)) for a in val_cmd]
        code, verdict = run(agent, cmd)
        (out / "4-verdict.txt").write_text(
            verdict if verdict.strip() else "(no output)\n", encoding="utf-8")

        state = "validates" if code == 0 else f"FAILS (exit {code})"
        print(f"  {agent:<20} {state}")
        if code != 0:
            failed.append(agent)
            print("      " + verdict.strip().replace("\n", "\n      ")[:400])

    if failed:
        print(f"\n{len(failed)} trace(s) no longer satisfy their contract: "
              f"{', '.join(failed)}")
        print("Fix the artefact, or the contract, before committing these.")
        return 1
    print("\nevery trace validates end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
