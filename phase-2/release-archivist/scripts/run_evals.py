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
suite was green while `evals/golden/` was read by no code at all, so flipping a
classification rule changed six decisions and nothing noticed. A golden diff is
a finding, not an inconvenience -- investigate before you regenerate.

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


def project_log(out: str) -> dict:
    d = json.loads(out)
    return {
        # `status` is projected because refusing on an empty log is a contract
        # guarantee. Omitting it meant the refusal branch could be deleted
        # wholesale and every eval still passed.
        "status": d["status"],
        "coverage": d["coverage"],
        "decisions": {str(i["line"]): {"class": i["class"], "rule": i["rule"]}
                      for i in d["items"]},
        "needs_human_judgment": d["needs_human_judgment"],
        "empty_release": d["empty_release"],
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

    # The classifier ledger, so the notes are checked against what was actually
    # classified rather than against their own arithmetic.
    _, out = run("classify.py", [INPUTS / "03-sprint42.log", "--json"])
    ledger = tmpd / "03-sprint42.json"
    ledger.write_text(out, encoding="utf-8")

    cases = [
        ("classify.py <- 03-sprint42.log", "classify.py",
         [INPUTS / "03-sprint42.log", "--json"], {0}, "03-sprint42.json"),
        ("classify.py <- adversarial-all-noise.log", "classify.py",
         [INPUTS / "adversarial-all-noise.log", "--json"], {0},
         "adversarial-all-noise.json"),
        ("classify.py <- 05-empty.log (must refuse)", "classify.py",
         [INPUTS / "05-empty.log", "--json"], {0}, "05-empty.json"),
        ("classify.py <- 03-sprint42.log --brief", "classify.py",
         [INPUTS / "03-sprint42.log", "--brief"], {0},
         "raw:03-sprint42-brief.json"),
        # The delegation guarantee, gated. Without the ledger the validator
        # cannot tell a delegated line from a settled one, so the only fixture
        # that exercised it ran ledger-less and proved nothing.
        ("validate_output.py <- adversarial-missing-feature.md (+ledger)",
         "validate_output.py",
         [INPUTS / "adversarial-missing-feature.md", "--ledger", ledger], {1}, None),
        ("validate_output.py <- adversarial-undelegated-move.md (+ledger)",
         "validate_output.py",
         [INPUTS / "adversarial-undelegated-move.md", "--ledger", ledger], {1}, None),
        ("validate_output.py <- valid-delegated.md (+ledger)", "validate_output.py",
         [INPUTS / "valid-delegated.md", "--ledger", ledger], {0}, None),
        ("validate_output.py <- valid-notes.md (+ledger)", "validate_output.py",
         [INPUTS / "valid-notes.md", "--ledger", ledger], {0}, None),
        ("validate_output.py <- valid-refusal.md", "validate_output.py",
         [INPUTS / "valid-refusal.md"], {0}, None),
        ("validate_output.py <- adversarial-leaky-notes.md", "validate_output.py",
         [INPUTS / "adversarial-leaky-notes.md"], {1}, None),
        ("validate_output.py <- adversarial-missing-feature.md",
         "validate_output.py",
         [INPUTS / "adversarial-missing-feature.md"], {1}, None),
        # Its ONLY violation is the leaked hash, so deleting the structural
        # leak checks fails this case. The multi-violation fixture cannot.
        ("validate_output.py <- adversarial-leak-only.md", "validate_output.py",
         [INPUTS / "adversarial-leak-only.md"], {1}, None),
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
                # `raw:` compares the whole envelope, used for --brief: a
                # projection would only check the fields it happened to pick,
                # and brief() was gutted to a three-field stub with every
                # eval still green.
                got = (json.loads(out) if golden.startswith("raw:")
                       else project_log(out))
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
