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


def secret_detection() -> None:
    """`must_flag` must demand only what is certain, and miss nothing obvious.

    This was the weakest thing in the codebase on both sides at once: it raised
    security demands on comments, placeholders and vault-entry names — forcing
    an honest reviewer to fabricate a finding in order to pass — while missing
    real keys split across a concatenation or committed to a generated file.
    """
    def diff_for(line: str, path: str = "src/S.cs") -> pathlib.Path:
        return w(f"sec-{abs(hash(line + path))}.diff",
                 f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
                 f"@@ -1,2 +1,3 @@\n{line}\n")

    no_demand = {
        "J-01": ('+ // api_key = "your-key-here"', "an example in a comment"),
        "J-07": ('+ password = "changeme";', "a placeholder default"),
        "J-02": ('+ secret = "billing-api-key";', "a vault entry name"),
    }
    for tag, (line, what) in no_demand.items():
        d = json.loads(sh(PD, diff_for(line))[1])
        case(tag, f"{what} does not demand a security finding",
             not d["must_flag"], json.dumps(d["must_flag"])[:120])

    must = {
        "G-20b": ('+ const k = "sk_live_51H8xQ2eZvKYlo2CabcdEF";', "a live key"),
        "J-08": ('+ const k = "sk_live_51H8x" + "Q2eZvKYlo2C";',
                 "a key split across a concatenation"),
    }
    for tag, (line, what) in must.items():
        d = json.loads(sh(PD, diff_for(line))[1])
        case(tag, f"{what} is demanded", bool(d["must_flag"]),
             json.dumps(d["must_flag"])[:120])

    d = json.loads(sh(PD, diff_for('+ const k = "sk_live_51H8xQ2eZvKYlo2CabcdEF";',
                                   "dist/bundle.min.js"))[1])
    case("J-09", "a live key in a generated file is still demanded",
         bool(d["must_flag"]), json.dumps(d["must_flag"])[:120])

    # pytest naming must count as a test, or an honest review is rejected for
    # missing a defect that does not exist
    _, out = sh(PD, w("pytest.diff",
                      "diff --git a/src/calc.py b/src/calc.py\n"
                      "--- a/src/calc.py\n+++ b/src/calc.py\n@@ -1,2 +1,3 @@\n"
                      "+    if total > 0:\n"
                      "diff --git a/test_calc.py b/test_calc.py\n"
                      "--- a/test_calc.py\n+++ b/test_calc.py\n@@ -1,2 +1,3 @@\n"
                      "+    assert calc(1) == 1\n"))
    d = json.loads(out)
    case("J-03", "pytest's test_*.py naming counts as a test file",
         d["test_expectation"]["test_files_touched"] == 1
         and d["test_expectation"]["expectation_met"],
         json.dumps(d["test_expectation"]))

    # the NO-CONTEXT refusal must not embed a path, or its digest never repeats
    a = TMP / "nc-a"
    b = TMP / "nc-bbbbbbbbbbbb"
    a.mkdir(exist_ok=True)
    b.mkdir(exist_ok=True)
    _, o1 = sh(LR, "--context", a, "--today", TODAY)
    _, o2 = sh(LR, "--context", b, "--today", TODAY)
    case("K-06", "the NO-CONTEXT refusal is byte-identical whatever the path",
         o1 == o2, "differs by context directory")


