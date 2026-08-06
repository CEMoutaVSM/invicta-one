#!/usr/bin/env python3
"""Mechanical compliance audit against audit/REQUIREMENTS.md.

Covers the [AUTO] assertions only. The [JUDGE] ones need a reasoning agent --
see HANDOFF.md section 5 for the subagent invocation.

Usage: python audit/run_audit.py [-v]
Exit:  0 all pass, 1 one or more failures
"""
import hashlib, json, pathlib, re, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENTS = ["release-archivist", "jira-scribe", "code-sentinel"]
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
    check("A3", f"{a} Eval Log is at the bottom",
          idx > 0 and idx > len(t) * 0.6, f"at {100*idx//max(len(t),1)}% of file")
    tail = t[idx:] if idx > 0 else ""
    rows = [l for l in tail.splitlines()
            if l.startswith("| ") and re.match(r"\|\s*\d+\s*\|", l)]
    check("A4", f"{a} Eval Log shows >=3 inputs", len(rows) >= 3,
          f"{len(rows)} rows")
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
check("E3", "all agents' evals pass with md5-stable output x3", det_ok)

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
            "--today", "2026-08-06")
check("F3", "uncited finding is rejected", c == 1 and "NO RULE CITED" in out)
check("F4", "finding on a suppressed path is rejected", "SUPPRESSED" in out)

# F5: expired deviation stops suppressing
c, out = sh(ROOT / "code-sentinel/scripts/load_rules.py",
            "--path", "src/onboarding/Saga.cs", "--today", "2026-08-06")
check("F5", "expired deviation no longer suppresses",
      "no suppressions" in out and "expired" in out)

# F6: refusal treated as success
c, out = sh(ROOT / "jira-scribe/scripts/parse_input.py",
            ROOT / "jira-scribe/evals/inputs/01-refinement.txt")
try:
    refuses = json.loads(out)["status"] == "insufficient_input"
except Exception:
    refuses = False
check("F6", "refusal path exercised and exits 0", refuses and c == 0)

# F8: documented paths exist
missing = []
for md in ROOT.rglob("*.md"):
    for m in re.finditer(r"`((?:scripts|context|references|evals|scenario|audit)"
                         r"/[\w./-]+)`", md.read_text(encoding="utf-8")):
        t = m.group(1)
        if not ((md.parent / t).exists() or (ROOT / t).exists()):
            missing.append(f"{md.relative_to(ROOT)} -> {t}")
check("F8", "every documented path exists", not missing, "; ".join(missing[:5]))

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
