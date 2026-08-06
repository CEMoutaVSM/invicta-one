#!/usr/bin/env python3
"""Contract validator for the Release Archivist.

Two things the model is not trusted on: the coverage ledger reconciling,
and internal tokens leaking into customer-facing text.

Usage: python validate_output.py <notes.md> [--ledger classify.json]
"""
import json, re, sys

COVERAGE = re.compile(r"<!--\s*Coverage:\s*in=(\d+)\s+published=(\d+)\s+"
                      r"internal=(\d+)\s+suppressed=(\d+)\s+accounted=(\d+)")
LEAK = [
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "commit hash"),
    (re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b"), "ticket key"),
    (re.compile(r"\b(PostingService|PeriodGuard|IQueryable|RabbitMQ|EF Core|"
                r"read-model|projection|middleware|repository)\b", re.I), "internal name"),
    (re.compile(r"\b(feature|bugfix|hotfix|release)/[\w.-]+"), "branch name"),
    (re.compile(r"\b(revolutionary|game-?changing|seamless|cutting-?edge)\b", re.I),
     "marketing superlative (L2-REL-06)"),
]

def customer_section(md: str) -> str:
    return md.split("<!-- INTERNAL")[0]

def validate(md: str, ledger: dict | None) -> list[str]:
    errs = []
    if "Status: insufficient_input" in md:
        return errs

    m = COVERAGE.search(md)
    if not m:
        errs.append("missing coverage audit comment - the zero-loss guarantee "
                    "is unverifiable without it")
    else:
        i, p, n, s, a = (int(x) for x in m.groups())
        if p + n + s != a:
            errs.append(f"ledger internally inconsistent: {p}+{n}+{s} != {a}")
        if i != a:
            errs.append(f"ITEMS LOST: in={i} but accounted={a} "
                        f"({i - a} item(s) vanished)")
        if ledger and ledger.get("coverage", {}).get("items_in") != i:
            errs.append(f"declared in={i} but classifier saw "
                        f"{ledger['coverage']['items_in']}")

    body = customer_section(md)
    for pat, label in LEAK:
        for hit in set(pat.findall(body)):
            hit = hit if isinstance(hit, str) else hit[0]
            errs.append(f"{label} leaked into customer-facing text: {hit!r}")

    heads = re.findall(r"^##\s+(New|Improved|Fixed)\s*$", body, re.M)
    if heads and heads != [h for h in ["New", "Improved", "Fixed"] if h in heads]:
        errs.append("sections out of contract order (New / Improved / Fixed)")

    items = re.findall(r"^-\s+\*\*(.+?)\*\*", body, re.M)
    dupes = {x for x in items if items.count(x) > 1}
    if dupes:
        errs.append(f"item appears in more than one section: {sorted(dupes)}")
    return errs

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_output.py <notes.md> [--ledger <json>]"); return 2
    ledger = None
    if "--ledger" in sys.argv:
        ledger = json.load(open(sys.argv[sys.argv.index("--ledger") + 1]))
    errs = validate(open(sys.argv[1], encoding="utf-8").read(), ledger)
    if errs:
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs: print(f"  - {e}")
        return 1
    print("PASS - ledger reconciles, no internal tokens leaked")
    return 0

if __name__ == "__main__":
    sys.exit(main())