def false_positives() -> None:
    """Correct work that earlier versions rejected."""
    w("k4.txt", "as an accountant I want the export to handle 5000 rows in 30 "
                "seconds so that month end is quick\n")
    _, p = sh(JSP, TMP / "k4.txt")
    story = ("## Export large invoice lists\n\n### Context\nMonth end needs speed.\n\n"
             "### User Story\nAs an accountant, I want the export to handle large "
             "lists, so that month end is quick.\n\n### Acceptance Criteria\n"
             "1. **Given** a list of 5,000 rows **When** I export **Then** it "
             "completes within 30 seconds.\n\n### Technical Hints\n- Stream it.\n\n"
             "### Out of Scope\n- Scheduled exports.\n\n### Open Questions\n"
             "- [ ] None.\n\n### Readiness\nREADY\n")
    c, o = sh(JSV, w("k4.md", story), "--parsed", w("k4.json", p))
    case("J-04", "a stated 5000 written as '5,000' is not a fabrication", c == 0,
         o.strip()[:150])

    notes = (RA / "evals/inputs/valid-notes.md").read_text(encoding="utf-8")
    _, lout = sh(RAC, RA / "evals/inputs/03-sprint42.log", "--json")
    sla = notes.replace("hardening in the customer notes field.",
                        "hardening in the customer notes field, meeting our "
                        "SLA-95 target for US-2026.")
    c, o = sh(RAV, w("sla.md", sla), "--ledger", w("led2.json", lout))
    case("J-05", "'SLA-95' and 'US-2026' are not leaked ticket keys", c == 0,
         o.strip()[:150])

    # ... while the release's real ticket keys still are
    leaky = notes.replace("export a filtered invoice list to CSV.",
                          "export a filtered invoice list to CSV (PROJ-2811).")
    c, o = sh(RAV, w("leaky.md", leaky), "--ledger", w("led3.json", lout))
    case("J-05b", "a ticket key from this release IS caught",
         c == 1 and "PROJ-2811" in o, o.strip()[:150])


def ledger_honesty() -> None:
    """Without the classifier ledger the guarantee is not checkable, and the
    tool must not claim otherwise. It printed `PASS - ledger reconciles` over
    notes that had dropped five features."""
    c, o = sh(RAV, RA / "evals/inputs/valid-notes.md")
    case("J-10", "without --ledger the tool says what it did NOT check",
         c == 0 and "NOT CHECKED" in o and "ledger reconciles" not in o,
         o.strip()[:200])
    _, lout = sh(RAC, RA / "evals/inputs/03-sprint42.log", "--json")
    c, o = sh(RAV, RA / "evals/inputs/valid-notes.md",
              "--ledger", w("led4.json", lout))
    case("J-10b", "with --ledger it says the guarantee was actually checked",
         c == 0 and "against the classifier" in o, o.strip()[:200])


