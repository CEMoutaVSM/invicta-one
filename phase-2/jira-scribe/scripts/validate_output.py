#!/usr/bin/env python3
"""Contract validator for the Jira Scribe.

The agent is not trusted to have followed its own output contract.
This checks. Exit 0 = valid, 1 = contract violation, 2 = usage error.

Usage: python validate_output.py <story.md> [--parsed parse_input.json]
"""
import argparse
import json
import pathlib
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX: handled via BrokenPipeError
    pass
try:  # non-ASCII input must not crash on a cp1252 console
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


REQUIRED = ["Context", "User Story", "Acceptance Criteria",
            "Technical Hints", "Out of Scope", "Open Questions", "Readiness"]

GHERKIN = re.compile(r"\*\*Given\*\*.+?\*\*When\*\*.+?\*\*Then\*\*", re.S)
STORY_LINE = re.compile(r"As an?\s+.+?,\s*I want\s+.+?,\s*so that\s+.+", re.I)
# Estimation and assignment metadata. Anchored to a line for the phrases that
# also occur in ordinary prose: a story quoting a ticket that said "assigned to
# the billing team" is not an estimate, and failing it was a false positive.
FORBIDDEN_ANY = re.compile(r"\b(story points?|\d+\s*(?:sp|pts?)\b|t-?shirt siz)", re.I)
FORBIDDEN_META = re.compile(
    r"^\s*(?:[-*+]\s*)?\*{0,2}(estimates?|assignee|assigned to|story points?)"
    r"\*{0,2}\s*:", re.I | re.M)
COMPOUND_WHEN = re.compile(r"\*\*When\*\*[^*]*\band\b[^*]*\*\*Then\*\*", re.I)
# Matched against emphasis-flattened text. `**Status:** insufficient_input`
# puts the colon inside the bold, which this pattern cannot express directly —
# and a legitimate refusal written that way was being REJECTED.
REFUSAL = re.compile(r"^\s*Status\s*:\s*insufficient_input\s*\.?\s*$", re.M | re.I)
# List markers, so `1.` in the acceptance criteria is not read as a figure the
# story invented.
ORDINAL = re.compile(r"^\s*\d+[.)]\s", re.M)


def demph(text: str) -> str:
    """Flatten markdown emphasis. Underscores are preserved deliberately:
    stripping them turns `insufficient_input` into `insufficientinput`, so a
    correct refusal stops being recognised as one."""
    return re.sub(r"[*`]+", "", text)


