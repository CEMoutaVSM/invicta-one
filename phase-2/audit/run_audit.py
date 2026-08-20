#!/usr/bin/env python3
"""Mechanical compliance audit against audit/REQUIREMENTS.md.

Covers the [AUTO] assertions only. The [JUDGE] ones need a reasoning agent --
see HANDOFF.md section 5 for the subagent invocation.

A NOTE ON CHECKS THAT CANNOT FAIL
---------------------------------
An earlier version of this file reported 35/35 while the submission was missing
a scored requirement. A4 counted markdown table ROWS instead of eval inputs, so
an Eval Log could claim three inputs while the agent had two and still pass. A3
only required the heading to appear past 60% of the file. A6 was a regex for the
word "md5". A green audit that cannot see its own gaps is worse than no audit,
because someone trusts it. Each check below is written to be failable, and the
ones that assert behaviour now RUN the behaviour.

Usage: python audit/run_audit.py [-v]
Exit:  0 all pass, 1 one or more failures
"""
import json, pathlib, re, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENTS = ["release-archivist", "jira-scribe", "code-sentinel"]
TODAY = "2026-08-06"
R = []


def check(rid, desc, ok, detail=""):
    R.append((rid, desc, bool(ok), detail))


def sh(*cmd, cwd=None):
    p = subprocess.run([sys.executable, *[str(c) for c in cmd]],
                       capture_output=True, text=True, cwd=cwd or ROOT)
    return p.returncode, p.stdout + p.stderr


def skill(a):
    return (ROOT / a / "SKILL.md").read_text(encoding="utf-8")


# --- A. submission -----------------------------------------------------------
for a in AGENTS:
    check("A1", f"{a}/SKILL.md exists", (ROOT / a / "SKILL.md").is_file())

for a in AGENTS:
    t = skill(a)
    check("A2", f"{a} has an Eval Log", "## Eval Log" in t)
    idx = t.find("## Eval Log")

    # A3: the Eval Log must be the LAST top-level section, not merely late in
    # the file. "Past 60%" would pass with three more sections after it.
    later = [m.group(1) for m in re.finditer(r"^##\s+(.+?)\s*$", t, re.M)
             if m.start() > idx] if idx > 0 else ["(no Eval Log)"]
    check("A3", f"{a} Eval Log is the last section", idx > 0 and not later,
          f"sections after it: {later}" if later else "nothing follows it")

    # A4: count the eval INPUTS that exist on disk, not the rows of a table the
    # author wrote. This is the check that caught jira-scribe claiming three.
    inputs = sorted(p.name for p in (ROOT / a / "evals" / "inputs").glob("*")
                    if p.is_file())
    check("A4", f"{a} has >=3 separate eval inputs on disk", len(inputs) >= 3,
          f"{len(inputs)}: {', '.join(inputs)}")

    # And the Eval Log must not claim more cases than the suite actually runs.
    tail = t[idx:] if idx > 0 else ""
    rows = [l for l in tail.splitlines()
            if l.startswith("| ") and re.match(r"\|\s*\d+\s*\|", l)]
    code, out = sh(ROOT / a / "scripts" / "run_evals.py", cwd=ROOT / a)
    m = re.search(r"(\d+)/(\d+) passed", out)
    ran = int(m.group(2)) if m else 0
    check("A4b", f"{a} Eval Log rows do not exceed cases the suite runs",
          rows and ran and len(rows) <= ran,
          f"{len(rows)} rows documented, {ran} cases run")

    check("A6", f"{a} Eval Log claims determinism",
          bool(re.search(r"determinis|md5|identical|3 (times|runs)|x3", tail, re.I)))

# --- B/C/D. trial-specific ---------------------------------------------------
arch = skill("release-archivist")
check("B1", "Archivist accepts commits AND Jira",
      "git log" in arch.lower() and "jira" in arch.lower())
check("B2", "Archivist filters named noise examples",
      all(k in arch.lower() for k in ("typo", "merge")))