# --------------------------------------------------------------------------
# Round five. Auditor L attacked the round-four repairs; auditor M read the
# submission cold. Both directions of the secret scanner were open again.
# --------------------------------------------------------------------------
def round_five() -> None:
    import json

    D = chr(10).join   # diffs are built from lists; no escapes to mangle

    # L-1: a vendor's published example key must never DEMAND a finding. AWS
    # documents AKIAIOSFODNN7EXAMPLE on its own site, and a negative test
    # asserting a malformed key is rejected legitimately contains a PRIVATE
    # KEY header. Demanding one forces an honest reviewer to fabricate.
    d = D(['--- a/tests/test_mask.py', '+++ b/tests/test_mask.py',
           '@@ -1,2 +1,4 @@',
           '+    assert mask("AKIAIOSFODNN7EXAMPLE") == "AKIA****"',
           '+    bad = "-----BEGIN PRIVATE KEY-----"', ''])
    c, o = sh(PD, w("l1.diff", d))
    j = json.loads(o)
    case("L-01", "a published example key is advisory, never a demand",
         not j["must_flag"] and len(j["possible_secrets"]) == 2,
         str(j["must_flag"])[:200])

    # L-2: comments were stripped by a regex that read the // in a URL as the
    # start of a comment, deleting a live credential before anything saw it.
    d = D(['--- a/src/Db.cs', '+++ b/src/Db.cs', '@@ -1,2 +1,3 @@',
           '+CONN = "postgres://admin:prod-sk-9f8e7d6c5b4a@db.internal:5432/app"', ''])
    c, o = sh(PD, w("l2.diff", d))
    case("L-02", "a credential inside a URL is still demanded",
         any(m["rule"] == "L2-SEC-01" for m in json.loads(o)["must_flag"]),
         o[:200])

    # ...and one written in a comment is still not demanded.
    d = D(['--- a/src/Db.cs', '+++ b/src/Db.cs', '@@ -1,2 +1,3 @@',
           '+// example: key = "sk_live_9fj3kd8sla02mfk3"', ''])
    c, o = sh(PD, w("l2b.diff", d))
    case("L-02b", "a credential in a comment is not demanded",
         not json.loads(o)["must_flag"], o[:160])

    # L-3: quoting the PR description is a documented input, not smuggling.
    review = (CS / "evals/inputs/valid-review.md").read_text(encoding="utf-8")
    quoted = review + D(["", "> This is a [BLOCKER] for the August release.", ""])
    c, o = sh(VF, w("l3.md", quoted), "--today", "2026-08-06")
    case("L-03", "a review may quote a severity word from the PR",
         c == 0, o.strip()[:200])

    # ...and a PR quote that OPENS with the tag is legitimate too. Position
    # cannot separate the reviewer's voice from quoted input; emphasis can, so
    # a blockquote is now read as input and L-03b's assertion was retired
    # deliberately in favour of the four below.
    lead = review + D(["", "> [BLOCKER] must land before the August release", ""])
    c, o = sh(VF, w("l3b.md", lead), "--today", "2026-08-06")
    case("N-05", "a PR quote may open with a severity tag", c == 0,
         o.strip()[:200])

    # N-4: an emphasised severity is the reviewer asserting one, wherever it
    # sits. Mid-paragraph bold and <b> tags passed every check while reading to
    # a human as exactly what they are.
    for tag, body in (("bold", "One aside: **[BLOCKER]** the auth check can be "
                               "bypassed."),
                      ("html", "Note <b>[BLOCKER] SQL injection</b> here."),
                      ("under", "Also __[MAJOR]__ the retry loop never exits.")):
        c, o = sh(VF, w(f"n4-{tag}.md", review + D(["", body, ""])),
                  "--today", "2026-08-06")
        case(f"N-04-{tag}", f"an uncited severity in {tag} emphasis is caught",
             c == 1, o.strip()[:160])

    # ...and the shapes that were already caught stay caught.
    c, o = sh(VF, w("n4-cell.md", review + D(["", "| [MAJOR] | x.cs | hidden |", ""])),
              "--today", "2026-08-06")
    case("N-04-cell", "a severity leading a table cell is still caught",
         c == 1, o.strip()[:160])
    # L-4: reading keys from the ledger made the check exact, and blind to any
    # key the ledger had not heard of - which passed with a false all-clear.
    notes = (RA / "evals/inputs/valid-notes.md").read_text(encoding="utf-8")
    leak = notes.replace("rounding is now consistent",
                         "rounding is now consistent (tracked as ACME-4521)", 1)
    c, o = sh(RAV, w("l4.md", leak))
    case("L-04", "a ticket key absent from the ledger still counts as a leak",
         c == 1 and "ACME-4521" in o, o.strip()[:160])

    # ...and the false positives that caused the narrowing stay fixed.
    fine = notes.replace("rounding is now consistent",
                         "rounding is now consistent, meeting SLA-95 under "
                         "US-2026 rules", 1)
    c, o = sh(RAV, w("l4b.md", fine))
    case("L-04b", "SLA-95 and US-2026 are not ticket keys", c == 0,
         o.strip()[:160])

    # L-6: the trace recorder certified itself - forcing its exit code to zero
    # left verify.sh green. It now proves it can still say no.
    c, o = sh(ROOT / "demo/refresh.py", "--self-test")
    case("L-06", "the trace recorder detects a broken artefact",
         c == 0, o.strip()[-200:])

    # M-3: a revert of a revert RE-APPLIES the change. Filing it net zero
    # shipped a feature, accounted for it, suppressed it, and told nobody.
    log = D([chr(82) + 'evert "Revert "feat: draft invoice autosave""', ""])
    c, o = sh(RAC, w("m3.log", log), "--json")
    it = json.loads(o)["items"][0]
    case("R5-03", "a revert of a revert ships, and is flagged for the model",
         it["class"] == "FEATURE" and it["low_confidence"],
         f'{it["class"]} low={it["low_confidence"]}')

    # ...but a restored chore is still a chore, and costs no tokens.
    log = D([chr(82) + 'evert "Revert "chore: bump deps""', ""])
    c, o = sh(RAC, w("m3b.log", log), "--json")
    it = json.loads(o)["items"][0]
    case("R5-03b", "a restored chore stays noise",
         it["class"] == "NOISE" and not it["low_confidence"], it["class"])

    # M-1/M-2: every SKILL.md claims its Eval Log is generated from the runner
    # and cannot drift. The generator was lost and the tables drifted, so the
    # one machine-checkable sentence in the submission became its only false
    # one. It is enforced here now.
    c, o = sh(ROOT / "audit/refresh_eval_logs.py", "--check")
    case("R5-01", "every committed Eval Log reproduces from a fresh run",
         c == 0, o.strip()[-300:])
    # M-9: the --brief saving was written as 17% and is 21% after this round's
    # changes. A prose number that drifts silently is exactly what this round
    # was about, so the figure in SKILL.md is measured rather than remembered.
    import subprocess
    f = CS / "evals/inputs/02-permissions.diff"
    size = lambda *a: len(subprocess.run([sys.executable, str(PD), str(f), *a],
                                         capture_output=True, text=True).stdout)
    pct = round(100 * (size() - size("--brief")) / size())
    claim = (CS / "SKILL.md").read_text(encoding="utf-8")
    case("R5-09", "the stated --brief saving matches a measurement",
         f"{pct}% smaller" in claim, f"measured {pct}%")
    # Three numbers that used to be maintained by hand and drifted: each
    # agent's defect count in its SKILL.md against the entries in its own
    # delta log. A judge who counts them finds them equal.
    for agent, root in (("code-sentinel", CS), ("jira-scribe", JS),
                        ("release-archivist", RA)):
        deltas = (root / "references/eval-deltas.md").read_text(encoding="utf-8")
        n = len(re.findall(r"^\d+\. \*\*", deltas, re.M))
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"\*\*Deltas found and fixed\.\*\* (\d+) defects", skill)
        case(f"R5-02-{agent[:3]}",
             f"{agent} states as many defects as its delta log lists",
             bool(m) and int(m.group(1)) == n,
             f"SKILL says {m.group(1) if m else None}, log lists {n}")
    # N-1: the quoted URL was fixed and the unquoted one was not. A .env, YAML
    # or Dockerfile line lost its credential to the // of the scheme.
    d = D(["--- a/.env", "+++ b/.env", "@@ -1,2 +1,3 @@",
           "+DATABASE_URL=postgres://admin:prod-sk-9f8e12ab34@db.internal", ""])
    c, o = sh(PD, w("n1.diff", d))
    case("N-01", "a credential in an unquoted URL is demanded",
         any(m["rule"] == "L2-SEC-01" for m in json.loads(o)["must_flag"]),
         o[:200])

    # N-2: EXAMPLE_TOKEN matched incidental runs, so a genuine key containing
    # 0000000 was demoted from a demand to a judgement call.
    for tag, lit in (("zeros", "sk_live_00000004Qh8xZ2mPqRsTuVwX"),
                     ("digits", "AKIA1234567890ABCDEF")):
        d = D(["--- a/src/P.cs", "+++ b/src/P.cs", "@@ -1,2 +1,3 @@",
               '+var S = "' + lit + '";', ""])
        c, o = sh(PD, w(f"n2-{tag}.diff", d))
        case(f"N-02-{tag}", f"a real key containing {tag} is still demanded",
             bool(json.loads(o)["must_flag"]), o[:200])

    # N-3: the bare-header downgrade was gated on the file being a test, so the
    # same header in docs/ forced a finding.
    d = D(["--- a/docs/format.md", "+++ b/docs/format.md", "@@ -1,2 +1,3 @@",
           "+-----BEGIN PRIVATE KEY-----", ""])
    c, o = sh(PD, w("n3.diff", d))
    case("N-03", "a bare PEM header in docs does not force a finding",
         not json.loads(o)["must_flag"], o[:200])

    # N-6/N-7: shape alone is wrong in both directions. A leaked key arrives
    # announced; RS-232 is a noun phrase.
    sys.path.insert(0, str(RA / "scripts"))
    import importlib
    vo = importlib.import_module("validate_output")
    for tag, s, want in (
            ("long", "see PROJ-1234567 for detail", True),
            ("denied", "issue [US-4521] is closed", True),
            ("serial", "Now supports RS-232 serial devices", False),
            ("hw", "fixed RJ-45 detection and DDR-4 timing", False),
            ("level", "meets SLA-95 under US-2026 rules", False)):
        got = bool(vo.ticket_keys_in(s))
        case(f"N-06-{tag}", f"ticket detection is right on: {s[:38]}",
             got == want, f"flagged={got}, expected={want}")

    # N-8: a malformed double revert became a phantom FEATURE the notes were
    # then required to describe.
    c, o = sh(RAC, w("n8.log", chr(82) + 'evert "Revert ""' + chr(10)), "--json")
    it = json.loads(o)["items"][0]
    case("N-08", "a revert naming nothing does not invent a feature",
         it["class"] == "NOISE", it["class"])
    # O-1: numbers written into sentences had no generator, so one
    # classification change left an md5 transcript, a coverage line, two
    # documents and the page's payload table stale at once. `verify.sh`
    # runs `refresh_figures.py --check` directly; calling it from here as
    # well made the two scripts run each other to 85 processes.
    fig = (ROOT / "audit/refresh_figures.py").read_text(encoding="utf-8")
    case("O-01", "a generator owns every figure embedded in prose",
         "def rules(" in fig and "--check" in fig, "")

    # O-2: the recall claim - a review that MISSES a proven defect is a failed
    # review - lived only in this file, not in the scored artefact. The same
    # blind APPROVE must pass without --diff and fail with it.
    blind = CS / "evals/inputs/adversarial-missed-defect.md"
    c1, _ = sh(VF, blind, "--today", "2026-08-06")
    pd = w("o2-parsed.json", sh(PD, CS / "evals/inputs/02-permissions.diff")[1])
    c2, o = sh(VF, blind, "--diff", pd, "--today", "2026-08-06")
    case("O-02", "a blind APPROVE passes alone and fails against the diff",
         c1 == 0 and c2 == 1, f"without={c1} with={c2}")

    # O-3: the demo's readable trace was written once by hand and then
    # contradicted the JSON beside it for two rounds.
    tbl = (ROOT / "demo/release-archivist/2-classified.txt").read_text(encoding="utf-8")
    led = json.loads((ROOT / "demo/release-archivist/2-ledger.json")
                     .read_text(encoding="utf-8"))
    case("O-03", "the demo's readable trace agrees with its own ledger",
         f"published={led['coverage']['published']}" in tbl,
         f"ledger says {led['coverage']['published']}")
    # P-1: removing the 'only in a test file' condition from the bare-header
    # downgrade was right for docs/ and catastrophic for source: a real PEM key
    # puts its material on the NEXT line, so every genuine private key in
    # production code was demoted to advisory and a blind APPROVE passed.
    pem = D(["--- a/src/config.py", "+++ b/src/config.py", "@@ -1,2 +1,5 @@",
             chr(43) + 'KEY = """-----BEGIN RSA PRIVATE KEY-----',
             chr(43) + "MIIEowIBAAKCAQEAvJ8Kq2mN3pQrStUvWxYz0123456789abcdefghijklmnopqrs",
             chr(43) + '-----END RSA PRIVATE KEY-----"""', ""])
    c, o = sh(PD, w("p1.diff", pem))
    case("P-01", "a real multi-line PEM key in source is demanded",
         any(m["what"] == "private key" for m in json.loads(o)["must_flag"]),
         o[:200])

    # ...and the header alone, in documentation, still is not.
    doc = D(["--- a/docs/format.md", "+++ b/docs/format.md", "@@ -1,2 +1,3 @@",
             chr(43) + "-----BEGIN PRIVATE KEY-----", ""])
    c, o = sh(PD, w("p1b.diff", doc))
    case("P-01b", "a bare PEM header in docs is advisory only",
         not json.loads(o)["must_flag"], o[:200])

    # P-5: narrowing EXAMPLE_TOKEN to words made obvious filler a demand,
    # forcing a reviewer to invent a finding about a dead key.
    for tag, lit, want in (("zeros", "AKIA0000000000000000", False),
                           ("hexword", "sk_live_deadbeefdead", False),
                           ("real", "sk_live_00000004Qh8xZ2mPqRsTuVwX", True)):
        d2 = D(["--- a/src/P.cs", "+++ b/src/P.cs", "@@ -1,2 +1,3 @@",
                chr(43) + 'var k = "' + lit + '";', ""])
        c, o = sh(PD, w(f"p5-{tag}.diff", d2))
        got = bool(json.loads(o)["must_flag"])
        case(f"P-05-{tag}", f"{lit[:26]} is {'demanded' if want else 'advisory'}",
             got == want, f"demanded={got}")

    # P-2/P-3: the severity convention, all four shapes. Quoted material is
    # input; everywhere else a bracketed severity is the reviewer's claim; and
    # emphasising someone else's words makes them yours.
    for tag, extra, want in (
            ("plain-prose", "One aside: [BLOCKER] the auth check can be bypassed.", 1),
            ("emph-in-quote", "> **[BLOCKER]** the auth check can be bypassed.", 1),
            ("emph-prose", "Also **[MAJOR]** the retry loop never exits.", 1),
            ("plain-quote", "> This is a [BLOCKER] for the August release.", 0),
            ("quote-leading", "> [BLOCKER] must land before August.", 0),
            ("fenced", D(["```", "[BLOCKER] sample output", "```"]), 0)):
        c, o = sh(VF, w(f"p2-{tag}.md", review + D(["", extra, ""])),
                  "--today", "2026-08-06")
        case(f"P-02-{tag}", f"severity convention holds for {tag}", c == want,
             o.strip()[:160])

    # P-4: dropping fix/close/resolve from the tracker words re-opened the leak
    # for bare and ordinary-verb keys. Shape now works alongside announcement.
    for tag, s2, want in (
            ("ordinary-verb", "Fixed ACME-4521: export is faster", True),
            ("bare", "We shipped the ACME-4521 integration", True),
            ("bullet", "* ACME-4521 - improved export", True),
            ("serial", "Now supports RS-232 serial devices", False),
            ("hardware", "fixed RJ-45 detection and DDR-4 timing", False),
            ("gpu", "supports HDR-10 and RTX-4090", False)):
        got = bool(vo.ticket_keys_in(s2))
        case(f"P-04-{tag}", f"ticket detection is right on: {s2[:34]}",
             got == want, f"flagged={got}, expected={want}")

    # P-10: verify.sh ran the trace recorder without --check, so a stale
    # committed artefact was silently overwritten instead of turning it red.
    c, o = sh(ROOT / "demo/refresh.py", "--check")
    case("P-10", "the committed traces are what the code produces today",
         c == 0, o.strip()[-240:])

    # Q: no scratch file at the repo root. One was committed by `git add -A`,
    # carrying a connection string, in a submission whose L2-SEC-01 forbids
    # exactly that in source.
    stray = [f.name for f in ROOT.iterdir()
             if f.suffix in (".diff", ".log", ".tmp", ".bak")]
    case("Q-01", "no scratch files at the repository root", not stray,
         ", ".join(stray))

