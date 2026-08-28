#!/usr/bin/env python3
"""Findings validator for the Code Sentinel.

Makes the citation rule mechanical instead of aspirational. A finding that
cites no rule, cites a rule that is not loaded, cites a dormant rule, lands
on a suppressed path, or comments on style is rejected here — before a human
ever sees it.

This is the single highest-leverage script in the framework: it is what stops
the agent from having opinions about your architecture.

TWO DIRECTIONS, NOT ONE
-----------------------
Constraining what the agent *may* say is only half a reviewer. With `--diff`
this also checks what it *must* catch: a diff the parser proved has untested
new branches must produce an L2-TEST-01 finding against a file that actually
gained a branch. Precision without recall is a reviewer that approves
everything and is never wrong.

A REJECTED GOOD REVIEW IS AS BAD AS AN ACCEPTED BAD ONE
-------------------------------------------------------
Every check here is written to avoid firing on legitimate content. A review is
prose *about* code, so it quotes code, templates and rule IDs. Fenced blocks are
therefore masked before parsing (a ```` ``` ```` block containing `### [TODO]`
is an example, not a finding), the style check no longer matches the phrase
"string formatting", and coverage figures are read from the Coverage section
rather than from anywhere in the document.

Usage:
    python validate_findings.py <review.md> [--context DIR]
                                [--diff parse_diff.json] [--today YYYY-MM-DD]

Exit: 0 valid / 1 contract violation / 2 usage error / 3 config error
"""
import argparse
import datetime as dt
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


sys.path.insert(0, str(pathlib.Path(__file__).parent))
from load_rules import load, suppressed_for, norm_path, mask_fences  # noqa: E402

SEVERITIES = {"BLOCKER", "MAJOR", "MINOR"}
# The closed set from references/output-contract.md. Keep them in step: an
# enum here that the contract does not define rejects reviews written to spec.
VERDICTS = {"APPROVE", "APPROVE-WITH-COMMENTS", "REQUEST-CHANGES"}

# Any heading depth. Keying on `###` exactly meant a finding written with
# `####` vanished from validation entirely and passed uncited.
# Emphasis inside the heading is tolerated. `### **[MAJOR]** summary` is the
# commonest way a model writes this, and matching `[` immediately after the
# hashes meant that heading escaped BOTH the finding parser and the
# finding-shaped-text check — an uncited finding, invisible to every rule.
FINDING = re.compile(r"^#{1,6}\s*\*{0,2}\[(\w+)\]\*{0,2}\s*(.+?)\s*$", re.M)
ANY_HEADING = re.compile(r"^#{1,6}\s", re.M)
# Finding-shaped text that is NOT a contract heading — bold or a plain bullet.
# Both were routes to smuggling an uncited finding past the parser.
FINDING_LIKE = re.compile(
    r"^[ \t]*(?P<pre>(?:[-*+>|][ \t]*)?\*{0,2}(?:\|[ \t]*)?)"
    r"\[(?P<sev>\w+)\]\*{0,2}[ \t]*\S", re.M)
# A severity anywhere inside a table row or a blockquote. Bold and bullets were
# already caught; a table cell and a `>` quote were the next two shapes, and an
# uncited BLOCKER in either passed with an APPROVE verdict.
SMUGGLED = re.compile(r"^[ \t]*(?:\||>)(?P<row>.*\[(?P<sev>BLOCKER|MAJOR|MINOR|"
                      r"CRITICAL|CATASTROPHIC|WARNING)\].*)$", re.M | re.I)
WHERE = re.compile(r"^\s*[-*+]?\s*Where\s*:\s*([^\s:]+)", re.M | re.I)
WHERE_FULL = re.compile(r"^\s*[-*+]?\s*Where\s*:\s*(\S+)", re.M | re.I)
RULE = re.compile(r"^\s*[-*+]?\s*Rule\s*:\s*(L[23]-[A-Z]+-\d+)", re.M | re.I)
VERDICT = re.compile(r"^\s*[-*+]?\s*Verdict\s*:\s*([A-Za-z-]+)", re.M | re.I)
# A refusal must be a whole-document state on its own line, not a substring
# anyone can paste into a review. See `is_refusal`.
REFUSAL = re.compile(r"^\s*Status\s*:\s*insufficient_input\s*\.?\s*$", re.M | re.I)
COVERAGE_SECTION = re.compile(r"^#{1,6}\s*Coverage\s*$(.*?)(?=^#{1,6}\s|\Z)",
                              re.M | re.S)

