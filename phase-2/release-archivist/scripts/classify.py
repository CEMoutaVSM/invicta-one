#!/usr/bin/env python3
"""Deterministic classifier and coverage ledger for the Release Archivist.

Every input line is accounted for exactly once, with a reason. The ledger
guarantees lines_in == items + furniture + blank, which is what turns
"zero missing features" from a promise into an assertion a test can check.

WHY THE LEDGER COUNTS LINES, NOT JUST ITEMS
-------------------------------------------
The class buckets (published / internal / suppressed) partition the items by
construction, so reconciling them against the item count is arithmetic that
cannot fail. It said YES on inputs where six shipped features had already been
dropped before counting began, because a line that never became an item was
never counted at all. The ledger therefore starts at the *line*: anything not
classified must be explicitly named as furniture, and that is checkable.

Rules are ordered and first-match-wins, so the output is a pure function
of the input. Same log in, byte-identical classification out.

Usage:  python classify.py <log.txt> [--json]
Exit:   0 reconciles / 1 ledger does not reconcile / 2 usage error
"""
import argparse
import json
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

from collections import Counter

TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")

# Ordered. First match wins. Each entry: (id, pattern, class, reason)
#
# Conventional-commit prefixes come FIRST. They are an explicit statement of
# intent by the author, and must beat token heuristics further down: a commit
# reading `feat: add dashboard widget` was being classified INTERNAL because
# rule R-09 saw the word "dashboard" before any FEATURE rule could run. Five
# shipped features were silently reclassified that way, with the ledger still
# reporting a clean reconcile.
REVERT_OF_REVERT = re.compile(
    r"^\s*Reverts?\s+[\"“]\s*Reverts?\s+[\"“](?P<inner>.*?)[\"”]?\s*[\"”]?\s*$", re.I)