def main() -> int:
    for fn in (sentinel_shapes, sentinel_precision, sentinel_recall,
               sentinel_parsing, sentinel_context, secret_detection,
               archivist_zero_loss, archivist_leaks, archivist_classify,
               false_positives, ledger_honesty, scribe, cross_cutting,
               round_five):
        fn()

    verbose = "-v" in sys.argv
    # The count this suite reports is stated in two documents. It is
    # checked here rather than in `refresh_figures.py`, because only
    # this file knows the number without running anything.
    # The count this suite reports is stated in two documents. Checked here
    # rather than in `refresh_figures.py`, because only this file knows the
    # number without running anything - and the two scripts calling each
    # other once produced 85 concurrent processes. It is a plain gate, not
    # a case(), because a case would change the number it is checking.
    stated, mismatched = len(RESULTS), []
    for rel, pat in (("README.md", r"\*\*(\d+) checks\*\*"),
                     ("presentation/index.html", r"holds (\d+) checks")):
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        m = re.search(pat, text)
        if not m or int(m.group(1)) != stated:
            if m and "--sync" in sys.argv:
                path.write_text(re.sub(pat, lambda x: x.group(0).replace(
                    x.group(1), str(stated)), text), encoding="utf-8")
                print(f"  synced {rel} -> {stated} checks")
            else:
                mismatched.append(
                    f"{rel} says {m.group(1) if m else None}, "
                    f"this suite runs {stated}")

    failed = [r for r in RESULTS if not r[2]]
    print(f"auditor regressions — {len(RESULTS) - len(failed)}/{len(RESULTS)} held\n")
    for tag, desc, ok, detail in RESULTS:
        if ok and not verbose:
            continue
        print(f"  {'ok  ' if ok else 'FAIL'} [{tag}] {desc}"
              + (f"\n         {detail}" if detail and not ok else ""))
    for msg in mismatched:
        print(f"  FAIL [count] {msg}")
    if not failed and not mismatched:
        print("  every auditor finding is still fixed")
    else:
        print(f"\n{len(failed)} REGRESSION(S) - a defect an auditor found has returned")
    return 1 if (failed or mismatched) else 0


if __name__ == "__main__":
    sys.exit(main())
