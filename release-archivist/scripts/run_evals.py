#!/usr/bin/env python3
"""Self-contained eval runner for this agent.

Runs standalone: it references no sibling agent, no shared library, and no path
outside this folder -- so it still works when the other agents are deleted from
the tree. That is the independence test from INTERCHANGE.md.

Per input: the script completes with the expected exit code, and the output is
byte-identical across 3 runs.

Usage: python scripts/run_evals.py [-v]
"""
import hashlib
import pathlib
import subprocess
import sys

AGENT = pathlib.Path(__file__).resolve().parent.parent
INPUTS = AGENT / "evals" / "inputs"

# (script, input glob or None, acceptable exit codes)
PLAN = [
    ("classify.py", "*.log", {0}),
    ("validate_output.py", "valid-*.md", {0}),
]


def run(script, arg=None):
    cmd = [sys.executable, str(AGENT / "scripts" / script)]
    if arg:
        cmd.append(str(arg))
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout


def main() -> int:
    verbose = "-v" in sys.argv
    fails = cases = 0
    print(f"evals: {AGENT.name}")
    for script, glob, ok_codes in PLAN:
        targets = sorted(INPUTS.glob(glob)) if glob else [None]
        if glob and not targets:
            print(f"  SKIP  {script} - no inputs matching {glob}")
            continue
        for t in targets:
            cases += 1
            label = f"{script} <- {t.name if t else '(no input)'}"
            digests = set()
            code = None
            for _ in range(3):
                code, out = run(script, t)
                digests.add(hashlib.md5(out.encode()).hexdigest())
            if code not in ok_codes:
                print(f"  FAIL  {label}: exit {code}, "
                      f"expected {sorted(ok_codes)}")
                fails += 1
            elif len(digests) != 1:
                print(f"  FAIL  {label}: NON-DETERMINISTIC "
                      f"({len(digests)} distinct outputs over 3 runs)")
                fails += 1
            else:
                print(f"  ok    {label}  [{next(iter(digests))[:8]} x3]")
                if verbose:
                    print("        " + run(script, t)[1].splitlines()[0][:88])

    print(f"\n{cases - fails}/{cases} passed"
          + ("" if not fails else f" - {fails} FAILURE(S)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
