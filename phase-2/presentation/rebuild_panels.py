#!/usr/bin/env python3
"""Regenerate the agent panels inside presentation/index.html from the repo.

The page embeds each agent's SKILL.md, output contract, context layers, scripts
and eval output so a reader can inspect the actual deliverable without leaving
it. That content goes stale the moment an agent changes — after the SKILL.md
files were reorganised, the page was still showing the previous version.

This regenerates only the modal region, in place, reading everything from the
working tree. It lives in the repository on purpose: the original page builder
was kept in a scratch directory and was lost when the machine reverted
user-installed software, taking the ability to rebuild the page with it.

Usage:  python presentation/rebuild_panels.py
Exit:   0 rewritten / 1 the region could not be located
"""
import html
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PAGE = HERE / "index.html"

DROIDS = [
    ("bb8", "BB-8", "The Release Archivist", "release-archivist", "var(--amber)",
     "classify.py", "validate_output.py"),
    ("r2d2", "R2-D2", "The Scribe", "jira-scribe", "var(--sky)",
     "parse_input.py", "validate_output.py"),
    ("c3po", "C-3PO", "The Code Sentinel", "code-sentinel", "var(--gold)",
     "parse_diff.py", "validate_findings.py"),
]

START = '<div class="scroll">'
END = "</div>\n  </div>\n</div>\n\n<script>"


def esc(t):
    return html.escape(t, quote=False)