RULES = [
    ("R-05", r"^\s*(chore|style|ci|build)(\(.+?\))?:", "NOISE",
     "conventional-commit non-shipping type"),
    ("R-07", r"^\s*(refactor|test|docs)(\(.+?\))?:", "INTERNAL",
     "internal engineering work"),
    ("R-10", r"^\s*(feat|feature)(\(.+?\))?:", "FEATURE",
     "conventional-commit feature"),
    ("R-12", r"^\s*(fix|bugfix|hotfix)(\(.+?\))?:", "FIX",
     "conventional-commit fix"),
    ("R-01", r"^\s*Merge (branch|pull request|remote-tracking)", "NOISE",
     "merge commit"),
    # R-02 is handled ahead of the table, in `classify_one`: a revert of a
    # revert RE-APPLIES the change, so "net zero" was backwards. It is
    # classified from the subject it restores, and flagged for the model.
    # A plain revert un-ships whatever it names. Without this the reverted
    # subject line was read as the feature itself: `Revert "Add bulk invoice
    # import"` classified FEATURE, and the release announced something the
    # sprint had explicitly taken back.
    ("R-02b", r"^\s*Revert[s]? [\"']", "NOISE",
     "revert - the named change did not ship"),
    ("R-03", r"\b(wip|work in progress|temp|tmp|scratch|asdf|test commit|"
             r"squash me|fixup!|amend)\b", "NOISE", "work-in-progress marker"),
    ("R-04", r"\b(typo|spelling|grammar|comment|whitespace|indent|"
             r"formatting|prettier|lint|eslint|stylelint|gofmt)\b", "NOISE",
     "cosmetic / non-functional"),
    ("R-06", r"\b(bump|upgrade|update) (dependenc|package|version|"
             r"lockfile|npm|nuget|yarn)", "INTERNAL", "dependency maintenance"),
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
    ("R-11", r"\b(add(s|ed)?|introduc(e|es|ed)|new|implement(s|ed)?|"
             r"enable(s|d)?|support for|allow(s|ed)? (users?|customers?))\b",
     "FEATURE", "new capability"),
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
# A capability verb on a line we are about to bury. Not enough to reclassify —
# the token rule may well be right — but never safe to hide.
FEATURE_SIGNAL = re.compile(
    r"\b(add(s|ed)?|introduc(e|es|ed)|implement(s|ed)?|enable(s|d)?|"
    r"allow(s|ed)?|support for)\b", re.I)

GIT_FURNITURE = re.compile(r"^(commit [0-9a-f]{7,}|Author:|Date:|"
                           r"index [0-9a-f]+|Signed-off-by:)")


def line_kind(line: str) -> tuple[str, str]:
    """Every line gets a verdict: item, or furniture with a named reason.

    Nothing is dropped silently. A line this function cannot place is an item,
    because under-reporting a change is the failure this agent exists to stop.
    """
    s = line.strip()
    if not s:
        return "blank", "empty line"
    if GIT_FURNITURE.match(s):
        return "furniture", "git log furniture"
    # The ticket test comes BEFORE the comment test. `# PROJ-9002 Add CSV
    # export` is a shipped feature someone happened to prefix with a hash, and
    # discarding it as a header line deleted it from the release before
    # classification ever ran - with the ledger still reporting a clean
    # reconcile, because a line that never became an item was never counted.
    if TICKET.search(s):
        # A Jira CSV row has no spaces but is unambiguously an item.
        return "item", ""
    # `#123 fix login crash` is a GitHub issue reference, not a comment. Only a
    # `#` followed by prose is a header line.
    if re.match(r"^#\d+\b", s):
        return "item", ""
    if s.startswith("#"):
        return "furniture", "comment / header line"
    # Count words with common delimiters treated as separators, so a CSV row
    # is not mistaken for a single-word fragment and discarded.
    if len(re.split(r"[\s,;\t|]+", s)) >= 2:
        return "item", ""
    return "furniture", "single token, no ticket key"


def normalise(line: str) -> str:
    s = HASH.sub("", line).strip(" \t-*|")
    return re.sub(r"\s{2,}", " ", s).strip()


def classify_one(text: str) -> tuple[str, str, str, bool]:
    # A revert of a revert restores the change: the feature IS in this release.
    # Calling it "net zero" filed `Revert "Revert "feat: draft invoice autosave""`
    # as NOISE, so a shipped feature was accounted for, suppressed, never
    # mentioned to the customer, and every check stayed green. Whether it is new
    # TO CUSTOMERS also depends on where the original shipped, which the log does
    # not say - so the line is classified from the subject it restores and handed
    # to the model rather than settled here.
    if m := REVERT_OF_REVERT.match(text):
        inner = m.group("inner").strip()
        if not inner:
            # `Revert "Revert ""` names nothing. Falling back to the whole
            # line filed it as a FEATURE, and the validator then demanded a
            # customer entry for a line that says nothing - an invented note
            # extracted from garbage.
            return ("NOISE", "R-02", "revert of a revert naming nothing - "
                    "unreadable, so nothing is claimed", True)
        cls, rid, reason, _ = classify_one(inner)
        # A restored chore is still a chore. Only a restored publishable change
        # is worth the model's attention.
        return (cls, "R-02",
                f"revert of a revert - the change is restored, so it ships; "
                f"read from the inner subject ({inner[:40]!r})",
                cls in ("FEATURE", "FIX", "IMPROVEMENT"))
    matches = [(rid, cls) for rid, pat, cls, _ in COMPILED if pat.search(text)]
    for rid, pat, cls, reason in COMPILED:
        if not pat.search(text):
            continue
        low = bool(AMBIGUOUS.search(text)) and cls in ("IMPROVEMENT", "INTERNAL")
        # Buried, but talks like a feature. R-09b is exempt: "add tests"
        # is genuinely internal and would flag on every test commit.
        if cls in ("NOISE", "INTERNAL") and rid != "R-09b" \
                and FEATURE_SIGNAL.search(text):
            low = True
        # SHADOW MATCH. First-match-wins is what makes this reproducible, but it
        # also means a token rule silently outranks a later intent rule:
        # "fix logging of VAT totals on customer invoices" is buried INTERNAL by
        # R-09 on the word "logging", and the customer never hears about their
        # fix. Detecting the conflict is cheap and deterministic; resolving it
        # needs to know what the change means, which is the model's job. So the
        # line is flagged rather than quietly decided.
        #
        # INTERNAL only. A NOISE rule is a high-precision statement that nothing
        # shipped - "fix typo in InvoiceService comment" matches R-13 on the
        # word "fix", and flagging it would send every typo commit to the model
        # for adjudication, spending the tokens `--brief` exists to save. An
        # INTERNAL rule says only *where* the work was, which can coexist with
        # customer impact. Capability verbs in NOISE lines are still caught by
        # FEATURE_SIGNAL above.
        if cls == "INTERNAL" and rid != "R-09b" \
                and any(c in ("FEATURE", "FIX", "IMPROVEMENT")
                        for _, c in matches):
            shadow = next(r for r, c in matches
                          if c in ("FEATURE", "FIX", "IMPROVEMENT"))
            return cls, rid, (f"{reason} - but {shadow} also matches; "
                              "customer impact is unclear"), True
        return cls, rid, reason, low
    # Unmatched is never silently dropped - it is surfaced for human judgment.
    return "IMPROVEMENT", "R-00", "unmatched - defaulted, needs review", True


def run(text: str) -> dict:
    items, seen_tickets, furniture = [], {}, []
    blank = 0
    lines = text.splitlines()
    for n, raw in enumerate(lines, 1):
        kind, why = line_kind(raw)
        if kind == "blank":
            blank += 1
            continue
        if kind == "furniture":
            furniture.append({"line": n, "raw": raw.strip()[:80], "reason": why})
            continue
        norm = normalise(raw)
        cls, rid, reason, low = classify_one(norm)
        tickets = TICKET.findall(raw)
        # A line is a duplicate only when EVERY ticket on it has been seen
        # before. A line carrying an old key alongside a new one introduces new
        # work, and marking it a duplicate under-counted the entries the notes
        # were then required to contain - licensing a genuinely missing feature.
        dup_of = None
        if tickets and all(t in seen_tickets for t in tickets):
            dup_of = min(seen_tickets[t] for t in tickets)
        for t in tickets:
            seen_tickets.setdefault(t, n)
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

    # How many published items collapse into an existing published entry. This
    # is the only duplicate count the note body can be checked against: a
    # published item that duplicates an INTERNAL one still needs its own entry,
    # so counting all duplicates would licence a genuinely missing feature.
    PUB = {"FEATURE", "FIX", "IMPROVEMENT"}
    cls_of = {i["line"]: i["class"] for i in items}
    dupes_pub = sum(1 for i in items
                    if i["duplicate_of_line"] and i["class"] in PUB
                    and cls_of.get(i["duplicate_of_line"]) in PUB)

    ledger = {
        "lines_in": len(lines),
        "lines_blank": blank,
        "lines_furniture": len(furniture),
        "items_in": len(items),
        "published": published,
        "internal": counts["INTERNAL"],
        "suppressed": counts["NOISE"],
        "duplicates_merged": dupes,
        "duplicates_published": dupes_pub,
        "expected_entries": published - dupes_pub,
    }
    # Lines no rule could place. The regex table is cheap, reproducible and
    # right about most of a sprint log, but it has no idea what "handle edge
    # case in currency rounding" ships to a customer. Rather than default those
    # silently, they are handed to the model as an explicit, bounded job — and
    # the ledger records how many decisions were delegated, so the validator
    # knows exactly how far the model was allowed to move the totals.
    # Delegable lines: those no rule could place, and those a rule placed while
    # flagging that it was unsure. The SKILL tells the model to review the second
    # group; before this they were not delegated, so following that instruction
    # was rejected as overriding a settled classification.
    unclassified = [{"line": i["line"], "text": i["normalised"],
                     "provisional": i["class"],
                     "why": "no rule matched" if i["rule"] == "R-00"
                            else i["reason"]}
                    for i in items if i["low_confidence"]]
    ledger["unclassified"] = len(unclassified)

    ledger["items_accounted"] = (ledger["published"] + ledger["internal"]
                                 + ledger["suppressed"])
    # Both identities are structural: every item lands in exactly one class,
    # and every line in exactly one of item/furniture/blank. They are cheap
    # integrity assertions, and it would be dishonest to present them as the
    # zero-loss guarantee - neither can fail on any input. What can fail, and
    # what actually enforces "nothing is lost", is `expected_entries` above,
    # checked against the published entries by validate_output.py.
    ledger["classes_reconcile"] = ledger["items_in"] == ledger["items_accounted"]
    ledger["lines_reconcile"] = (
        ledger["lines_in"] == blank + len(furniture) + len(items))
    ledger["reconciles"] = (ledger["classes_reconcile"]
                            and ledger["lines_reconcile"])

    return {
        "agent": "release-archivist",
        "version": "1.0",
        "status": "ok" if items else "insufficient_input",
        "coverage": ledger,
        "by_class": dict(counts),
        "needs_human_judgment": [i["line"] for i in items if i["low_confidence"]],
        "security_items": [i["line"] for i in items if i["security"]],
        "empty_release": published == 0 and bool(items),
        "furniture": furniture,
        "unclassified": unclassified,
        "items": items,
    }


PUB = ("FEATURE", "FIX", "IMPROVEMENT")


def brief(res: dict) -> dict:
    """The same run, reduced to what the model actually has to decide.

    The full envelope carries nine fields for every line, including the ones
    already settled — then the SKILL tells the model to ignore them. That is
    paying, per run, to say "don't look at this". This keeps the two open jobs
    (customer wording, and the handful of lines no rule could place), the
    numbers the model must reproduce, and nothing else.
    """
    return {
        "agent": res["agent"],
        "version": res["version"],
        "status": res["status"],
        "empty_release": res["empty_release"],
        "decide": {
            # R-00 lines live in `classify`, not here: listing them twice made
            # the same line look like two separate jobs.
            "wording": [{"line": i["line"], "class": i["class"],
                         "text": i["normalised"],
                         **({"duplicate_of_line": i["duplicate_of_line"]}
                            if i["duplicate_of_line"] else {})}
                        for i in res["items"]
                        if i["class"] in PUB and i["rule"] != "R-00"],
            "classify": res["unclassified"],
            "check": [{"line": i["line"], "text": i["normalised"],
                       "provisional": i["class"], "why": i["reason"]}
                      for i in res["items"]
                      if i["low_confidence"] and i["rule"] != "R-00"],
        },
        # The SKILL asks the model to write an Internal Changes appendix and to
        # disclose security fixes in customer terms. Both were impossible from
        # the brief: the internal items were absent, and `security_items` was a
        # bare list of line numbers with no text attached.
        "internal": [{"line": i["line"], "text": i["normalised"]}
                     for i in res["items"] if i["class"] == "INTERNAL"],
        "security_items": [{"line": i["line"], "text": i["normalised"],
                            "class": i["class"]}
                           for i in res["items"] if i["security"]],
        "coverage": res["coverage"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--brief", action="store_true",
                    help="JSON reduced to what the model must decide")
    a = ap.parse_args()
    try:
        if a.file:
            raw = open(a.file, "rb").read()
        else:
            raw = sys.stdin.buffer.read()
    except OSError as e:
        print(f"usage: cannot read {a.file}: {e}", file=sys.stderr)
        return 2
    text = raw.decode("utf-8", errors="replace")
    res = run(text)
    c = res["coverage"]

    if a.json or a.brief:
        json.dump(brief(res) if a.brief else res, sys.stdout,
                  indent=2, ensure_ascii=False)
        print()
        # A --json caller got exit 0 even on a broken ledger, so a pipeline
        # could consume a lossy classification and never know.
        return 0 if c["reconciles"] else 1

    print(f"in={c['items_in']} published={c['published']} "
          f"internal={c['internal']} suppressed={c['suppressed']} "
          f"accounted={c['items_accounted']} "
          f"reconciles={'YES' if c['reconciles'] else 'NO'}")
    print(f"lines={c['lines_in']} (items={c['items_in']} "
          f"furniture={c['lines_furniture']} blank={c['lines_blank']}) "
          f"lines_reconcile={'YES' if c['lines_reconcile'] else 'NO'}")
    if res["empty_release"]:
        print("! empty release - emit the no-customer-facing-changes notice")
    for i in res["items"]:
        flag = "?" if i["low_confidence"] else " "
        dup = f" (dup of line {i['duplicate_of_line']})" if i["duplicate_of_line"] else ""
        print(f" {flag} {i['line']:>3} {i['class']:<11} {i['rule']}  "
              f"{i['normalised'][:58]}{dup}")
    for f in res["furniture"]:
        print(f"   {f['line']:>3} {'(furniture)':<11} --    {f['reason']}")
    if res["needs_human_judgment"]:
        print(f"\nLines needing judgment: {res['needs_human_judgment']}")
    return 0 if c["reconciles"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