check("B5", "Archivist guarantees zero loss via coverage",
      "items_in" in arch and "accounted" in arch)

scr = skill("jira-scribe")
check("C1", "Scribe accepts brain dump or transcript",
      "transcript" in scr.lower() and "brain dump" in scr.lower())
check("C1b", "Scribe has a fixture for BOTH input shapes",
      (ROOT / "jira-scribe/evals/inputs/01-refinement.txt").exists()
      and (ROOT / "jira-scribe/evals/inputs/02-braindump.txt").exists())
check("C2", "Scribe generates Context", "### Context" in scr)
check("C3", "Scribe uses Given-When-Then Gherkin",
      "Given" in scr and "When" in scr and "Then" in scr)
check("C4", "Scribe generates Technical Hints", "Technical Hints" in scr)

sen = skill("code-sentinel")
check("D1", "Sentinel accepts .diff or PR description",
      ".diff" in sen and "PR description" in sen)
check("D2", "Sentinel maps to team-specific standards",
      "L3-project.md" in sen and "L2-org-standards.md" in sen)
check("D3", "Sentinel uses negative prompting (a Constraints/never section)",
      "must **never**" in sen or "## 8. Constraints" in sen)
check("D4", "Sentinel excludes style/linter concerns",
      "linter" in sen.lower())
check("D6", "Sentinel flags missing test coverage",
      "L2-TEST-01" in sen or "test coverage" in sen.lower())

# --- E3 / F. determinism and self-imposed claims -----------------------------
det_ok = True
for a in AGENTS:
    c, _ = sh(ROOT / a / "scripts" / "run_evals.py", cwd=ROOT / a)
    det_ok &= (c == 0)
check("E3", "all agents' evals pass, golden-compared, md5-stable x3", det_ok)

# E3b: the golden sets are actually READ. Without this, every eval above is
# an exit-code check on a pure function and the regression gate is fictional.
wired = []
for a in AGENTS:
    src = (ROOT / a / "scripts" / "run_evals.py").read_text(encoding="utf-8")
    if "golden" not in src.lower() or "GOLDEN" not in src:
        wired.append(a)
check("E3b", "every agent's runner compares against evals/golden/", not wired,
      "not wired: " + ", ".join(wired) if wired else "")

# E3c: a golden gate that cannot fail is not a gate. Mutate a copy and require
# the suite to notice.
with tempfile.TemporaryDirectory() as tmp:
    dst = pathlib.Path(tmp) / "release-archivist"
    shutil.copytree(ROOT / "release-archivist", dst)
    g = dst / "evals" / "golden" / "03-sprint42.json"
    doc = json.loads(g.read_text(encoding="utf-8"))
    doc["decisions"]["1"]["class"] = "NOISE"        # was FEATURE
    g.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    c, _ = sh(dst / "scripts" / "run_evals.py", cwd=dst)
    check("E3c", "a corrupted golden makes the suite FAIL (the gate bites)",
          c != 0, f"exit {c} on a mutated golden")

# F1: independence, physically
indep = True
for a in AGENTS:
    with tempfile.TemporaryDirectory() as tmp:
        dst = pathlib.Path(tmp) / a
        shutil.copytree(ROOT / a, dst)
        c, _ = sh(dst / "scripts" / "run_evals.py", cwd=dst)
        indep &= (c == 0)
check("F1", "each agent passes alone with siblings deleted", indep)

# F2: no cross-agent references in code
leaks = []
for a in AGENTS:
    for py in (ROOT / a).rglob("*.py"):
        txt = py.read_text(encoding="utf-8")
        for other in AGENTS:
            if other != a and other in txt:
                leaks.append(f"{py.relative_to(ROOT)} -> {other}")
check("F2", "no agent references a sibling in code", not leaks, "; ".join(leaks))

# F3/F4: citation rule + suppression, via the adversarial fixture
c, out = sh(ROOT / "code-sentinel/scripts/validate_findings.py",
            ROOT / "code-sentinel/evals/inputs/adversarial-uncited-review.md",
            "--today", TODAY)