def md_to_html(md: str) -> str:
    """Enough markdown for the documents this repository actually contains."""
    fences = []

    def stash(m):
        fences.append(m.group(2))
        return f"\x00F{len(fences) - 1}\x00"

    md = re.sub(r"```(\w*)\n(.*?)```", stash, md, flags=re.S)

    def inline(x):
        x = esc(x)
        x = re.sub(r"`([^`]+)`", r"<code>\1</code>", x)
        x = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", x)
        x = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", x)
        return x

    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if m := re.match(r"^\x00F(\d+)\x00\s*$", ln):
            out.append("<pre><code>" + esc(fences[int(m.group(1))].rstrip())
                       + "</code></pre>")
            i += 1
            continue
        if m := re.match(r"^(#{1,6})\s+(.*)$", ln):
            out.append(f"<h{min(len(m.group(1)) + 2, 6)}>{inline(m.group(2))}"
                       f"</h{min(len(m.group(1)) + 2, 6)}>")
            i += 1
            continue
        if re.match(r"^\s*([-*_])\1{2,}\s*$", ln):
            out.append("<hr>")
            i += 1
            continue
        if ln.strip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            head = cells(ln)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append('<div class="tw"><table><thead><tr>'
                       + "".join(f"<th>{inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r)
                                 + "</tr>" for r in rows) + "</tbody></table></div>")
            continue
        if re.match(r"^\s*[-*+]\s+", ln) or re.match(r"^\s*\d+[.)]\s+", ln):
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", ln))
            items = []
            while i < len(lines) and (re.match(r"^\s*[-*+]\s+", lines[i])
                                      or re.match(r"^\s*\d+[.)]\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i]))
                i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                    items[-1] += " " + lines[i].strip()
                    i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items)
                       + f"</{tag}>")
            continue
        if ln.strip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{inline(' '.join(buf))}</blockquote>")
            continue
        if not ln.strip():
            i += 1
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and "\x00F" not in lines[i] \
                and not re.match(r"^(#{1,6}\s|\s*\||\s*[-*+]\s|\s*\d+[.)]\s|>)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    body = "\n".join(out)
    return re.sub(r"\x00F(\d+)\x00",
                  lambda m: "<pre><code>" + esc(fences[int(m.group(1))].rstrip())
                  + "</code></pre>", body)


def read(rel: str) -> str:
    f = REPO / rel
    return f.read_text(encoding="utf-8") if f.exists() else ""


def run_evals(folder: str) -> str:
    p = subprocess.run([sys.executable, str(REPO / folder / "scripts/run_evals.py")],
                       capture_output=True, text=True, cwd=REPO / folder)
    return (p.stdout + p.stderr).rstrip()


def script_block(folder: str, name: str) -> str:
    src = read(f"{folder}/scripts/{name}")
    doc = re.search(r'"""(.*?)"""', src, re.S)
    summary = " ".join(doc.group(1).strip().split("\n")[0].split()) if doc else ""
    return (f'<details class="filed"><summary><span class="fn">{name}</span>'
            f'<span class="fd">{esc(summary)}</span>'
            f'<span class="fl">{len(src.splitlines())} lines</span></summary>'
            f"<pre><code>{esc(src)}</code></pre></details>")


def pipeline_svg(slug, colour, parser, validator, job) -> str:
    return f'''<svg viewBox="0 0 940 210" class="flow" role="img" aria-label="Pipeline">
  <defs><marker id="ar2-{slug}" markerWidth="9" markerHeight="9" refX="8" refY="3"
    orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.45)"/></marker></defs>
  <g font-family="var(--mono)" font-size="12">
    <rect x="4" y="64" width="150" height="70" rx="5" fill="rgba(255,255,255,.05)" stroke="rgba(255,255,255,.18)"/>
    <text x="79" y="92" text-anchor="middle" fill="rgba(255,255,255,.9)">messy input</text>
    <text x="79" y="112" text-anchor="middle" fill="rgba(255,255,255,.45)" font-size="11">human, unedited</text>
    <rect x="196" y="64" width="176" height="70" rx="5" fill="rgba(255,255,255,.05)" stroke="{colour}"/>
    <text x="284" y="88" text-anchor="middle" fill="{colour}">{parser}</text>
    <text x="284" y="108" text-anchor="middle" fill="rgba(255,255,255,.5)" font-size="11">deterministic</text>
    <text x="284" y="124" text-anchor="middle" fill="rgba(255,255,255,.5)" font-size="11">no model</text>
    <rect x="414" y="64" width="150" height="70" rx="5" fill="rgba(255,255,255,.05)" stroke="rgba(255,255,255,.28)" stroke-dasharray="4 4"/>
    <text x="489" y="92" text-anchor="middle" fill="rgba(255,255,255,.9)">the model</text>
    <text x="489" y="112" text-anchor="middle" fill="rgba(255,255,255,.45)" font-size="11">judgement only</text>
    <rect x="606" y="64" width="176" height="70" rx="5" fill="rgba(255,255,255,.05)" stroke="{colour}"/>
    <text x="694" y="88" text-anchor="middle" fill="{colour}">{validator}</text>
    <text x="694" y="108" text-anchor="middle" fill="rgba(255,255,255,.5)" font-size="11">contract check</text>
    <text x="694" y="124" text-anchor="middle" fill="rgba(255,255,255,.5)" font-size="11">can reject</text>
    <rect x="824" y="34" width="112" height="52" rx="5" fill="rgba(8,174,135,.10)" stroke="var(--taco-green-300)"/>
    <text x="880" y="65" text-anchor="middle" fill="var(--taco-green-300)">PASS</text>
    <rect x="824" y="112" width="112" height="52" rx="5" fill="rgba(230,101,104,.10)" stroke="var(--taco-red-300)"/>
    <text x="880" y="143" text-anchor="middle" fill="var(--taco-red-300)">REJECTED</text>
    <path d="M158 99 H192" stroke="rgba(255,255,255,.45)" marker-end="url(#ar2-{slug})"/>
    <path d="M376 99 H410" stroke="rgba(255,255,255,.45)" marker-end="url(#ar2-{slug})"/>
    <path d="M568 99 H602" stroke="rgba(255,255,255,.45)" marker-end="url(#ar2-{slug})"/>
    <path d="M786 99 H806 V60 H820" fill="none" stroke="rgba(255,255,255,.45)" marker-end="url(#ar2-{slug})"/>
    <path d="M786 99 H806 V138 H820" fill="none" stroke="rgba(255,255,255,.45)" marker-end="url(#ar2-{slug})"/>
    <path d="M284 60 V30 H489 V60" fill="none" stroke="rgba(255,255,255,.22)" stroke-dasharray="3 5"/>
    <text x="386" y="22" text-anchor="middle" fill="rgba(255,255,255,.45)" font-size="11">
      refuses here if the input is underspecified</text>
  </g>
</svg>'''


def build_panels() -> str:
    panels = []
    for slug, droid, role, folder, colour, parser, validator in DROIDS:
        ctx = (md_to_html(read(f"{folder}/context/L2-org-standards.md")) + "<hr>"
               + md_to_html(read(f"{folder}/context/L3-project.md")) + "<hr>"
               + md_to_html(read(f"{folder}/context/L3-known-deviations.md")))
        refs = sorted((REPO / folder / "references").glob("*.md"))
        contract = "<hr>".join(md_to_html(f.read_text(encoding="utf-8")) for f in refs)
        code = ("<p class='muted'>Every mechanical decision this agent makes lives "
                "here. No file in this folder calls a model.</p>"
                + "".join(script_block(folder, p.name)
                          for p in sorted((REPO / folder / "scripts").glob("*.py"))))
        flow = (pipeline_svg(slug, colour, parser, validator, role)
                + "<p class='muted'>The two boxes in "
                f"<span style='color:{colour}'>colour</span> are ordinary Python. The "
                "dashed box is the only place the model is involved, and its output has "
                "to survive the box to its right.</p>"
                "<h4>Eval suite, run just now</h4><pre><code>"
                + esc(run_evals(folder)) + "</code></pre>")
        tabs = [("skill", "SKILL.md", md_to_html(read(f"{folder}/SKILL.md"))),
                ("contract", "Contracts &amp; references", contract),
                ("context", "Context (L2 / L3)", ctx),
                ("code", "The code", code),
                ("flow", "Diagram", flow)]
        nav = "".join(
            f'<button class="dtab" data-p="{slug}" data-t="{tid}"'
            + (' aria-selected="true"' if k == 0 else "")
            + f">{label}</button>"
            for k, (tid, label, _) in enumerate(tabs))
        bodies = "".join(
            f'<div class="dpane{" on" if k == 0 else ""}" data-p="{slug}" '
            f'data-t="{tid}">{content}</div>'
            for k, (tid, _, content) in enumerate(tabs))
        panels.append(
            f'<section class="panel" id="panel-{slug}" style="--accent:{colour}">'
            f'<header class="panel-head"><div><span class="rail">{droid} &middot; '
            f'{folder}</span><h3>{role}</h3></div>'
            f'<nav class="dtabs">{nav}</nav></header>'
            f'<div class="panel-body">{bodies}</div></section>')
        print(f"  {slug}: {len(tabs)} tabs, {len(refs)} reference file(s)")
    return "".join(panels)


def main() -> int:
    t = PAGE.read_text(encoding="utf-8")
    i = t.find(START)
    j = t.find(END, i)
    if i < 0 or j < 0:
        print("could not locate the panel region in index.html", file=sys.stderr)
        return 1
    panels = build_panels()
    out = t[:i + len(START)] + panels + t[j:]
    PAGE.write_text(out, encoding="utf-8")
    print(f"\nrewrote {PAGE}  ({len(t):,} -> {len(out):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