# Things the linter owns. Mentioning them is a defect in the agent.
#
# `formatting` on its own is NOT here: "string formatting" and "date formatting"
# are ordinary technical prose, and a real SQL-injection BLOCKER was rejected as
# a style nit for containing the phrase.
STYLE = re.compile(
    r"\b(indent(?:ation)?|whitespace|line length|naming convention|camelCase|"
    r"snake_case|PascalCase|import order|brace style|trailing comma|"
    r"code formatting|formatting is inconsistent|inconsistent formatting|"
    r"prettier|eslint style|rename this|more readable if)\b", re.I)


def flat(text: str) -> str:
    """Strip markdown emphasis so field matching is format-insensitive.

    Underscores are deliberately preserved: stripping them would corrupt
    `my_file.cs` and `insufficient_input`.
    """
    return re.sub(r"[*`]+", "", text)


def blocks(md: str) -> list[dict]:
    heads = list(FINDING.finditer(md))
    # A finding body ends at the NEXT heading of any level, not at the next
    # finding. Otherwise the last finding swallows the Coverage and Suppressed
    # sections, and prose from those sections is attributed to it.
    stops = [m.start() for m in ANY_HEADING.finditer(md)]
    out = []
    for m in heads:
        later = [s for s in stops if s > m.end()]
        end = min(later) if later else len(md)
        body = md[m.end():end]
        fb = flat(body)
        w, r = WHERE.search(fb), RULE.search(fb)
        wf = WHERE_FULL.search(fb)
        out.append({"severity": m.group(1), "summary": m.group(2),
                    "path": w.group(1) if w else None,
                    "raw_where": wf.group(1) if wf else None,
                    "rule": r.group(1) if r else None,
                    "body": body})
    return out


def stray_findings(md: str, found: list[dict]) -> list[str]:
    """Finding-shaped text the contract parser did not pick up."""
    seen = {f["summary"] for f in found}
    out = []
    for m in FINDING_LIKE.finditer(md):
        eol = md.find("\n", m.start())
        line = md[m.start():eol if eol > 0 else len(md)]
        if any(s and s in line for s in seen):
            continue
        pre = m.group("pre")
        shape = ("a table row" if "|" in pre else
                 "a blockquote" if ">" in pre else
                 "bold text" if "**" in pre else "a bullet")
        out.append(f"[{m.group('sev')}] written as {shape}, not a heading - "
                   "findings must use a `### [SEVERITY] summary` heading or "
                   "they escape validation")
    for m in SMUGGLED.finditer(md):
        if any(s and s in m.group("row") for s in seen):
            continue
        shape = "a table row" if m.group(0).lstrip().startswith("|") else "a blockquote"
        out.append(f"[{m.group('sev').upper()}] written inside {shape}, not a "
                   "heading - a severity that is not a `### [SEVERITY]` heading "
                   "escapes the citation rule entirely")
    return out


def is_refusal(md: str) -> bool:
    return bool(REFUSAL.search(flat(md)))