check("F3", "uncited finding is rejected", c == 1 and "NO RULE CITED" in out)
check("F4", "finding on a suppressed path is rejected", "SUPPRESSED" in out)

# F3b: the citation rule must not be bypassable by declaring a refusal.
c, out = sh(ROOT / "code-sentinel/scripts/validate_findings.py",
            ROOT / "code-sentinel/evals/inputs/adversarial-refusal-bypass.md",
            "--today", TODAY)
check("F3b", "refusal marker does not bypass validation", c == 1,
      f"exit {c}")

# F3c: a finding written at the wrong heading depth must not escape checking.
with tempfile.TemporaryDirectory() as tmp:
    smug = pathlib.Path(tmp) / "smuggled.md"
    smug.write_text(
        "# Review\n\n**Verdict:** REQUEST-CHANGES\n\n"
        "#### [MAJOR] uncited speculation\n"
        "- **Where:** `src/x.cs:1`\n\n"
        "## Coverage\nFiles changed: 1 · Reviewed: 1 · Skipped: 0\n",
        encoding="utf-8")
    c, out = sh(ROOT / "code-sentinel/scripts/validate_findings.py", smug,
                "--today", TODAY)
    check("F3c", "a #### finding is still validated", c == 1 and "NO RULE" in out)

# F5: expired deviation stops suppressing
c, out = sh(ROOT / "code-sentinel/scripts/load_rules.py",
            "--path", "src/onboarding/Saga.cs", "--today", TODAY)
check("F5", "expired deviation no longer suppresses",
      "no suppressions" in out and "expired" in out)

# F5b: a deviation the loader cannot read must not silence a rule either.
with tempfile.TemporaryDirectory() as tmp:
    ctx = pathlib.Path(tmp)
    for f in ("L2-org-standards.md", "L3-project.md"):
        shutil.copy(ROOT / "code-sentinel" / "context" / f, ctx / f)
    (ctx / "L3-known-deviations.md").write_text(
        "### DEV-900 — unreadable expiry\n"
        "Status: accepted | Owner: @x\n"
        "Agent behaviour: do not flag L2-SEC-04 for paths under src/\n"
        "Expires: TBD\n", encoding="utf-8")
    c, out = sh(ROOT / "code-sentinel/scripts/load_rules.py",
                "--context", ctx, "--path", "src/x.cs", "--today", TODAY)
    check("F5b", "a deviation with an unreadable expiry does not suppress",
          "no suppressions" in out and c == 3, f"exit {c}")

# F5c: context present but unparseable must refuse, not load zero rules.
with tempfile.TemporaryDirectory() as tmp:
    ctx = pathlib.Path(tmp)
    (ctx / "L2-org-standards.md").write_text("# L2\n\nnothing\n", encoding="utf-8")
    c, out = sh(ROOT / "code-sentinel/scripts/load_rules.py",
                "--context", ctx, "--today", TODAY)
    check("F5c", "an unparseable context is a CONFIG error, not an empty rule set",
          c == 3 and "CONFIG" in out, f"exit {c}")

# F6: refusal treated as success
c, out = sh(ROOT / "jira-scribe/scripts/parse_input.py",
            ROOT / "jira-scribe/evals/inputs/01-refinement.txt")
try:
    refuses = json.loads(out)["status"] == "insufficient_input"
except Exception:
    refuses = False
check("F6", "refusal path exercised and exits 0", refuses and c == 0)

# B5b: the zero-loss guarantee must be falsifiable. Remove a published entry
# from the notes, leave the ledger alone, and require a failure.
with tempfile.TemporaryDirectory() as tmp:
    notes = (ROOT / "release-archivist/evals/inputs/valid-notes.md").read_text(
        encoding="utf-8")
    cut = "\n".join(l for l in notes.splitlines()
                    if "Currency rounding" not in l)
    p = pathlib.Path(tmp) / "cut.md"
    p.write_text(cut, encoding="utf-8")
    c, out = sh(ROOT / "release-archivist/scripts/validate_output.py", p)
    check("B5b", "deleting a published entry FAILS validation",
          c == 1 and "MISSING FEATURES" in out, f"exit {c}")

