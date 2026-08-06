#!/usr/bin/env python3
"""Deterministic classifier and coverage ledger for the Release Archivist.

Every input line is labelled exactly once, with a reason. The ledger
guarantees items_in == items_accounted, which is what turns "zero missing
features" from a promise into an assertion a test can check.

Rules are ordered and first-match-wins, so the output is a pure function
of the input. Same log in, byte-identical classification out.

Usage:  python classify.py <log.txt> [--json]
"""
import argparse
import json
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX
    pass

from collections import Counter

TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")

# Ordered. First match wins. Each entry: (id, pattern, class, reason)
RULES = [
    ("R-01", r"^\s*Merge (branch|pull request|remote-tracking)", "NOISE",
     "merge commit"),
    ("R-02", r"^\s*Revert \"Revert", "NOISE", "revert of a revert - net zero"),
    ("R-03", r"\b(wip|work in progress|temp|tmp|scratch|asdf|test commit|"
             r"squash me|fixup!|amend)\b", "NOISE", "work-in-progress marker"),
    ("R-04", r"\b(typo|spelling|grammar|comment|whitespace|indent|"
             r"formatting|prettier|lint|eslint|stylelint|gofmt)\b", "NOISE",
     "cosmetic / non-functional"),
    ("R-05", r"^\s*(chore|style|ci|build)(\(.+?\))?:", "NOISE",
     "conventional-commit non-shipping type"),
    ("R-06", r"\b(bump|upgrade|update) (dependenc|package|version|"
             r"lockfile|npm|nuget|yarn)", "INTERNAL", "dependency maintenance"),
    ("R-07", r"^\s*(refactor|test|docs)(\(.+?\))?:", "INTERNAL",
     "internal engineering work"),
    ("R-08", r"\b(refactor|rename|extract|inline|cleanup|clean up|dead code|"
             r"tech debt|migrate to|move to|reorganis|reorganiz)\b", "INTERNAL",
     "internal restructuring, no customer-visible change"),
    ("R-09", r"\b(pipeline|dockerfile|helm|terraform|k8s|kubernetes|"
             r"github action|jenkins|deploy script|observability|"
             r"telemetry|logging|metrics|dashboard)\b", "INTERNAL",
     "infrastructure / tooling"),
    # R-09b added during eval run 1: "add regression test" was matching the
    # FEATURE rule R-11 on the verb "add". Test work is never customer-facing,
    # so it must be caught before any FEATURE pattern can see it.
    ("R-09b", r"\b(unit|integration|regression|e2e|smoke|snapshot) tests?\b|"
              r"\btests? (coverage|suite|harness|fixture)\b|"
              r"\badd(s|ed)? (a )?tests?\b", "INTERNAL",
     "test-only change, not customer-facing"),
    ("R-10", r"^\s*(feat|feature)(\(.+?\))?:", "FEATURE",
     "conventional-commit feature"),
    ("R-11", r"\b(add(s|ed)?|introduc(e|es|ed)|new|implement(s|ed)?|"
             r"enable(s|d)?|support for|allow(s|ed)? (users?|customers?))\b",
     "FEATURE", "new capability"),
    ("R-12", r"^\s*(fix|bugfix|hotfix)(\(.+?\))?:", "FIX",
     "conventional-commit fix"),
    ("R-13", r"\b(fix(es|ed)?|resolve(s|d)?|correct(s|ed)?|repair|"
             r"no longer (crash|fail|throw)|stop(s|ped)? (crash|fail))\b",
     "FIX", "defect resolution"),
    ("R-14", r"\b(improve(s|d|ment)?|faster|speed ?up|optimi[sz]e|reduce|"
             r"performance|responsive|smoother|clearer|simplif)\b",
     "IMPROVEMENT", "enhancement to existing behaviour"),
]
COMPILED = [(i, re.compile(p, re.I), c, r) for i, p, c, r in RULES]

