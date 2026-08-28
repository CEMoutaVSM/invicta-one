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
suite was green while `evals/golden/` was read by no code at all, so sabotaging
a rule changed the classification and nothing noticed. A golden diff is a
finding, not an inconvenience -- investigate before you regenerate.

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
TODAY = "2026-08-06"          # fixed, so expiry logic is reproducible


def run(script, args):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def project_diff(out: str) -> dict:
    d = json.loads(out)
    return {
        # `status` is projected because the refusal/unparseable distinction is
        # a contract guarantee. Omitting it meant that branch could be deleted
        # wholesale and every eval still passed.
        "status": d["status"],
        "coverage": d["coverage"],
        "decisions": {f["path"]: {"kind": f["kind"],
                                  "skip_reason": f["skip_reason"]}
                      for f in d["files"]},
        # Projected because it is a decision the reviewer is held to. Omitting
        # it meant the entire secret scan could be deleted with every eval and
        # every compliance check still green.
        "must_flag": d.get("must_flag", []),
        "test_expectation": d["test_expectation"],
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


def suppression_case() -> list[str]:
    """Check the suppression golden: which rules are silenced per path."""
    try:
        want = json.loads((GOLDEN / "expected-suppressions.json").read_text(
            encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read expected-suppressions.json: {e}"]
    errs = []
    for path, rules in want.items():
        if path.startswith("_"):
            continue
        code, out = run("load_rules.py", ["--path", path, "--json",
                                          "--today", TODAY])
        if code != 0:
            errs.append(f"{path}: load_rules exited {code}")
            continue
        got = sorted(s["rule"] for s
                     in json.loads(out)["suppressed_for_path"][path])
        if got != sorted(rules):
            errs.append(f"{path}: golden={sorted(rules)} got={got}")
    return errs


def main() -> int:
    verbose = "-v" in sys.argv
    tmp = tempfile.TemporaryDirectory()
    tmpd = pathlib.Path(tmp.name)

    # Parsed diff, so the review can be checked for RECALL and not only for
    # precision: a review that misses a defect the parser already proved is a
    # failed review, however well-cited its silence is.
    code, out = run("parse_diff.py", [INPUTS / "02-permissions.diff"])
    pd = tmpd / "02-permissions.json"
    pd.write_text(out, encoding="utf-8")
    # the same diff in --brief form, so the recall check is proved against the
    # envelope the model is actually handed
    _, bout = run("parse_diff.py", [INPUTS / "02-permissions.diff", "--brief"])
    pdb = tmpd / "02-permissions-brief.json"
    pdb.write_text(bout, encoding="utf-8")
    empty_ctx = tmpd / "no-context"
    empty_ctx.mkdir()

    cases = [
        ("parse_diff.py <- 02-permissions.diff", "parse_diff.py",
         [INPUTS / "02-permissions.diff"], {0}, "02-permissions.json"),
        ("parse_diff.py <- 04-mixed-format.diff", "parse_diff.py",
         [INPUTS / "04-mixed-format.diff"], {0}, "04-mixed-format.json"),
        ("parse_diff.py <- 06-empty.diff (must refuse)", "parse_diff.py",
         [INPUTS / "06-empty.diff"], {0}, "06-empty.json"),
        ("parse_diff.py <- 02-permissions.diff --brief", "parse_diff.py",
         [INPUTS / "02-permissions.diff", "--brief"], {0},
         "raw:02-permissions-brief.json"),
        # The brief envelope must stay readable by our own recall check. It was
        # renaming `files` to `review`, so --diff silently saw no files and
        # rejected a correct review.
        ("validate_findings.py <- valid-review.md (+brief diff)",
         "validate_findings.py",
         [INPUTS / "valid-review.md", "--diff", pdb, "--today", TODAY], {0}, None),
        ("load_rules.py <- context/", "load_rules.py",
         ["--today", TODAY], {0}, None),
        ("load_rules.py <- NO CONTEXT (must refuse)", "load_rules.py",
         ["--context", empty_ctx, "--today", TODAY], {3}, None),
        ("validate_findings.py <- valid-review.md (+diff)",
         "validate_findings.py",
         [INPUTS / "valid-review.md", "--diff", pd, "--today", TODAY], {0}, None),
        ("validate_findings.py <- valid-refusal.md", "validate_findings.py",
         [INPUTS / "valid-refusal.md", "--today", TODAY], {0}, None),
        ("validate_findings.py <- adversarial-uncited-review.md",
         "validate_findings.py",
         [INPUTS / "adversarial-uncited-review.md", "--today", TODAY], {1}, None),
        ("validate_findings.py <- adversarial-verdict-contradiction.md",
         "validate_findings.py",
         [INPUTS / "adversarial-verdict-contradiction.md", "--today", TODAY],
         {1}, None),
        ("validate_findings.py <- adversarial-refusal-bypass.md",
         "validate_findings.py",
         [INPUTS / "adversarial-refusal-bypass.md", "--today", TODAY], {1}, None),
        # Its ONLY violation is the style comment, so deleting the style check
        # fails this case. The multi-violation fixture above cannot do that.
        ("validate_findings.py <- adversarial-style-only.md",
         "validate_findings.py",
         [INPUTS / "adversarial-style-only.md", "--today", TODAY], {1}, None),
        # Its ONLY violation is the missing citation, so deleting the citation
        # rule fails this case. The multi-violation fixture cannot.
        ("validate_findings.py <- adversarial-uncited-only.md",
         "validate_findings.py",
         [INPUTS / "adversarial-uncited-only.md", "--today", TODAY], {1}, None),
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
                # projection only checks the fields it happened to pick, and
                # brief() was gutted to a stub with every eval still green.
                got = (json.loads(out) if golden.startswith("raw:")
                       else project_diff(out))
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

    total += 1
    errs = suppression_case()
    if errs:
        fails += 1
        print("  FAIL  load_rules.py <- expected-suppressions.json")
        for e in errs:
            print(f"        {e}")
    else:
        print("  ok    load_rules.py <- expected-suppressions.json  [golden ok]")

    tmp.cleanup()
    print(f"\n{total - fails}/{total} passed"
          + ("" if not fails else f" - {fails} FAILURE(S)"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