# D6b: recall. A review that misses a defect the parser proved must FAIL.
with tempfile.TemporaryDirectory() as tmp:
    tmpd = pathlib.Path(tmp)
    c, out = sh(ROOT / "code-sentinel/scripts/parse_diff.py",
                ROOT / "code-sentinel/evals/inputs/02-permissions.diff")
    (tmpd / "d.json").write_text(out, encoding="utf-8")
    blind = tmpd / "blind.md"
    blind.write_text("# Review\n\n**Verdict:** APPROVE\n\nNo findings.\n\n"
                     "## Coverage\nFiles changed: 3 · Reviewed: 2 · Skipped: 1\n",
                     encoding="utf-8")
    c, out = sh(ROOT / "code-sentinel/scripts/validate_findings.py", blind,
                "--diff", tmpd / "d.json", "--today", TODAY)
    check("D6b", "a review that misses an untested branch FAILS",
          c == 1 and "L2-TEST-01" in out, f"exit {c}")

# F8: documented paths exist
missing = []
PATH_RE = re.compile(r"`((?:scripts|context|references|evals|scenario|audit)"
                     r"/[\w./-]+)`")
# Also catch paths written relative to an agent, e.g. `<agent>/references/x.md`
AGENT_PATH_RE = re.compile(r"`((?:release-archivist|jira-scribe|code-sentinel)"
                           r"/[\w./-]+)`")
for md in ROOT.rglob("*.md"):
    if ".git" in md.parts:
        continue
    text = md.read_text(encoding="utf-8")
    for rx in (PATH_RE, AGENT_PATH_RE):
        for m in rx.finditer(text):
            t = m.group(1)
            # A bare `context/L3-project.md` in a framework-level document means
            # "inside an agent", so resolve against each agent too before
            # calling it missing.
            if ((md.parent / t).exists() or (ROOT / t).exists()
                    or any((ROOT / a / t).exists() for a in AGENTS)):
                continue
            missing.append(f"{md.relative_to(ROOT)} -> {t}")

# The anatomy diagram describes what every agent has. Checking it stops the
# tree drifting into fiction: it listed two files that existed in no agent, and
# the old checker structurally could not see them.
fw = (ROOT / "AGENT-FRAMEWORK.md").read_text(encoding="utf-8")
anat = re.search(r"## 2\. Anatomy.*?```(.*?)```", fw, re.S)
for name in sorted(set(re.findall(r"\b[\w][\w.-]*\.(?:md|py)\b",
                                  anat.group(1) if anat else ""))):
    for a in AGENTS:
        if not any((ROOT / a).rglob(name)):
            missing.append(f"AGENT-FRAMEWORK.md anatomy -> {a}/**/{name}")
check("F8", "every documented path exists", not missing,
      "; ".join(sorted(set(missing))[:6]))

# --- report ------------------------------------------------------------------
verbose = "-v" in sys.argv
fails = [r for r in R if not r[2]]
print(f"Compliance audit — {len(R) - len(fails)}/{len(R)} automated checks passed\n")
for rid, desc, ok, detail in R:
    if ok and not verbose:
        continue
    print(f"  {'ok  ' if ok else 'FAIL'} [{rid}] {desc}"
          + (f"\n         {detail}" if detail and (verbose or not ok) else ""))
if not fails:
    print("  all automated checks passed")
print(f"\nStill requires judgment (see REQUIREMENTS.md): "
      f"A5 A7 B3 B4 B6 C5 C6 C7 D5 D7 E1 E2 E4 F7")
print("Run the four-auditor sweep from HANDOFF.md section 5 for those.")
sys.exit(1 if fails else 0)
