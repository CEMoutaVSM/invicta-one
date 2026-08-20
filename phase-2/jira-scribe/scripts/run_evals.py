#!/usr/bin/env python3
"""Self-contained eval runner for this agent.

Runs standalone: it references no sibling agent, no shared library, and no path
outside this folder -- so it still works when the other agents are deleted from
the tree. That is the independence test from INTERCHANGE.md.

Per case, three assertions:

  1. the script exits with the expected code
  2. the output is byte-identical across 3 runs
  3. where a golden file exists, the DECISIONS match it exactly

(3) is the one that can actually fail on a logic change. Exit codes and
md5-across-runs are near-tautological on a pure function of a fixed file: the
suite was green while `evals/golden/` was read by no code at all. A golden diff
is a finding, not an inconvenience -- investigate before you regenerate.

Usage: python scripts/run_evals.py [-v]
Exit:  0 all passed / 1 one or more failures
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

AGENT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = AGENT / "scripts"
INPUTS = AGENT / "evals" / "inputs"
GOLDEN = AGENT / "evals" / "golden"


def run(script, args):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def project_parse(out: str) -> dict:
    d = json.loads(out)
    return {
        "status": d["status"],
        "actor": d["candidates"]["actor"],
        "actor_source": d["actor_source"],
        "actor_candidates": d["actor_candidates"],
        "actor_ambiguous": d["actor_ambiguous"],
        "missing_fields": d["missing_fields"],
        "reversals_detected": len(d["reversals"]),
    }


def expected(name: str) -> dict:
    g = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
    return {k: v for k, v in g.items()
            if not k.startswith("_") and k != "input"}


def diff_keys(got: dict, want: dict) -> list[str]:
    out = []
    for k in sorted(set(got) | set(want)):
        if got.get(k) != want.get(k):
            out.append(f"{k}: golden={want.get(k)!r} got={got.get(k)!r}")
    return out


def main() -> int:
    verbose = "-v" in sys.argv
    tmp = tempfile.TemporaryDirectory()
    tmpd = pathlib.Path(tmp.name)

    # The parsed input, so a story can be checked against what was actually
    # said. Without it the fabrication guard is built but not installed.
    _, out = run("parse_input.py", [INPUTS / "01-refinement.txt"])
    parsed = tmpd / "01-refinement.json"
    parsed.write_text(out, encoding="utf-8")

    cases = [
        ("parse_input.py <- 01-refinement.txt (transcript, must refuse)",
         "parse_input.py", [INPUTS / "01-refinement.txt"], {0},
         "01-refinement.json"),
        ("parse_input.py <- 02-braindump.txt (brain dump, happy path)",
         "parse_input.py", [INPUTS / "02-braindump.txt"], {0},
         "02-braindump.json"),
        ("parse_input.py <- 01-refinement.txt --brief", "parse_input.py",
         [INPUTS / "01-refinement.txt", "--brief"], {0}, "raw:01-refinement-brief.json"),
        ("validate_output.py <- valid-story.md", "validate_output.py",
         [INPUTS / "valid-story.md"], {0}, None),
        ("validate_output.py <- valid-refusal.md", "validate_output.py",
         [INPUTS / "valid-refusal.md"], {0}, None),
        ("validate_output.py <- adversarial-ready-with-missing.md",
         "validate_output.py",
         [INPUTS / "adversarial-ready-with-missing.md"], {1}, None),
        ("validate_output.py <- adversarial-fabricated-numbers.md (+parsed)",
         "validate_output.py",
         [INPUTS / "adversarial-fabricated-numbers.md", "--parsed", parsed],
         {1}, None),
        # One fixture per check. A fixture carrying several violations still
        # exits 1 after you delete one of the checks, so the suite stayed green
        # while the READY-with-MISSING guard - "the check that matters most" -
        # could be removed outright.
        ("validate_output.py <- adversarial-ready-only.md", "validate_output.py",
         [INPUTS / "adversarial-ready-only.md"], {1}, None),
        ("validate_output.py <- adversarial-gherkin-only.md", "validate_output.py",
         [INPUTS / "adversarial-gherkin-only.md"], {1}, None),
    ]

    fails = total = 0
    print(f"evals: {AGENT.name}")
    for label, script, args, ok_codes, golden in cases:
        total += 1
        digests, code, out = set(), None, ""
        for _ in range(3):
            code, out = run(script, args)
            digests.add(hashlib.md5(out.encode("utf-8")).hexdigest())
        problems = []
        if code not in ok_codes:
            problems.append(f"exit {code}, expected {sorted(ok_codes)}")
        if len(digests) != 1:
            problems.append(f"NON-DETERMINISTIC ({len(digests)} outputs over 3 runs)")
        if golden and not problems:
            try:
                # `raw:` compares the whole envelope, used for --brief.
                got = (json.loads(out) if golden.startswith("raw:")
                       else project_parse(out))
                problems += diff_keys(got, expected(golden.removeprefix("raw:")))
            except (json.JSONDecodeError, KeyError, OSError) as e:
                problems.append(f"golden comparison failed: {e}")
        if problems:
            fails += 1
            print(f"  FAIL  {label}")
            for p in problems:
                print(f"        {p}")
        else:
            mark = " [golden ok]" if golden else ""
            print(f"  ok    {label}  [{next(iter(digests))[:8]} x3]{mark}")
            if verbose:
                print("        " + (out.splitlines() or [""])[0][:88])

    tmp.cleanup()
    print(f"\n{total - fails}/{total} passed"
          + ("" if not fails else f" - {fails} FAILURE(S)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
