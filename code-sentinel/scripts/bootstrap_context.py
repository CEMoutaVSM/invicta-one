#!/usr/bin/env python3
"""Bootstrap a draft L3-project.md for a new repository.

Step 1 of the calibration protocol. Reads what the repo already tells us --
ADRs, README, folder structure -- and drafts project rules WITH the evidence
behind each one, marked `draft` so they stay dormant.

The agent cannot ratify its own context. A human must promote draft -> ratified.

Usage: python bootstrap_context.py <repo-path> [-o L3-project.draft.md]
"""
import argparse, pathlib, re, sys

SIGNALS = [
    ("layering",   r"\b(controller|service|repository|handler|usecase)\b",
     "L3-ARCH", "Layering appears to be {} - confirm the allowed call direction."),
    ("money",      r"\b(decimal|Money|Currency|amount)\b",
     "L3-DATA", "Monetary types detected - confirm the required representation."),
    ("events",     r"\b(RabbitMQ|Kafka|IEvent|DomainEvent|publish)\b",
     "L3-EVENT", "Eventing detected - confirm publish-after-commit expectation."),
    ("migrations", r"\b(migration|EF Core|Flyway|Liquibase|alembic)\b",
     "L3-DATA", "Migrations detected - confirm reversibility requirement."),
    ("auth",       r"\b(OIDC|OAuth|JWT|Authorize|permission|role)\b",
     "L3-SEC", "AuthZ detected - confirm where checks must live."),
]

def scan(repo: pathlib.Path) -> dict:
    docs, hits = [], {}
    for pat in ("README*", "docs/**/*.md", "**/adr/**/*.md", "**/ADR*.md"):
        docs += [p for p in repo.glob(pat) if p.is_file()][:20]
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore")[:20000]
                     for p in docs)
    dirs = sorted({p.relative_to(repo).parts[0] for p in repo.glob("*/")
                   if p.is_dir() and not p.name.startswith(".")})
    for name, pat, prefix, tmpl in SIGNALS:
        found = re.findall(pat, text, re.I)
        if found:
            hits[name] = (prefix, tmpl, sorted(set(f.lower() for f in found))[:6],
                          len(found))
    return {"docs": [str(p.relative_to(repo)) for p in docs], "dirs": dirs,
            "hits": hits}

def render(repo: pathlib.Path, s: dict) -> str:
    out = [f"# L3 — Project Context: {repo.name}", "",
           "Status: **DRAFT — NOT RATIFIED**", "Owner: <assign a tech lead>",
           "", "> Auto-drafted by bootstrap_context.py. Every rule below is `draft`",
           "> and therefore DORMANT: it produces no findings until a human",
           "> promotes it to `ratified`. The agent cannot ratify its own context.",
           "", f"Evidence read: {len(s['docs'])} doc(s); "
           f"top-level dirs: {', '.join(s['dirs'][:12]) or 'none'}", "",
           "## Intentional patterns a generic reviewer would wrongly flag",
           "<!-- FILL THIS IN. It is the highest-value section and cannot be",
           "     inferred reliably. List what looks wrong but is deliberate. -->",
           "- ", "", "| ID | Rule | Status | Evidence | Confidence |",
           "|---|---|---|---|---|"]
    n = 0
    for name, (prefix, tmpl, terms, count) in s["hits"].items():
        n += 1
        conf = "high" if count > 12 else "medium" if count > 4 else "low"
        out.append(f"| {prefix}-{n:02d} | {tmpl.format(', '.join(terms))} "
                   f"| draft | {count} mention(s): {', '.join(terms[:4])} | {conf} |")
    if not n:
        out.append("| — | No signals found. Write rules by hand. | draft | — | — |")
    out += ["", "## Ratification checklist",
            "- [ ] Every rule reviewed by a tech lead",
            "- [ ] Wrong rules deleted, not left as draft",
            "- [ ] Intentional patterns section completed",
            "- [ ] Status changed to `ratified` on rules that survive",
            "- [ ] Golden set re-run to confirm no true positives were lost", ""]
    return "\n".join(out)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo"); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}"); return 2
    md = render(repo, scan(repo))
    if a.out:
        pathlib.Path(a.out).write_text(md, encoding="utf-8")
        print(f"wrote {a.out} — DRAFT, requires human ratification")
    else:
        print(md)
    return 0

if __name__ == "__main__":
    sys.exit(main())