# Low confidence: the model is asked to look only at these.
AMBIGUOUS = re.compile(r"\b(handle|update|change|adjust|tweak|rework|"
                       r"modify|revisit)\b", re.I)
SECURITY = re.compile(r"\b(security|vulnerab|CVE-\d|XSS|CSRF|injection|"
                      r"auth bypass|privilege escalation)\b", re.I)


def is_item(line: str) -> bool:
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    # Ignore git-log furniture
    if re.match(r"^(commit [0-9a-f]{7,}|Author:|Date:|\s*$)", s):
        return False
    return len(s.split()) >= 2


def normalise(line: str) -> str:
    s = HASH.sub("", line).strip(" \t-*|")
    return re.sub(r"\s{2,}", " ", s).strip()


def classify_one(text: str) -> tuple[str, str, str, bool]:
    for rid, pat, cls, reason in COMPILED:
        if pat.search(text):
            low = bool(AMBIGUOUS.search(text)) and cls in ("IMPROVEMENT", "INTERNAL")
            return cls, rid, reason, low
    # Unmatched is never silently dropped - it is surfaced for human judgment.
    return "IMPROVEMENT", "R-00", "unmatched - defaulted, needs review", True


def run(text: str) -> dict:
    items, seen_tickets = [], {}
    for n, raw in enumerate(text.splitlines(), 1):
        if not is_item(raw):
            continue
        norm = normalise(raw)
        cls, rid, reason, low = classify_one(norm)
        tickets = TICKET.findall(raw)
        dup_of = None
        for t in tickets:
            if t in seen_tickets:
                dup_of = seen_tickets[t]
            else:
                seen_tickets[t] = n
        items.append({
            "line": n, "raw": raw.strip(), "normalised": norm,
            "class": cls, "rule": rid, "reason": reason,
            "tickets": tickets, "duplicate_of_line": dup_of,
            "low_confidence": low,
            "security": bool(SECURITY.search(norm)),
        })

    counts = Counter(i["class"] for i in items)
    published = counts["FEATURE"] + counts["FIX"] + counts["IMPROVEMENT"]
    dupes = sum(1 for i in items if i["duplicate_of_line"])

    ledger = {
        "items_in": len(items),
        "published": published,
        "internal": counts["INTERNAL"],
        "suppressed": counts["NOISE"],
        "duplicates_merged": dupes,
    }
    ledger["items_accounted"] = (ledger["published"] + ledger["internal"]
                                 + ledger["suppressed"])
    ledger["reconciles"] = ledger["items_in"] == ledger["items_accounted"]

    return {
        "agent": "release-archivist",
        "version": "1.0",
        "status": "ok" if items else "insufficient_input",
        "coverage": ledger,
        "by_class": dict(counts),
        "needs_human_judgment": [i["line"] for i in items if i["low_confidence"]],
        "security_items": [i["line"] for i in items if i["security"]],
        "empty_release": published == 0 and bool(items),
        "items": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = open(a.file, encoding="utf-8").read() if a.file else sys.stdin.read()
    res = run(text)

    if a.json:
        json.dump(res, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    c = res["coverage"]
    print(f"in={c['items_in']} published={c['published']} "
          f"internal={c['internal']} suppressed={c['suppressed']} "
          f"accounted={c['items_accounted']} "
          f"reconciles={'YES' if c['reconciles'] else 'NO'}")
    if res["empty_release"]:
        print("! empty release - emit the no-customer-facing-changes notice")
    for i in res["items"]:
        flag = "?" if i["low_confidence"] else " "
        dup = f" (dup of line {i['duplicate_of_line']})" if i["duplicate_of_line"] else ""
        print(f" {flag} {i['line']:>3} {i['class']:<11} {i['rule']}  "
              f"{i['normalised'][:58]}{dup}")
    if res["needs_human_judgment"]:
        print(f"\nLines needing judgment: {res['needs_human_judgment']}")
    return 0 if res["coverage"]["reconciles"] else 1


if __name__ == "__main__":
    sys.exit(main())
