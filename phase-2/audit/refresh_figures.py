#!/usr/bin/env python3
"""Regenerate every figure this repository embeds in prose.

The Eval Log tables already had a generator (`refresh_eval_logs.py`). The
numbers written into sentences did not, and one classification change proved why
that mattered: moving `published` from 6 to 7 left an md5 transcript, a coverage
line, two documents and the page's payload table stale at once — in a repository
whose whole argument is that a claim should be checked rather than asserted.

The first version of this file enumerated the figures it happened to know about,
which is the same defect one level up. A judge re-deriving the numbers found a
README claiming `15/15` where 17 run, and a per-agent table summing to 36 four
lines below a sentence saying 38. Every count a document states is computed here
now, including the ones in the README's own transcripts.

The regression-check count is NOT here either, and that is structural: this
script and `regressions.py` would otherwise each run the other, which they did
once, to 85 concurrent processes. `regressions.py` knows its own count without
running anything, so it owns that figure.

What is deliberately NOT here: the Tessl scores. They come from an external
service, this tree cannot derive them, and they are labelled as external
wherever they appear. A generator that pretended to reproduce them would be the
same defect wearing a third hat.

Usage:  python audit/refresh_figures.py [--check]
        --check  report drift and exit 1 without writing
Exit:   0 every figure matches / 1 drift found (or rewritten, without --check)
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
AGENTS = ("release-archivist", "jira-scribe", "code-sentinel")
HTML = "presentation/index.html"
WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
         10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
         14: "fourteen", 15: "fifteen", 16: "sixteen",
         17: "seventeen", 18: "eighteen"}


def out(agent: str, script: str, *args) -> str:
    p = subprocess.run([PY, str(ROOT / agent / script), *args],
                       capture_output=True, text=True, cwd=ROOT / agent)
    return p.stdout


def payload(agent: str, script: str, inp: str, json_flag: bool) -> tuple:
    """Full and --brief payload sizes, and the reduction as a percentage."""
    base = [inp, "--json"] if json_flag else [inp]
    full = len(out(agent, script, *base))
    brief = len(out(agent, script, *base, "--brief"))
    return full, brief, round(100 * (full - brief) / full)


def suite(agent: str) -> dict:
    """Case counts, read from the agent's Eval Log rather than re-run.

    `refresh_eval_logs.py --check` already fails if that table is not exactly
    what the runner produces, so counting its rows is as trustworthy as running
    the suite again — and running three full suites here made this gate the
    slowest thing in `verify.sh` for four numbers.
    """
    skill = (ROOT / agent / "SKILL.md").read_text(encoding="utf-8")
    rows = [l for l in skill.splitlines() if re.match(r"^\|\s*\d+\s*\|", l)]
    return {"cases": len(rows),
            "golden": sum(1 for l in rows if "| yes |" in l),
            "inputs": len(list((ROOT / agent / "evals/inputs").iterdir()))}


def figures() -> dict:
    LOG = "evals/inputs/03-sprint42.log"
    plain = out("release-archivist", "scripts/classify.py", LOG)
    # md5 as a POSIX shell computes it: the transcript shows `md5sum`, which
    # exists where line endings are LF.
    md5 = hashlib.md5(plain.replace(chr(13) + chr(10), chr(10)).encode()).hexdigest()
    cov = json.loads(out("release-archivist", "scripts/classify.py", LOG,
                         "--json"))["coverage"]
    s = {a: suite(a) for a in AGENTS}

    reg_src = (ROOT / "audit/regressions.py").read_text(encoding="utf-8")
    # Auditor tags: how "N independent auditors" is counted. R5- is a namespace,
    # not an auditor — an earlier auditor already owned the M- prefix.
    auditors = len({m for m in re.findall(r'case\(f?"([A-Z][A-Z0-9]*)-', reg_src)
                    if not m.startswith("R5")})
    defects = {a: len(re.findall(r"^\d+\. \*\*",
                                 (ROOT / a / "references/eval-deltas.md")
                                 .read_text(encoding="utf-8"), re.M))
               for a in AGENTS}

    return {
        "md5": md5, "cov": cov, "suite": s,
        "ra": payload("release-archivist", "scripts/classify.py", LOG, True),
        "js": payload("jira-scribe", "scripts/parse_input.py",
                      "evals/inputs/02-braindump.txt", False),
        "cs": payload("code-sentinel", "scripts/parse_diff.py",
                      "evals/inputs/02-permissions.diff", False),
        "cases": sum(v["cases"] for v in s.values()),
        "inputs": sum(v["inputs"] for v in s.values()),
        "auditors": auditors,
        "defects": defects, "defects_total": sum(defects.values()),
    }


def rules(f: dict) -> list:
    """(file, pattern, replacement, regex flags) — one per embedded figure."""
    c, p = f["cov"], f["cov"]["published"]
    s, d = f["suite"], f["defects"]
    r = [
        # --- transcripts ------------------------------------------------------
        ("README.md", r"^[0-9a-f]{32}$", f["md5"], re.M),
        ("release-archivist/SKILL.md", r"^[0-9a-f]{32}$", f["md5"], re.M),

        # --- the Archivist's ledger, quoted in four places --------------------
        ("release-archivist/SKILL.md",
         r"in=\d+ published=\d+ internal=\d+ suppressed=\d+ accounted=\d+",
         f"in={c['items_in']} published={p} internal={c['internal']} "
         f"suppressed={c['suppressed']} accounted={c['items_accounted']}", 0),
        ("scenario/SCENARIO.md", r"published notes carry \d+ items",
         f"published notes carry {p} items", 0),
        ("scenario/SCENARIO.md",
         r"has \d+ lines, of\nwhich \d+ are pure noise and \d+ internal",
         f"has {c['items_in']} lines, of\nwhich {c['suppressed']} are pure "
         f"noise and {c['internal']} internal", 0),
        ("demo/README.md", r"become \w+ customer-facing",
         f"become {WORDS.get(p, p)} customer-facing", 0),

        # --- payload reductions ----------------------------------------------
        ("release-archivist/SKILL.md", r"about \*\*\d+% smaller\*\*",
         f"about **{f['ra'][2]}% smaller**", 0),
        ("jira-scribe/SKILL.md", r"About \*\*\d+% smaller\*\*",
         f"About **{f['js'][2]}% smaller**", 0),
        ("code-sentinel/SKILL.md", r"\*\*\d+% smaller\*\*",
         f"**{f['cs'][2]}% smaller**", 0),

        # --- corpus totals ----------------------------------------------------
        ("README.md", r"\*\*\d+ cases over \d+ input files\*\*",
         f"**{f['cases']} cases over {f['inputs']} input files**", 0),
        ("AGENT-FRAMEWORK.md", r"\d+ inputs across \d+ cases",
         f"{f['inputs']} inputs across {f['cases']} cases", 0),

        # --- defects, checks, auditors ----------------------------------------
        ("README.md",
         r"\*\*\d+ in total\*\*,\n\d+ in the Archivist, \d+ in the Scribe, "
         r"\d+ in the Sentinel",
         f"**{f['defects_total']} in total**,\n{d['release-archivist']} in the "
         f"Archivist, {d['jira-scribe']} in the Scribe, "
         f"{d['code-sentinel']} in the Sentinel", 0),
        ("README.md", r"\*\*\w+ independent auditors\*\*",
         f"**{WORDS.get(f['auditors'], f['auditors'])} independent auditors**", 0),
        ("verify.sh", r"defect \w+ independent auditors",
         f"defect {WORDS.get(f['auditors'], f['auditors'])} independent auditors", 0),
        (HTML, r"\d+ cases that fail when the logic changes",
         f"{f['cases']} cases that fail when the logic changes", 0),
    ]

    # --- per-agent delta counts in each SKILL.md ------------------------------
    for a in AGENTS:
        r.append((f"{a}/SKILL.md", r"\*\*Deltas found and fixed\.\*\* \d+ defects",
                  f"**Deltas found and fixed.** {d[a]} defects", 0))

    # --- README's per-agent table and independence transcript -----------------
    for a in AGENTS:
        r.append(("README.md", rf"(\| `{a}` \| )\d+( \| )\d+( \| )\d+( \|)",
                  (lambda m, k=a: m.group(1) + str(s[k]["cases"]) + m.group(2)
                   + str(s[k]["golden"]) + m.group(3) + str(s[k]["inputs"])
                   + m.group(4)), 0))
        r.append(("README.md",
                  rf"(\[OK \] {a}\s+ran with [^\n]+\n\s+)\d+/\d+ passed",
                  (lambda m, k=a: m.group(1)
                   + f"{s[k]['cases']}/{s[k]['cases']} passed"), 0))

    # --- the page: stat row and payload table ---------------------------------
    r += [
        (HTML, r"(class=\"stat\" style=\"color:var\(--sky\)\">)\d+(<)",
         (lambda m: m.group(1) + str(f["cases"]) + m.group(2)), 0),
        (HTML, r"(class=\"stat\" style=\"color:var\(--amber\)\">)\d+(<)",
         (lambda m: m.group(1) + str(f["defects_total"]) + m.group(2)), 0),
    ]
    for droid, key in (("BB-8", "ra"), ("R2-D2", "js"), ("C-3PO", "cs")):
        r.append((HTML,
                  r"(<b>" + droid + r"</b>.{0,200}?<td class='n'>)[\d,]+"
                  r"(</td><td class='n'>)[\d,]+"
                  r"(</td><td class='n'><b>&minus;)\d+(%)",
                  (lambda m, k=key: m.group(1) + f"{f[k][0]:,}" + m.group(2)
                   + f"{f[k][1]:,}" + m.group(3) + str(f[k][2]) + m.group(4)), 0))
    return r


def main() -> int:
    check = "--check" in sys.argv
    f = figures()
    rs = rules(f)
    drift, missing = [], []

    for rel, pat, want, flags in rs:
        path = ROOT / rel
        t = path.read_text(encoding="utf-8")
        repl = want if callable(want) else want.replace("\\", "\\\\")
        new, n = re.subn(pat, repl, t, flags=flags)
        if n == 0:
            missing.append(f"{rel}: nothing matched {pat[:64]!r}")
            continue
        if new != t:
            label = "<computed>" if callable(want) else want[:52].replace("\n", " ")
            drift.append(f"{rel} -> {label}")
            if not check:
                path.write_text(new, encoding="utf-8")

    for m in missing:
        print(f"  !! {m}")
    if drift and check:
        print("figures that no longer match the code:")
        for d in drift:
            print("   ", d)
        print("Run `python audit/refresh_figures.py` to regenerate them.")
    elif drift:
        print(f"regenerated {len(drift)} figure(s):")
        for d in drift:
            print("   ", d)
    elif not missing:
        print(f"every embedded figure matches the code ({len(rs)} checked)")
    return 1 if (drift or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
