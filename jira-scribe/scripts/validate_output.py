#!/usr/bin/env python3
"""Contract validator for the Jira Scribe.

The agent is not trusted to have followed its own output contract.
This checks. Exit 0 = valid, exit 1 = contract violation.

Usage: python validate_output.py <story.md> [--parsed parse_input.json]
"""
import json
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX
    pass


REQUIRED = ["Context", "User Story", "Acceptance Criteria",
            "Technical Hints", "Out of Scope", "Open Questions", "Readiness"]

GHERKIN = re.compile(r"\*\*Given\*\*.+?\*\*When\*\*.+?\*\*Then\*\*", re.S)
STORY_LINE = re.compile(r"As an?\s+.+?,\s*I want\s+.+?,\s*so that\s+.+", re.I)
FORBIDDEN = re.compile(
    r"\b(story points?|\d+\s*(?:sp|pts?)\b|estimate[sd]?:|assignee:|"
    r"assigned to|t-?shirt siz)", re.I)
COMPOUND_WHEN = re.compile(r"\*\*When\*\*[^*]*\band\b[^*]*\*\*Then\*\*", re.I)


def sections(md: str) -> dict:
    out, cur = {}, None
    for line in md.splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def validate(md: str, parsed: dict | None) -> list[str]:
    errs: list[str] = []

    if "## Insufficient Input" in md:
        if "Status: insufficient_input" not in md:
            errs.append("failure-mode output missing explicit status line")
        if not re.search(r"\*\*Missing:\*\*", md):
            errs.append("failure-mode output must list missing fields")
        return errs

    sec = sections(md)

    # Presence and order
    found = [s for s in REQUIRED if s in sec]
    for s in REQUIRED:
        if s not in sec:
            errs.append(f"missing required section: {s}")
    if found != [s for s in REQUIRED if s in found]:
        errs.append("sections out of contract order")

    # Title
    if not re.search(r"^##\s+\S", md, re.M):
        errs.append("missing H2 title")
    title = re.search(r"^##\s+(.+)$", md, re.M)
    if title and len(title.group(1)) > 80:
        errs.append(f"title exceeds 80 chars ({len(title.group(1))})")
    if title and re.match(r"^[A-Z]+-\d+", title.group(1)):
        errs.append("title must not carry a ticket prefix")

    # User story line
    if "User Story" in sec and not STORY_LINE.search(sec["User Story"]):
        errs.append("User Story is not in 'As a / I want / so that' form")

    # Acceptance criteria
    ac = sec.get("Acceptance Criteria", "")
    crit = re.findall(r"^\s*\d+\.\s", ac, re.M)
    if not crit:
        errs.append("no numbered acceptance criteria")
    if len(GHERKIN.findall(ac)) < len(crit):
        errs.append(f"{len(crit) - len(GHERKIN.findall(ac))} AC not in "
                    "Given-When-Then form")
    if COMPOUND_WHEN.search(ac):
        errs.append("compound When detected - split into separate criteria")

    # Forbidden content
    for m in FORBIDDEN.finditer(md):
        errs.append(f"forbidden content (estimate/assignee): {m.group(0)!r}")

    # Readiness consistency - the check that matters most
    missing_markers = len(re.findall(r"MISSING:", md))
    ready = re.search(r"^READY\b", sec.get("Readiness", ""), re.M)
    if missing_markers and ready:
        errs.append(f"READY declared with {missing_markers} MISSING marker(s)")
    open_qs = len(re.findall(r"^\s*-\s*\[ \]", sec.get("Open Questions", ""), re.M))
    if missing_markers > open_qs:
        errs.append(f"{missing_markers} MISSING marker(s) but only "
                    f"{open_qs} open question(s)")

    # Hallucinated numbers: any figure in the story must exist in the input
    if parsed:
        allowed = set(parsed.get("numeric_literals", []))
        body = "\n".join(sec.get(s, "") for s in
                         ("Context", "User Story", "Acceptance Criteria"))
        for n in set(re.findall(r"\b\d+(?:[.,]\d+)?\b", body)):
            if n not in allowed and n not in {"1", "2", "3", "4", "5",
                                              "6", "7", "8", "9", "10"}:
                errs.append(f"value {n!r} appears in story but not in input "
                            "(possible fabrication)")
    return errs


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_output.py <story.md> [--parsed <json>]")
        return 2
    md = open(sys.argv[1], encoding="utf-8").read()
    parsed = None
    if "--parsed" in sys.argv:
        parsed = json.load(open(sys.argv[sys.argv.index("--parsed") + 1],
                                encoding="utf-8"))
    errs = validate(md, parsed)
    if errs:
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("PASS - output satisfies the contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
