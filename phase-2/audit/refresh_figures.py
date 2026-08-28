#!/usr/bin/env python3
"""Regenerate every figure this repository embeds in prose.

The Eval Log tables already had a generator (`refresh_eval_logs.py`). The
numbers written into sentences did not, and the R-02 fix proved why that
mattered: changing one classification moved `published` from 6 to 7, and the
md5 transcript in the README, the coverage line in a SKILL.md, a sentence in
SCENARIO.md and another in demo/README.md all went stale at once — in a
repository whose whole argument is that a claim should be checked rather than
asserted.

What is deliberately NOT here: the Tessl scores and the auditor count. Neither
can be derived from this tree, and both are labelled as external where they
appear. A generator that pretended to reproduce them would be the same defect
wearing a different hat.

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
WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


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


def figures() -> dict:
    LOG = "evals/inputs/03-sprint42.log"
    plain = out("release-archivist", "scripts/classify.py", LOG)
    # md5 as a POSIX shell would compute it: the transcript shows `md5sum`,
    # which exists where line endings are LF.
    md5 = hashlib.md5(plain.replace("\r\n", "\n").encode()).hexdigest()
    cov = json.loads(out("release-archivist", "scripts/classify.py", LOG,
                         "--json"))["coverage"]
    ra = payload("release-archivist", "scripts/classify.py", LOG, True)
    js = payload("jira-scribe", "scripts/parse_input.py",
                 "evals/inputs/02-braindump.txt", False)
    cs = payload("code-sentinel", "scripts/parse_diff.py",
                 "evals/inputs/02-permissions.diff", False)
    return {"md5": md5, "cov": cov, "ra": ra, "js": js, "cs": cs}


def rules(f: dict) -> list:
    """(file, pattern, replacement, regex flags) — one per embedded figure."""
    c = f["cov"]
    p = c["published"]
    return [
        ("README.md", r"^[0-9a-f]{32}$", f["md5"], re.M),
        ("release-archivist/SKILL.md", r"^[0-9a-f]{32}$", f["md5"], re.M),
        ("release-archivist/SKILL.md",
         r"in=\d+ published=\d+ internal=\d+ suppressed=\d+ accounted=\d+",
         f"in={c['items_in']} published={p} internal={c['internal']} "
         f"suppressed={c['suppressed']} accounted={c['items_accounted']}", 0),
        ("release-archivist/SKILL.md", r"about \*\*\d+% smaller\*\*",
         f"about **{f['ra'][2]}% smaller**", 0),
        ("jira-scribe/SKILL.md", r"About \*\*\d+% smaller\*\*",
         f"About **{f['js'][2]}% smaller**", 0),
        ("code-sentinel/SKILL.md", r"\*\*\d+% smaller\*\*",
         f"**{f['cs'][2]}% smaller**", 0),
        ("scenario/SCENARIO.md", r"published notes carry \d+ items",
         f"published notes carry {p} items", 0),
        ("demo/README.md", r"become \w+ customer-facing",
         f"become {WORDS.get(p, p)} customer-facing", 0),
        # The page's payload table, one row per droid:
        #   <td class='n'>6,786</td><td class='n'>2,275</td>
        #   <td class='n'><b>&minus;66%</b></td>
        *[("presentation/index.html",
          r"(<b>" + droid + r"</b>.{0,200}?<td class='n'>)[\d,]+"
          r"(</td><td class='n'>)[\d,]+"
          r"(</td><td class='n'><b>&minus;)\d+(%)",
          (lambda m, k=key: m.group(1) + f"{f[k][0]:,}" + m.group(2)
                           + f"{f[k][1]:,}" + m.group(3) + str(f[k][2])
                           + m.group(4)), 0)
         for droid, key in (("BB-8", "ra"), ("R2-D2", "js"), ("C-3PO", "cs"))],
    ]


def main() -> int:
    check = "--check" in sys.argv
    f = figures()
    drift, missing = [], []

    for rel, pat, want, flags in rules(f):
        path = ROOT / rel
        t = path.read_text(encoding="utf-8")
        repl = want if callable(want) else want.replace("\\", "\\\\")
        new, n = re.subn(pat, repl, t, flags=flags)
        if n == 0:
            missing.append(f"{rel}: nothing matched {pat[:60]!r}")
            continue
        if new != t:
            label = "<computed>" if callable(want) else want[:52]
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
        print("every embedded figure matches the code")
    return 1 if (drift or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