def mask_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering.

    A story whose acceptance criteria quote the refusal template was read as
    declaring `insufficient_input` and rejected for also delivering seven
    sections. Quoted material is not structure.
    """
    out, fence = [], None
    for line in text.split("\n"):
        s = line.lstrip()
        if fence is None:
            m = re.match(r"(`{3,}|~{3,})", s)
            if m:
                fence = m.group(1)[0] * 3
                out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if s.startswith(fence):
                fence = None
    return "\n".join(out)


def sections(md: str) -> tuple[dict, list[str]]:
    """Return (section text, section names in document order)."""
    out, order, cur = {}, [], None
    for line in md.splitlines():
        m = re.match(r"^###\s+\*{0,2}(.+?)\*{0,2}\s*$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
            order.append(cur)
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}, order


def is_refusal(md: str, sec: dict) -> tuple[bool, list[str]]:
    """A refusal is a whole-document state, not a string anyone can paste in.

    Gating on the substring alone made the marker a universal bypass: a
    document could declare READY FOR DEV, carry MISSING markers, name an
    assignee and skip every required section, and still pass by mentioning
    `insufficient_input` anywhere in the file.
    """
    flat = demph(md)
    heading = "## Insufficient Input" in flat
    marker = bool(REFUSAL.search(flat))
    if not (heading or marker):
        return False, []
    errs = []
    if not heading:
        errs.append("declares insufficient_input without an "
                    "'## Insufficient Input' section")
    if not marker:
        errs.append("failure-mode output missing explicit status line")
    if not re.search(r"Missing\s*:", flat, re.I):
        errs.append("failure-mode output must list missing fields")
    # Refusing and delivering are exclusive.
    delivered = [s for s in REQUIRED if s in sec]
    if delivered:
        errs.append("declares insufficient_input but also delivers "
                    f"{len(delivered)} contract section(s): "
                    f"{', '.join(delivered)}")
    if re.search(r"^\s*READY\b", demph(md), re.M):
        errs.append("declares insufficient_input and READY in the same document")
    return True, errs


def context_numerals(context_dir: pathlib.Path | None) -> set[str]:
    """Figures the project context legitimately supplies (`.NET 8`, `React 18`)."""
    if not context_dir:
        return set()
    f = context_dir / "L3-project.md"
    if not f.exists():
        return set()
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b",
                          f.read_text(encoding="utf-8-sig")))


def validate(md: str, parsed: dict | None,
             context_dir: pathlib.Path | None = None) -> list[str]:
    errs: list[str] = []
    md = mask_fences(md)
    sec, order = sections(md)

    refusal, refusal_errs = is_refusal(md, sec)
    if refusal:
        return refusal_errs

    # Presence and order
    for s in REQUIRED:
        if s not in sec:
            errs.append(f"missing required section: {s}")
    # Real order check. The old comparison filtered the found list by itself,
    # so it was true by construction and could never fire.
    present = [s for s in order if s in REQUIRED]
    if present != [s for s in REQUIRED if s in present]:
        errs.append(f"sections out of contract order: {' -> '.join(present)}")

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
    for m in FORBIDDEN_ANY.finditer(md):
        errs.append(f"forbidden content (estimate): {m.group(0)!r}")
    for m in FORBIDDEN_META.finditer(md):
        errs.append(f"forbidden content (estimate/assignee metadata): "
                    f"{m.group(0).strip()!r}")

    # Readiness consistency - the check that matters most. Emphasis is stripped
    # first: `**READY FOR DEV**` in bold used to slip past a bare `^READY`.
    missing_markers = len(re.findall(r"MISSING:", md))
    ready = re.search(r"^\s*READY\b", demph(sec.get("Readiness", "")), re.M)
    if missing_markers and ready:
        errs.append(f"READY declared with {missing_markers} MISSING marker(s)")
    open_qs = len(re.findall(r"^\s*-\s*\[ \]", sec.get("Open Questions", ""), re.M))
    if missing_markers > open_qs:
        errs.append(f"{missing_markers} MISSING marker(s) but only "
                    f"{open_qs} open question(s)")

    # Hallucinated numbers: any figure in the story must exist in the input.
    # Checked across EVERY section - restricting it to three meant an invented
    # threshold parked in Technical Hints was never looked at.
    if parsed:
        # Compared on a canonical form. Portuguese speakers write "1,5 seconds"
        # and the story renders it "1.5"; an exact string match called that a
        # fabrication of the speaker's own number.
        def forms(v: str) -> set[str]:
            """Every shape the same quantity is written in.

            A comma is a decimal point to a Portuguese speaker and a thousands
            separator to an English one, so `1,5` and `5,000` need opposite
            treatment. Both readings are accepted rather than guessed: writing
            a stated 5000 as `5,000` was being reported as a fabrication.
            """
            out = {v}
            plain = v.replace(",", "")          # 5,000 -> 5000
            dec = v.replace(",", ".")           # 1,5   -> 1.5
            for x in (plain, dec):
                out.add(x)
                if "." in x:
                    out.add(x.rstrip("0").rstrip("."))
            return {y for y in out if y}

        allowed: set[str] = set()
        for v in (set(parsed.get("numeric_literals", []))
                  | context_numerals(context_dir)):
            allowed |= forms(v)
        body = "\n".join(sec.get(s, "") for s in REQUIRED if s in sec)
        body = ORDINAL.sub(" ", body)
        for n in sorted(set(re.findall(r"\b\d[\d,.]*\d\b|\b\d\b", body))):
            if not (forms(n) & allowed):
                errs.append(f"value {n!r} appears in story but not in input "
                            "(possible fabrication)")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--parsed", help="parse_input.py JSON")
    ap.add_argument("--context", default=str(pathlib.Path(__file__).parent.parent
                                             / "context"))
    a = ap.parse_args()

    try:
        md = open(a.story, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"usage: cannot read {a.story}: {e}", file=sys.stderr)
        return 2
    parsed = None
    if a.parsed:
        try:
            parsed = json.load(open(a.parsed, encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"usage: cannot read --parsed {a.parsed}: {e}", file=sys.stderr)
            return 2

    errs = validate(md, parsed, pathlib.Path(a.context))
    if errs:
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("PASS - output satisfies the contract")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