def validate(md: str, ctx: pathlib.Path, today: dt.date,
             diff: dict | None = None) -> list[str]:
    errs: list[str] = []
    # Fenced blocks are quoted material, not contract structure. A review that
    # shows a template containing `### [TODO]` was previously credited with a
    # phantom finding and rejected for it.
    md = mask_fences(md)
    fm = flat(md)
    found = blocks(md)
    strays = stray_findings(md, found)

    # `insufficient_input` is a *successful* outcome, so it skips the checks
    # that do not apply to it. That made the marker a universal bypass. A
    # refusal is a claim about the whole document: a document that also raises
    # findings, or states a verdict, is a contradiction rather than a refusal —
    # and the finding-shaped-text check still runs, because skipping it let bold
    # findings ride in behind the marker.
    if is_refusal(md):
        contradictions = list(strays)
        if found:
            contradictions.append(
                f"declares insufficient_input but also raises {len(found)} "
                "finding(s) - a refusal reviews nothing")
        if vm := VERDICT.search(fm):
            contradictions.append(
                f"declares insufficient_input but also states a verdict "
                f"({vm.group(1).upper()}) - refusing and ruling are exclusive")
        # Liberal in what it accepts: §8's refusal template says `Needed:`, and
        # demanding `Missing:` rejected a refusal written exactly to spec.
        if not re.search(r"(Missing|Needed|Required|Reason)\s*:", fm, re.I):
            contradictions.append("refusal does not state what was missing - "
                                  "give a `Missing:` or `Needed:` line")
        return contradictions

    try:
        loaded = load(ctx, today)
    except (UnicodeDecodeError, OSError) as e:
        # `load_rules.py` exits 3 on an unreadable context; this crashed with a
        # traceback and exit 1, which is indistinguishable from "the review was
        # rejected". A config fault must never look like a verdict.
        return [f"CONFIG: cannot read context under {ctx}: {e}"]
    if not loaded.get("usable"):
        # Blaming each finding here would hide the real problem, which is
        # configuration, not the review.
        detail = "; ".join(loaded.get("parse_errors", [])[:3])
        return [f"CONFIG: rule set is not usable (mode={loaded['mode']}, "
                f"active={loaded['counts']['active']}, context={ctx}). The "
                "agent cannot validate a review it had no rules to produce."
                + (f" {detail}" if detail else "")]
    active = {r["id"] for r in loaded["active_rules"]}
    dormant = {r["id"] for r in loaded["dormant_rules"]}

    errs.extend(strays)

    for f in found:
        tag = f"[{f['severity']}] {f['summary'][:48]}"

        if f["severity"] not in SEVERITIES:
            errs.append(f"{tag}: invalid severity (allowed: "
                        f"{', '.join(sorted(SEVERITIES))})")

        # THE CITATION RULE
        if not f["rule"]:
            errs.append(f"{tag}: NO RULE CITED - agent may not raise "
                        "findings it cannot attribute")
        elif f["rule"] in active:
            pass                       # active wins if a rule is in both sets
        elif f["rule"] in dormant:
            errs.append(f"{tag}: cites {f['rule']} which is DRAFT/dormant "
                        "and must not produce findings")
        else:
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
    # READY-declared-with-MISSING in the Scribe. Matched case-insensitively:
    # `Approve` used to slip past a check keyed on `APPROVE`.
    vm = VERDICT.search(fm)
    sev = {f["severity"] for f in found}
    if vm:
        verdict = vm.group(1).upper()
        if verdict not in VERDICTS:
            errs.append(f"unknown verdict {vm.group(1)!r} (allowed: "
                        f"{', '.join(sorted(VERDICTS))})")
        if verdict == "APPROVE" and sev:
            errs.append(f"verdict APPROVE contradicts {len(found)} finding(s)")
        if verdict != "REQUEST-CHANGES" and "BLOCKER" in sev:
            errs.append(f"verdict {verdict} declared with a BLOCKER present")
        if verdict in ("REQUEST-CHANGES", "APPROVE-WITH-COMMENTS") and not sev:
            errs.append(f"verdict {verdict} with no findings")
    else:
        errs.append("missing Verdict line")

    if len(found) > 10:
        errs.append(f"{len(found)} findings exceeds the cap of 10")

    # Coverage must reconcile. Read from the Coverage SECTION: scanning the
    # whole document with re.S spliced figures out of quoted PR prose.
    finding_paths = {norm_path(f["path"]) for f in found if f["path"]}
    covsec = COVERAGE_SECTION.search(fm)
    cov = re.search(r"Files changed:\s*(\d+).*?Reviewed:\s*(\d+).*?"
                    r"Skipped:\s*(\d+)", covsec.group(1), re.S) if covsec else None
    rev = None
    if cov:
        tot, rev, skip = (int(x) for x in cov.groups())
        if rev + skip != tot:
            errs.append(f"coverage does not reconcile: {rev} + {skip} != {tot}")
        # Arithmetic alone was satisfiable by a lie: 4 findings across 4 files
        # while claiming `Reviewed: 0` still summed correctly.
        if len(finding_paths) > rev:
            errs.append(f"claims Reviewed: {rev} but raises findings against "
                        f"{len(finding_paths)} distinct file(s) - a file you "
                        "did not review cannot yield a finding")
    elif found or diff:
        # Required whenever there is a diff to reconcile against, not only when
        # findings exist: a coverage-free "APPROVE, no findings" otherwise
        # skipped the reviewed-versus-reviewable check entirely.
        errs.append("missing Coverage section")

    # --- recall: what the review MUST catch, given the parsed diff ----------
    if diff:
        dcov = diff.get("coverage", {})
        reviewable = {norm_path(f["path"]) for f in diff.get("files", [])
                      if f.get("kind") == "review"}
        tests = {norm_path(f["path"]) for f in diff.get("files", [])
                 if f.get("kind") == "test"}
        skipped = {norm_path(f["path"]) for f in diff.get("files", [])
                   if f.get("kind") == "skip"}

        if rev is not None and dcov.get("reviewable") is not None:
            # A test file is a legitimate place to find a defect - a hardcoded
            # production secret in a test is still a hardcoded production
            # secret - so the reviewed count may exceed `reviewable`.
            if rev < dcov["reviewable"]:
                errs.append(f"claims Reviewed: {rev} but the diff has "
                            f"{dcov['reviewable']} reviewable file(s)")
            if rev > dcov["reviewable"] + len(tests):
                errs.append(f"claims Reviewed: {rev}, more than the "
                            f"{dcov['reviewable'] + len(tests)} file(s) it was "
                            "permitted to review")
        if cov and dcov.get("files_changed") is not None \
                and int(cov.group(1)) != dcov["files_changed"]:
            errs.append(f"claims Files changed: {cov.group(1)} but the diff "
                        f"has {dcov['files_changed']}")

        # Defects the parser is certain about. Recall used to hinge only on new
        # branches, so a diff that added a live secret while touching no control
        # flow demanded nothing and an APPROVE passed.
        for must in diff.get("must_flag", []):
            want = norm_path(must["path"])
            if not any(f["rule"] == must["rule"] and f["path"]
                       and norm_path(f["path"]) == want for f in found):
                errs.append(
                    f"MISSED: the parser found a {must['what']} added in "
                    f"{must['path']}, and no finding cites {must['rule']} "
                    "against that file. This one is not a judgement call.")

        te = diff.get("test_expectation", {})
        if te and not te.get("expectation_met", True):
            branchy = {norm_path(f["path"]) for f in diff.get("files", [])
                       if f.get("new_branches") or f.get("removed_branches")}
            cited = {f["path"] and norm_path(f["path"]) for f in found
                     if f["rule"] == "L2-TEST-01"}
            if not (cited & branchy):
                errs.append(
                    f"MISSED: {te.get('new_branches')} new branch(es) with "
                    f"{te.get('test_files_touched')} test file(s) touched, but "
                    "no finding cites L2-TEST-01 against a file that gained a "
                    "branch. The parser proved this defect exists; the review "
                    "has to report it, on the right file.")

        # A finding must land on a line the diff actually touched. Citing a line
        # nowhere near a hunk is a fabricated location, and it passed silently.
        hunks = {norm_path(f["path"]): [h.get("new_start") for h in f.get("hunks", [])]
                 for f in diff.get("files", []) if f.get("kind") == "review"}
        for f in found:
            if not f["path"] or ":" not in (f["raw_where"] or ""):
                continue
            try:
                line = int(f["raw_where"].rsplit(":", 1)[1])
            except ValueError:
                continue
            starts = hunks.get(norm_path(f["path"]))
            if starts and all(abs(line - s) > 400 for s in starts if s):
                errs.append(
                    f"{f['path']}:{line} is not inside any hunk of this diff "
                    f"(hunks start at {', '.join(str(s) for s in starts)}) - "
                    "cite a line the change actually touched")

        # A generated file may not be reviewed, but if a credential was
        # committed to one the reviewer must be free to say so.
        demanded = {norm_path(m["path"]) for m in diff.get("must_flag", [])}
        for p in sorted(finding_paths & skipped - demanded):
            errs.append(f"finding raised on {p}, which the parser marked "
                        "skip (generated/vendored) - it must not be reviewed")
        for p in sorted(finding_paths - reviewable - tests - skipped):
            errs.append(f"finding raised on {p}, which is not in the diff")

    if not found and not re.search(r"no findings|nothing to flag|looks (?:fine|sound)",
                                   md, re.I):
        errs.append("zero findings but the review does not say so plainly")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("review")
    ap.add_argument("--context", default=str(pathlib.Path(__file__).parent.parent
                                             / "context"))
    ap.add_argument("--diff", help="parse_diff.py JSON, to check recall")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    try:
        today = dt.date.fromisoformat(a.today)
    except ValueError:
        print(f"usage: --today expects YYYY-MM-DD, got {a.today!r}",
              file=sys.stderr)
        return 2
    try:
        md = open(a.review, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"usage: cannot read {a.review}: {e}", file=sys.stderr)
        return 2
    diff = None
    if a.diff:
        try:
            diff = json.load(open(a.diff, encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"usage: cannot read --diff {a.diff}: {e}", file=sys.stderr)
            return 2

    errs = validate(md, pathlib.Path(a.context), today, diff)
    if errs and errs[0].startswith("CONFIG:"):
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 3
    if errs:
        print(f"FAIL ({len(errs)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("PASS - all findings cited, scoped and in contract")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
