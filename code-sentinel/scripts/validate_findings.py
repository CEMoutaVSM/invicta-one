#!/usr/bin/env python3
"""Findings validator for the Code Sentinel.

Makes the citation rule mechanical instead of aspirational. A finding that
cites no rule, cites a rule that is not loaded, cites a dormant rule, lands
on a suppressed path, or comments on style is rejected here — before a human
ever sees it.

This is the single highest-leverage script in the framework: it is what stops
the agent from having opinions about your architecture.

Usage: python validate_findings.py <review.md> [--context DIR] [--today YYYY-MM-DD]
"""
import argparse
import datetime as dt
import pathlib
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX
    pass


sys.path.insert(0, str(pathlib.Path(__file__).parent))
from load_rules import load, suppressed_for  # noqa: E402

SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
FINDING = re.compile(r"^###\s*\[(\w+)\]\s*(.+?)\s*$", re.M)
WHERE = re.compile(r"^\s*-\s*\*\*Where:\*\*\s*`?([^`\s:]+)", re.M)
RULE = re.compile(r"^\s*-\s*\*\*Rule:\*\*\s*(L[23]-[A-Z]+-\d+)", re.M)

# Things the linter owns. Mentioning them is a defect in the agent.
STYLE = re.compile(
    r"\b(indent(?:ation)?|whitespace|line length|naming convention|camelCase|"
    r"snake_case|PascalCase|import order|brace style|trailing comma|"
    r"formatting|prettier|eslint style|rename this|more readable if)\b", re.I)


def blocks(md: str) -> list[dict]:
    heads = list(FINDING.finditer(md))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        body = md[m.end():end]
        w, r = WHERE.search(body), RULE.search(body)
        out.append({"severity": m.group(1), "summary": m.group(2),
                    "path": w.group(1) if w else None,
                    "rule": r.group(1) if r else None,
                    "body": body})
    return out


def validate(md: str, ctx: pathlib.Path, today: dt.date) -> list[str]:
    errs: list[str] = []
    if "Status: insufficient_input" in md:
        return errs

    loaded = load(ctx, today)
    if not loaded.get("usable"):
        # Blaming each finding here would hide the real problem, which is
        # configuration, not the review.
        return [f"CONFIG: rule set is empty (mode={loaded['mode']}, "
                f"context={ctx}). The agent cannot validate a review it had "
                "no rules to produce."]
    active = {r["id"] for r in loaded["active_rules"]}
    dormant = {r["id"] for r in loaded["dormant_rules"]}

    found = blocks(md)
    for f in found:
        tag = f"[{f['severity']}] {f['summary'][:48]}"

        if f["severity"] not in SEVERITIES:
            errs.append(f"{tag}: invalid severity (allowed: "
                        f"{', '.join(sorted(SEVERITIES))})")

        # THE CITATION RULE
        if not f["rule"]:
            errs.append(f"{tag}: NO RULE CITED - agent may not raise "
                        "findings it cannot attribute")
        elif f["rule"] in dormant:
            errs.append(f"{tag}: cites {f['rule']} which is DRAFT/dormant "
                        "and must not produce findings")
        elif f["rule"] not in active:
            errs.append(f"{tag}: cites {f['rule']} which is not in the "
                        "loaded rule set")

        if not f["path"]:
            errs.append(f"{tag}: no location given")
        elif f["rule"]:
            for s in suppressed_for(loaded, f["path"]):
                if s["rule"] == f["rule"]:
                    errs.append(f"{tag}: {f['rule']} is SUPPRESSED on "
                                f"{f['path']} by {s['deviation']} - this is a "
                                "false positive the project context already "
                                "ruled out")

        if m := STYLE.search(f["body"]):
            errs.append(f"{tag}: style/formatting comment ({m.group(0)!r}) "
                        "- the linter owns this")

    # Verdict must agree with the findings - same class of bug as
    # READY-declared-with-MISSING in the Scribe.
    vm = re.search(r"\*\*Verdict:\*\*\s*([A-Z-]+)", md)
    sev = {f["severity"] for f in found}
    if vm:
        verdict = vm.group(1)
        if verdict == "APPROVE" and sev:
            errs.append(f"verdict APPROVE contradicts {len(found)} finding(s)")
        if verdict != "REQUEST-CHANGES" and "BLOCKER" in sev:
            errs.append(f"verdict {verdict} declared with a BLOCKER present")
        if verdict == "REQUEST-CHANGES" and not sev:
            errs.append("verdict REQUEST-CHANGES with no findings")
    else:
        errs.append("missing Verdict line")

    if len(found) > 10:
        errs.append(f"{len(found)} findings exceeds the cap of 10")

    # Coverage must reconcile
    cov = re.search(r"Files changed:\s*(\d+).*?Reviewed:\s*(\d+).*?"
                    r"Skipped:\s*(\d+)", md, re.S)
    if cov:
        tot, rev, skip = (int(x) for x in cov.groups())
        if rev + skip != tot:
            errs.append(f"coverage does not reconcile: {rev} + {skip} != {tot}")
    elif found:
        errs.append("missing Coverage section")

    if not found and not re.search(r"no findings|nothing to flag|looks (?:fine|sound)",
                                   md, re.I):
        errs.append("zero findings but the review does not say so plainly")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("review")
    ap.add_argument("--context", default=str(pathlib.Path(__file__).parent.parent
                                             / "context"))
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    errs = validate(open(a.review, encoding="utf-8").read(),
                    pathlib.Path(a.context), dt.date.fromisoformat(a.today))
    if errs:
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("PASS - all findings cited, scoped and in contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
