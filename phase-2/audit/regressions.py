#!/usr/bin/env python3
"""Every defect an auditor found, reproduced as a test that fails if it returns.

Eight independent auditors attacked these agents across three rounds. Their
findings were fixed, and the fixes were proved by scripted attacks — but those
attack scripts lived outside version control and were lost when this machine
reverted user-installed software. The fixes survived; the proof did not.

That gap mattered: `verify.sh` proves the agents work, and proved nothing about
whether an auditor's finding had quietly come back. This file closes it. Each
case names the auditor and finding it descends from, so a failure says which
defect returned rather than merely that something broke.

Usage:  python audit/regressions.py [-v]
Exit:   0 all held / 1 one or more regressions
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CS, JS, RA = ROOT / "code-sentinel", ROOT / "jira-scribe", ROOT / "release-archivist"
TODAY = "2026-08-06"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="regressions-"))
RESULTS: list[tuple[str, str, bool, str]] = []

VF = CS / "scripts/validate_findings.py"
LR = CS / "scripts/load_rules.py"
PD = CS / "scripts/parse_diff.py"
RAV = RA / "scripts/validate_output.py"
RAC = RA / "scripts/classify.py"
JSV = JS / "scripts/validate_output.py"
JSP = JS / "scripts/parse_input.py"

HEAD = "# Code Review\n\n**Verdict:** {v}\n\n## Findings\n\n"
COV = "\n## Coverage\nFiles changed: {t} · Reviewed: {r} · Skipped: {s}\n"


def sh(*cmd) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *map(str, cmd)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def w(name: str, text: str) -> pathlib.Path:
    f = TMP / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def case(tag: str, desc: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tag, desc, bool(ok), detail))


# --------------------------------------------------------------------------
# The Sentinel: the citation rule must bind whatever shape a finding takes
# --------------------------------------------------------------------------
def sentinel_shapes() -> None:
    shapes = {
        "B-04": ("#### [MAJOR] uncited via a deeper heading\n"
                 "- **Where:** `src/a.cs:1`\n"),
        "F-01": ("### **[MAJOR]** uncited via a bold heading\n"
                 "- **Where:** `src/a.cs:1`\n"),
        "E-A4": "**[BLOCKER]** uncited via bold text\n",
        "E-F1": "- [BLOCKER] uncited via a bullet\n",
        "G-11a": "| Sev | Note |\n|---|---|\n| [BLOCKER] | uncited via a table |\n",
        "G-11b": "> [MAJOR] uncited via a blockquote\n",
    }
    for tag, body in shapes.items():
        f = w(f"shape-{tag}.md", HEAD.format(v="REQUEST-CHANGES") + body
              + COV.format(t=1, r=1, s=0))
        c, o = sh(VF, f, "--today", TODAY)
        case(tag, f"uncited finding in this shape is rejected", c == 1,
             o.strip()[:150])

    # a refusal must not be a way to smuggle any of them past the checks
    f = w("refusal-bypass.md",
          "# Review\n\nStatus: insufficient_input\n\nMissing: the diff.\n\n"
          "**Verdict:** Approve\n\n**[BLOCKER]** smuggled behind a refusal\n")
    c, o = sh(VF, f, "--today", TODAY)
    case("B-01", "the refusal marker does not disable the checks", c == 1,
         o.strip()[:150])


def sentinel_precision() -> None:
    """Correct reviews must not be rejected."""
    ok_cases = {
        "E-A1": HEAD.format(v="APPROVE-WITH-COMMENTS")
        + "### [MAJOR] Nullable dereference on a new path\n"
          "- **Where:** `src/a.cs:1`\n- **Rule:** L2-LOGIC-02 — nullable\n"
        + COV.format(t=1, r=1, s=0),
        "E-A3": HEAD.format(v="REQUEST-CHANGES")
        + "### [BLOCKER] SQL built with string formatting\n"
          "- **Where:** `src/r.cs:9`\n- **Rule:** L2-SEC-04 — parameterised\n"
          "- **Why it matters:** the query is assembled with string formatting.\n"
        + COV.format(t=1, r=1, s=0),
        "E-A2": HEAD.format(v="REQUEST-CHANGES")
        + "### [MAJOR] Template not followed\n- **Where:** `src/a.cs:1`\n"
          "- **Rule:** L2-LOGIC-01 — error paths\n"
          "- **Why it matters:** the template is:\n\n```markdown\n"
          "### [TODO] summary\n- **Where:** x\n```\n"
        + COV.format(t=1, r=1, s=0),
    }
    for tag, body in ok_cases.items():
        c, o = sh(VF, w(f"ok-{tag}.md", body), "--today", TODAY)
        case(tag, "a legitimate review is accepted", c == 0, o.strip()[:150])

    f = w("refusal-good.md", "# Review\n\n**Status:** insufficient_input\n\n"
                             "**Needed:** a unified diff.\n")
    c, o = sh(VF, f, "--today", TODAY)
    case("H-09", "a refusal written to the documented template passes", c == 0,
         o.strip()[:150])


def sentinel_recall() -> None:
    c, out = sh(PD, CS / "evals/inputs/02-permissions.diff")
    pd = w("perm.json", out)
    blind = w("blind.md", "# Review\n\n**Verdict:** APPROVE\n\nNo findings.\n\n"
              + COV.format(t=3, r=2, s=1))
    c, o = sh(VF, blind, "--diff", pd, "--today", TODAY)
    case("D-06", "a review that misses an untested branch is rejected",
         c == 1 and "L2-TEST-01" in o, o.strip()[:150])

    secret = ("diff --git a/src/pay/Gateway.cs b/src/pay/Gateway.cs\n"
              "--- a/src/pay/Gateway.cs\n+++ b/src/pay/Gateway.cs\n@@ -10,2 +10,3 @@\n"
              '+    const string Key = "sk_live_51H8xQ2eZvKYlo2C";\n')
    _, out = sh(PD, w("secret.diff", secret))
    sd = w("secret.json", out)
    c, o = sh(VF, w("appr.md", "# Review\n\n**Verdict:** APPROVE\n\nNo findings.\n\n"
                    + COV.format(t=1, r=1, s=0)), "--diff", sd, "--today", TODAY)
    case("G-20", "APPROVE over an added live key is rejected",
         c == 1 and "MISSED" in o, o.strip()[:150])

    # the same key in a test file still counts
    _, out = sh(PD, w("secret-test.diff",
                      secret.replace("src/pay/Gateway.cs", "tests/pay/GatewayTests.cs")))
    c, o = sh(VF, w("appr2.md", "# Review\n\n**Verdict:** APPROVE\n\nNo findings.\n\n"
                    + COV.format(t=1, r=1, s=0)),
              "--diff", w("secret-test.json", out), "--today", TODAY)
    case("G-08", "a live key in a test file is still demanded",
         c == 1 and "MISSED" in o, o.strip()[:150])


def sentinel_parsing() -> None:
    checks = [
        ("F-04", "in-hunk ---/+++ do not create a phantom file",
         "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
         "@@ -1,4 +1,5 @@\n--- legacy sql comment\n+++ separator line added\n+ok = 1\n",
         lambda d: d["coverage"]["files_changed"] == 1),
        ("B-11", "a mixed-format diff parses both files",
         "diff --git a/src/a.cs b/src/a.cs\n--- a/src/a.cs\n+++ b/src/a.cs\n"
         "@@ -1,2 +1,3 @@\n+x = 1\n--- a/src/b.cs\n+++ b/src/b.cs\n@@ -1,2 +1,3 @@\n+y = 2\n",
         lambda d: d["coverage"]["files_changed"] == 2),
        ("E-A7b", "'for' inside a string literal is not a branch",
         "diff --git a/src/a.cs b/src/a.cs\n--- a/src/a.cs\n+++ b/src/a.cs\n"
         '@@ -1,2 +1,3 @@\n+    var m = "waiting for approval from the accountant";\n',
         lambda d: d["test_expectation"]["new_branches"] == 0),
        ("E-A7c", "a colour literal does not hide a real branch",
         "diff --git a/src/a.ts b/src/a.ts\n--- a/src/a.ts\n+++ b/src/a.ts\n"
         '@@ -1,2 +1,4 @@\n+    return dark ? "#101010" : "#ffffff";\n'
         "+    if (dark) { return 1; }\n",
         lambda d: d["test_expectation"]["new_branches"] >= 1),
        ("F-13", "foreach counts as a new branch",
         "diff --git a/src/a.cs b/src/a.cs\n--- a/src/a.cs\n+++ b/src/a.cs\n"
         "@@ -1,2 +1,3 @@\n+  foreach (var l in inv.Lines) { T += l.Net; }\n",
         lambda d: d["test_expectation"]["new_branches"] == 1),
    ]
    for tag, desc, diff, pred in checks:
        c, out = sh(PD, w(f"parse-{tag}.diff", diff))
        try:
            ok = pred(json.loads(out))
            detail = ""
        except Exception as e:
            ok, detail = False, str(e)[:120]
        case(tag, desc, ok, detail)


def sentinel_context() -> None:
    def ctx(name: str, devs: str = "", l2: str | None = None) -> pathlib.Path:
        d = TMP / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "L2-org-standards.md").write_text(
            l2 if l2 is not None
            else (CS / "context/L2-org-standards.md").read_text(encoding="utf-8"),
            encoding="utf-8")
        (d / "L3-project.md").write_text(
            (CS / "context/L3-project.md").read_text(encoding="utf-8"),
            encoding="utf-8")
        if devs:
            (d / "L3-known-deviations.md").write_text(devs, encoding="utf-8")
        return d

    c, o = sh(LR, "--context", ctx("ctx-empty", l2="# L2\n\nno table here\n"),
              "--today", TODAY)
    case("B-14", "a context that parses to no rules is a config error, not empty",
         c == 3 and "CONFIG" in o, f"exit {c}")

    c, o = sh(LR, "--context", ctx(
        "ctx-tbd",
        "### DEV-900 — unreadable expiry\nStatus: accepted | Owner: @x\n"
        "Agent behaviour: do not flag L2-SEC-04 for paths under src/\n"
        "Expires: TBD\n"), "--path", "src/x.cs", "--today", TODAY)
    case("M-03", "a deviation with an unreadable expiry does not suppress",
         "no suppressions" in o and c == 3, o.strip().splitlines()[-1][:120])

    c, o = sh(LR, "--context", ctx(
        "ctx-underscore",
        "### DEV-400 — underscore in the path\nStatus: accepted | Owner: @x\n"
        "Agent behaviour: do not flag L2-SEC-04 for paths under src/read_model\n"
        "Expires: 2027-06\n"), "--path", "src/read_model/q.cs", "--today", TODAY)
    case("F-05", "an underscore in a suppression path survives parsing",
         "L2-SEC-04" in o and "no suppressions" not in o,
         o.strip().splitlines()[-1][:120])

    # the clock, not a human, retires a deviation
    c, before = sh(LR, "--path", "src/onboarding/Saga.cs", "--today", "2026-05-14")
    c2, after = sh(LR, "--path", "src/onboarding/Saga.cs", "--today", TODAY)
    case("F-05b", "an expiry date retires a deviation on its own",
         "L3-EVENT-01" in before and "no suppressions" in after,
         "before/after differ" if before != after else "IDENTICAL")

    # path shape must not change the answer
    got = []
    for shape in ("src/reporting/readmodel/Q.cs", "./src/reporting/readmodel/Q.cs",
                  "a/src/reporting/readmodel/Q.cs", r"src\reporting\readmodel\Q.cs"):
        _, o = sh(LR, "--path", shape, "--json", "--today", TODAY)
        got.append(sorted(x["rule"] for x in
                          json.loads(o)["suppressed_for_path"][shape]))
    case("M-02", "every path shape suppresses identically",
         all(g == ["L2-SEC-04"] for g in got), str(got))

    c, o = sh(VF, CS / "evals/inputs/valid-review.md", "--context",
              ctx("ctx-bad", l2="\x00\xff not utf8"), "--today", TODAY)
    case("G-14", "an unreadable context exits 3, not 1", c == 3, f"exit {c}")


# --------------------------------------------------------------------------
# The Archivist: nothing is lost, and nothing is invented
# --------------------------------------------------------------------------
def archivist_zero_loss() -> None:
    _, lout = sh(RAC, RA / "evals/inputs/03-sprint42.log", "--json")
    ledger = w("ledger.json", lout)
    notes = (RA / "evals/inputs/valid-notes.md").read_text(encoding="utf-8")

    c, o = sh(RAV, RA / "evals/inputs/valid-notes.md", "--ledger", ledger)
    case("BASE", "the honest release notes validate", c == 0, o.strip()[:150])

    cut = "\n".join(l for l in notes.splitlines() if "Bulk invoice export" not in l)
    c, o = sh(RAV, w("dropped.md", cut), "--ledger", ledger)
    case("D-01", "dropping a shipped feature is rejected", c == 1, o.strip()[:150])

    swap = "\n".join(l for l in notes.splitlines()
                     if "Bulk invoice export" not in l).replace(
        "## Improved",
        "- **Merge branch tidy-up** — internal housekeeping. <!-- src:2 -->\n\n## Improved")
    c, o = sh(RAV, w("swap.md", swap), "--ledger", ledger)
    case("G-03", "a net-zero swap (feature out, noise in) is rejected", c == 1,
         o.strip()[:150])

    dup = "\n".join(l for l in notes.splitlines()
                    if "View-only access" not in l).replace("duplicates=0", "duplicates=1")
    c, o = sh(RAV, w("dupes.md", dup), "--ledger", ledger)
    case("H-01", "a model-authored duplicates= cannot delete a feature", c == 1,
         o.strip()[:150])

    bad = notes.replace("<!-- src:11 -->", "<!-- src:2 -->")
    c, o = sh(RAV, w("wrongsrc.md", bad), "--ledger", ledger)
    case("G-03b", "attributing an entry to a suppressed line is rejected", c == 1,
         o.strip()[:150])

    # a vague log inflates the delegable set; it must not widen the guarantee
    vague = "\n".join(f"PROJ-40{n} update the rework of the adjust handling"
                      for n in range(1, 6))
    _, vout = sh(RAC, w("vague.log", vague), "--json")
    vlc = json.loads(vout)["coverage"]
    empty = ("# Release Notes\n\n## New\n\n"
             f"<!-- Coverage: in={vlc['items_in']} published=0 "
             f"internal={vlc['internal'] + vlc['published']} "
             f"suppressed={vlc['suppressed']} accounted={vlc['items_in']} -->\n")
    c, o = sh(RAV, w("vague-notes.md", empty), "--ledger", w("vledger.json", vout))
    case("H-03", "delegation slack cannot swallow every publishable item", c == 1,
         o.strip()[:150])

    undeleg = (RA / "evals/inputs/adversarial-undelegated-move.md")
    c, o = sh(RAV, undeleg, "--ledger", ledger)
    case("H-02c", "re-classifying a line that was not delegated is rejected",
         c == 1 and "did not delegate" in o, o.strip()[:150])

    c, o = sh(RAV, RA / "evals/inputs/valid-delegated.md", "--ledger", ledger)
    case("G-06", "a properly declared delegated re-classification passes", c == 0,
         o.strip()[:150])


def archivist_leaks() -> None:
    notes = (RA / "evals/inputs/valid-notes.md").read_text(encoding="utf-8")
    _, lout = sh(RAC, RA / "evals/inputs/03-sprint42.log", "--json")
    ledger = w("ledger2.json", lout)

    hidden = ("# Release Notes\n\nHere are this month's changes.\n\n<!-- INTERNAL -->\n"
              + notes.split("\n", 1)[1])
    c, o = sh(RAV, w("hidden.md", hidden))
    case("G-05", "customer sections cannot hide behind the INTERNAL marker",
         c == 1 and "AFTER the INTERNAL marker" in o, o.strip()[:150])

    innocent = notes.replace(
        "hardening in the customer notes field.",
        "hardening in the customer notes field, including COVID-19 reporting and UTF-8 export.")
    c, o = sh(RAV, w("innocent.md", innocent), "--ledger", ledger)
    case("G-12", "'COVID-19' and 'UTF-8' are not leaked ticket keys", c == 0,
         o.strip()[:150])

    c, o = sh(RAV, w("id.md",
                     "# Release Notes\n\n## New\n"
                     "- **Invoice reference** — the list now shows the invoice ID. <!-- src:1 -->\n"
                     "- **Second thing** — another change. <!-- src:2 -->\n\n"
                     "<!-- Coverage: in=2 published=2 internal=0 suppressed=0 "
                     "accounted=2 duplicates=0 -->\n"))
    case("F-06", "the word 'ID' is not treated as an internal name", c == 0,
         o.strip()[:150])

    fenced = ("# Release Notes\n\nStatus: insufficient_input\n\nMissing: no items.\n\n"
              "The ledger template looks like:\n\n```\n"
              "<!-- Coverage: in=1 published=1 internal=0 suppressed=0 accounted=1 -->\n```\n")
    c, o = sh(RAV, w("fenced.md", fenced))
    case("G-17", "a refusal quoting the ledger in a fence is accepted", c == 0,
         o.strip()[:150])


def archivist_classify() -> None:
    checks = [
        ("E-C1", "'# PROJ-9002 Add CSV export' is an item, not a comment",
         "# PROJ-9002 Add CSV export for accountants\nfix(auth): stop drop PROJ-3\n",
         lambda d: d["coverage"]["items_in"] == 2),
        ("F-10", "'#123 fix login crash' is an item",
         "#123 fix login crash for customers\n",
         lambda d: d["coverage"]["items_in"] == 1),
        ("B-09", "a Jira CSV row is an item",
         "PROJ-3001,Done,Add multi-currency invoice totals\n",
         lambda d: d["coverage"]["items_in"] == 1),
        ("B-08", "'feat:' beats a token rule",
         "feat: add customer dashboard widget PROJ-1\n",
         lambda d: d["coverage"]["published"] == 1),
        ("H-08", "a customer fix buried by a token rule is flagged, not hidden",
         "fix logging of VAT totals on customer invoices PROJ-3002\n",
         lambda d: d["needs_human_judgment"] == [1]),
        ("C-03", "a plain revert is not published as a feature",
         'Revert "Add bulk invoice import" PROJ-9010\n',
         lambda d: d["coverage"]["published"] == 0),
        ("F-09", "a line adding a new ticket is not a duplicate",
         "feat: add CSV export PROJ-10\n"
         "feat: PROJ-10 PROJ-11 also adds XLSX export for accountants\n",
         lambda d: d["coverage"]["expected_entries"] == 2),
    ]
    for tag, desc, log, pred in checks:
        c, out = sh(RAC, w(f"log-{tag}.log", log), "--json")
        try:
            ok, detail = pred(json.loads(out)), ""
        except Exception as e:
            ok, detail = False, str(e)[:120]
        case(tag, desc, ok, detail)


# --------------------------------------------------------------------------
# The Scribe: refuse rather than invent, and do not cry fabrication
# --------------------------------------------------------------------------
def scribe() -> None:
    c, o = sh(JSP, JS / "evals/inputs/01-refinement.txt")
    d = json.loads(o)
    case("A-09", "an ambiguous actor is surfaced, never chosen",
         d["actor_ambiguous"] and d["candidates"]["actor"] is None,
         f"actor={d['candidates']['actor']} ambiguous={d['actor_ambiguous']}")

    w("admin.txt", "the admin console feels sluggish when loading the invoice list\n")
    _, o = sh(JSP, TMP / "admin.txt")
    case("M-10", "'the admin console' is not read as an actor",
         json.loads(o)["candidates"]["actor"] is None,
         f"actor={json.loads(o)['candidates']['actor']}")

    w("deadline.txt", "as an accountant I want the nightly export to complete by "
                      "23:59 so that the morning report is ready\n")
    _, o = sh(JSP, TMP / "deadline.txt")
    d = json.loads(o)
    case("F-07", "'complete by 23:59' is not parsed as a speaker",
         d["speakers"] == [] and {"23", "59"} & set(d["numeric_literals"]),
         f"speakers={d['speakers']}")

    c, o = sh(JSV, JS / "evals/inputs/adversarial-ready-only.md")
    case("B-07", "READY declared beside a MISSING marker is rejected", c == 1,
         o.strip()[:150])

    c, o = sh(JSV, JS / "evals/inputs/valid-refusal.md")
    case("F-12", "a correct refusal document passes", c == 0, o.strip()[:150])

    _, p1 = sh(JSP, JS / "evals/inputs/01-refinement.txt")
    parsed = w("p1.json", p1)
    c, o = sh(JSV, JS / "evals/inputs/adversarial-fabricated-numbers.md",
              "--parsed", parsed)
    case("D-08", "invented figures are caught under --parsed", c == 1,
         o.strip()[:150])

    # ... and figures the speaker really gave are not
    w("spoken.txt", "as an accountant I want the export to retry three times over "
                    "twenty-four hours so that transient failures recover\n")
    _, sp = sh(JSP, TMP / "spoken.txt")
    story = ("## Retry the nightly export\n\n### Context\nTransient failures need retries.\n\n"
             "### User Story\nAs an accountant, I want the export to retry, so that "
             "failures recover.\n\n### Acceptance Criteria\n1. **Given** a failure "
             "**When** the export runs **Then** it retries 3 times within 24 hours.\n\n"
             "### Technical Hints\n- Use the existing scheduler.\n\n"
             "### Out of Scope\n- Manual retries.\n\n### Open Questions\n- [ ] None.\n\n"
             "### Readiness\nREADY\n")
    c, o = sh(JSV, w("spoken.md", story), "--parsed", w("spoken.json", sp))
    case("G-18", "spoken 'three'/'twenty-four' match the digits 3/24", c == 0,
         o.strip()[:150])

    quoted = (JS / "evals/inputs/valid-story.md").read_text(encoding="utf-8").replace(
        "Support reports", "The ticket said the work was assigned to the billing team. "
                           "Support reports")
    c, o = sh(JSV, w("quoted.md", quoted))
    case("M-12", "'assigned to' inside quoted prose is not assignee metadata", c == 0,
         o.strip()[:150])

    base = (JS / "evals/inputs/valid-story.md").read_text(encoding="utf-8")
    fenced = base + ("\n\nFor reference the refusal template is:\n\n```\n"
                     "## Insufficient Input\nStatus: insufficient_input\n"
                     "**Missing:** actor\n```\n")
    c, o = sh(JSV, w("fenced-story.md", fenced))
    case("D-03", "a fenced refusal template does not make a story a refusal", c == 0,
         o.strip()[:150])


# --------------------------------------------------------------------------
# Cross-cutting: exit codes, encodings, brief/full agreement
# --------------------------------------------------------------------------
def cross_cutting() -> None:
    c, o = sh(VF, TMP / "does-not-exist.md", "--today", TODAY)
    case("M-07a", "a missing input file exits 2", c == 2 and "Traceback" not in o,
         f"exit {c}")
    c, o = sh(LR, "--today", "yesterday")
    case("M-07b", "a malformed --today exits 2", c == 2 and "Traceback" not in o,
         f"exit {c}")
    b = TMP / "binary.diff"
    b.write_bytes(b"\x00\x01\x02binary")
    c, o = sh(PD, b)
    case("M-07c", "a binary diff exits 2", c == 2 and "Traceback" not in o,
         f"exit {c}")

    c, o = sh(JSP, w("emoji.txt", "as an accountant I want the export 🎉 to work "
                                  "so that the month closes cleanly\n"))
    case("M-05", "an emoji does not crash the parser",
         c == 0 and "UnicodeEncodeError" not in o, f"exit {c}")

    # the brief envelope must stay readable by our own validators
    _, full = sh(PD, CS / "evals/inputs/02-permissions.diff")
    _, brief = sh(PD, CS / "evals/inputs/02-permissions.diff", "--brief")
    c, o = sh(VF, CS / "evals/inputs/valid-review.md",
              "--diff", w("brief.json", brief), "--today", TODAY)
    case("G-09", "a --brief diff is accepted by --diff", c == 0, o.strip()[:150])

    _, bfull = sh(JSP, JS / "evals/inputs/01-refinement.txt")
    _, bbrief = sh(JSP, JS / "evals/inputs/01-refinement.txt", "--brief")
    fj, bj = json.loads(bfull), json.loads(bbrief)
    case("G-10", "--brief keeps the fabrication guard's input",
         "numeric_literals" in bj and bj["numeric_literals"] == fj["numeric_literals"],
         "numeric_literals missing" if "numeric_literals" not in bj else "")
    case("BRIEF", "--brief agrees with the full envelope on the decisions",
         all(bj.get(k) == fj.get(k) for k in
             ("status", "missing_fields", "actor_ambiguous", "actor_source")),
         "")

    # determinism: the same input, ten times
    digests = set()
    for _ in range(10):
        _, o = sh(RAV, RA / "evals/inputs/adversarial-leaky-notes.md")
        digests.add(o)
    case("M-01", "the archivist validator is deterministic over 10 runs",
         len(digests) == 1, f"{len(digests)} distinct outputs")


def main() -> int:
    for fn in (sentinel_shapes, sentinel_precision, sentinel_recall,
               sentinel_parsing, sentinel_context, archivist_zero_loss,
               archivist_leaks, archivist_classify, scribe, cross_cutting):
        fn()

    verbose = "-v" in sys.argv
    failed = [r for r in RESULTS if not r[2]]
    print(f"auditor regressions — {len(RESULTS) - len(failed)}/{len(RESULTS)} held\n")
    for tag, desc, ok, detail in RESULTS:
        if ok and not verbose:
            continue
        print(f"  {'ok  ' if ok else 'FAIL'} [{tag}] {desc}"
              + (f"\n         {detail}" if detail and not ok else ""))
    if not failed:
        print("  every auditor finding is still fixed")
    else:
        print(f"\n{len(failed)} REGRESSION(S) - a defect an auditor found has returned")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
