#!/usr/bin/env python3
"""Rule loader / calibration engine for the Code Sentinel.

Assembles the ACTIVE rule set from the context layers:

    L2 (org)  +  L3 ratified (project)  -  active deviations  =  active rules

Rules marked `draft` are dormant. Deviations past their expiry date are
ignored, so the registry cannot quietly rot into a list of excuses.

This is deliberately code and not prose: which rules are live must be a
fact you can print, diff and put in a test, not something the model decides.

FAIL-SAFE CONTRACT
------------------
Every ambiguity in this file resolves towards *flagging more*, never less:

  - a context file that exists but parses to zero rules is a CONFIG ERROR,
    not an empty rule set. Silently loading nothing produces a clean review
    of unchecked code, which is the worst failure this agent can have.
  - a rule whose status is not recognisably ratified is DORMANT.
  - a deviation whose expiry is missing or unparseable does NOT suppress.

Usage:
    python load_rules.py [--context DIR] [--path src/foo.cs] [--json]

    --path  report which rules are suppressed for that specific file

Exit: 0 usable rule set / 2 usage error / 3 config error
"""
import argparse
import datetime as dt
import fnmatch
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


RULE_ID = re.compile(r"L[23]-[A-Z]+-\d+")
DEV_HDR = re.compile(r"^#{2,4}\s+(DEV-\d+)\s*[‐-―—–:-]\s*(.+?)\s*$", re.M)
SUPPRESS = re.compile(r"do not flag\s+(L[23]-[A-Z]+-\d+)\s+for paths?\s+(?:under\s+)?(\S+)",
                      re.I)

# A status is only ratified if it says so unambiguously. Anything carrying a
# provisional word is dormant, however it is dressed up: `draft`,
# `draft (pending ADR-012)`, `not-ratified`, `DRAFT - do not use`.
RATIFIED = {"ratified", "active", "accepted", "approved", "in force"}
PROVISIONAL = re.compile(
    r"\b(draft|proposed|pending|provisional|not[-\s]?ratified|unratified|"
    r"wip|tbd|todo|do not use|deprecated|retired|superseded)\b", re.I)

FIELD_NAMES = ("status", "owner", "reviewed", "rationale",
               "agent behaviour", "agent behavior", "expires")


def _demph(text: str) -> str:
    """Strip markdown emphasis so `**Status:**` parses like `Status:`.

    Underscores are preserved. Stripping them rewrote suppression targets —
    `src/read_model` became `src/readmodel` — so the deviation displayed as
    active and silently suppressed nothing.
    """
    return re.sub(r"[*`]+", "", text)


def mask_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line numbering.

    Everything in this codebase parses markdown line by line, which means an
    *example* inside a ``` block reads as live content. A rules table shown as
    documentation put a fabricated rule ID into the active set, which defeats
    the citation rule outright; the same blindness invented findings from
    templates and misread quoted refusals. Content is replaced with empty lines
    rather than removed so line counts and offsets stay aligned.
    """
    out, fence = [], None
    for line in text.split("\n"):
        s = line.lstrip()
        if fence is None:
            m = re.match(r"(`{3,}|~{3,})", s)
            if m:
                fence = m.group(1)[0] * 3
                out.append("")
                continue
            out.append(line)
        else:
            out.append("")
            if s.startswith(fence):
                fence = None
    return "\n".join(out)


def parse_rules(path: pathlib.Path) -> tuple[list[dict], list[str]]:
    """Return (rules, parse_errors).

    A file that exists but yields no rules is an error, not an empty list.
    """
    if not path.exists():
        return [], []
    layer = "L2" if path.name.startswith("L2") else "L3"
    out, saw_table = [], False
    for line in mask_fences(path.read_text(encoding="utf-8")).splitlines():
        s = _demph(line).strip()
        if not s.startswith("|"):
            continue
        saw_table = True
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or not RULE_ID.fullmatch(cells[0]):
            continue
        rid, text = cells[0], cells[1]
        status = (cells[2].strip() if len(cells) > 2 and cells[2].strip()
                  else "ratified")
        low = status.lower()
        if PROVISIONAL.search(low):
            norm = "draft"
        elif low in RATIFIED:
            norm = "ratified"
        else:
            # Unrecognised status fails safe: dormant, and say so.
            norm = "unrecognised"
        out.append({"id": rid, "layer": layer, "text": text,
                    "status": norm, "status_raw": status})

    errs = []
    if not out:
        errs.append(f"CONFIG: {path.name} exists but no rules parsed from it. "
                    "Expected a markdown table with rows like "
                    "`| L2-SEC-01 | text | ratified |`. Refusing to treat this "
                    "as an empty rule set."
                    + ("" if saw_table else " No table rows found at all."))
    for r in out:
        if r["status"] == "unrecognised":
            errs.append(f"CONFIG: {r['id']} has unrecognised status "
                        f"{r['status_raw']!r} - treated as DORMANT. Use "
                        "'ratified' or 'draft'.")
    return out, errs


def _field(block: str, name: str) -> str:
    """Extract `Name: value` from a block, tolerating emphasis and wrapping.

    Field order is irrelevant. A value may continue onto following lines until
    a blank line, a new field, or a new heading.
    """
    lines = _demph(block).splitlines()
    pat = re.compile(rf"^\s*{re.escape(name)}\s*:\s*(.*)$", re.I)
    nxt = re.compile(r"^\s*(" + "|".join(re.escape(f) for f in FIELD_NAMES)
                     + r")\s*:", re.I)
    for i, line in enumerate(lines):
        m = pat.match(line)
        if not m:
            continue
        parts = [m.group(1).strip()]
        for cont in lines[i + 1:]:
            if not cont.strip() or nxt.match(cont) or cont.lstrip().startswith("#"):
                break
            parts.append(cont.strip())
        return " ".join(p for p in parts if p).split("|")[0].strip()
    return ""


def _parse_expiry(raw: str) -> tuple[dt.date | None, str]:
    """Return (last valid day, problem).

    A date we cannot read is a problem, not a pass. `2027-01` means "through
    January 2027", so it resolves to the LAST day of that month: reading it as
    the 1st retired a deviation four weeks early and, on a month boundary,
    made a deviation written this month already expired.
    """
    s = raw.strip()
    if not s:
        return None, "missing"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = (int(x) for x in s.split("-"))
        if not 1 <= m <= 12:
            return None, f"unparseable ({s!r})"
        nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
        return nxt - dt.timedelta(days=1), ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return dt.date.fromisoformat(s), ""
        except ValueError:
            return None, f"unparseable ({s!r})"
    return None, f"unparseable ({s!r})"


def parse_deviations(path: pathlib.Path, today: dt.date) -> list[dict]:
    if not path.exists():
        return []
    text = mask_fences(path.read_text(encoding="utf-8"))
    plain = _demph(text)
    heads = list(DEV_HDR.finditer(plain))
    out = []
    for i, m in enumerate(heads):
        did, title = m.group(1), m.group(2)
        end = heads[i + 1].start() if i + 1 < len(heads) else len(plain)
        block = plain[m.end():end]
        status = (_field(block, "Status") or "unknown").lower()
        expires = _field(block, "Expires")
        behaviour = (_field(block, "Agent behaviour")
                     or _field(block, "Agent behavior"))
        exp, exp_problem = _parse_expiry(expires)
        expired = bool(exp and exp < today)
        sup = SUPPRESS.search(" ".join(behaviour.split()))

        problems = []
        if exp_problem:
            problems.append(f"expiry {exp_problem}")
        if status == "accepted" and not sup:
            problems.append("no parseable 'Agent behaviour: do not flag <RULE> "
                            "for paths under <path>' line")

        # A deviation only suppresses when everything about it is legible:
        # accepted, unexpired, with a readable expiry and a readable target.
        active = (status == "accepted" and exp is not None
                  and not expired and sup is not None)
        out.append({
            "id": did, "title": title.strip(), "status": status,
            "expires": expires, "expired": expired,
            "active": active,
            "suppresses": sup.group(1) if sup else None,
            "path_glob": sup.group(2).rstrip(".") if sup else None,
            "behaviour": " ".join(behaviour.split()),
            "problems": problems,
        })
    return out


def load(context_dir: pathlib.Path, today: dt.date) -> dict:
    l2_path = context_dir / "L2-org-standards.md"
    l3_path = context_dir / "L3-project.md"
    l2, e2 = parse_rules(l2_path)
    l3, e3 = parse_rules(l3_path)
    rules = l2 + l3
    parse_errors = e2 + e3
    devs = parse_deviations(context_dir / "L3-known-deviations.md", today)

    # One ID, one status. A rule re-listed in L3 as `draft` while L2 has it
    # ratified put the same ID in both sets at once, and the agent was then
    # required to cite it (recall) and forbidden from citing it (dormant) in
    # the same review - an unsatisfiable contract, reported as two unrelated
    # errors.
    by_id: dict[str, set[str]] = {}
    for r in rules:
        by_id.setdefault(r["id"], set()).add(r["status"])
    for rid, statuses in sorted(by_id.items()):
        if len(statuses) > 1:
            parse_errors.append(
                f"CONFIG: {rid} is declared more than once with conflicting "
                f"statuses ({', '.join(sorted(statuses))}). A rule is either "
                "live or dormant; it cannot be both.")

    active = [r for r in rules if r["status"] == "ratified"]
    dormant = [r for r in rules if r["status"] != "ratified"
               and r["id"] not in {a["id"] for a in rules
                                   if a["status"] == "ratified"}]
    has_l2, has_l3 = l2_path.exists(), l3_path.exists()
    # "L2-only" must not be reported when L2 is missing too. An agent with an
    # empty rule set cannot flag anything, and would return a clean review of
    # code it never checked - the worst possible failure, because it looks fine.
    mode = "L2+L3" if (has_l2 and has_l3) else "L2-only" if has_l2 else "NO-CONTEXT"

    for d in devs:
        for p in d["problems"]:
            parse_errors.append(
                f"CONFIG: {d['id']} has {p} - suppression NOT applied. A "
                "deviation the loader cannot read must never silence a rule.")

    # usable requires BOTH a non-empty rule set AND a clean parse. A context
    # directory we half-understood is a config error, not a smaller rule set.
    usable = bool(active) and not parse_errors

    return {
        "agent": "code-sentinel",
        "mode": mode,
        "usable": usable,
        "evaluated_at": today.isoformat(),
        "active_rules": active,
        "dormant_rules": dormant,
        "deviations": devs,
        "expired_deviations": [d["id"] for d in devs if d["expired"]],
        "parse_errors": parse_errors,
        "counts": {"active": len(active), "dormant": len(dormant),
                   "deviations_active": sum(1 for d in devs if d["active"])},
        "warnings": (
            parse_errors
            + ([] if has_l3 else
               ["No L3-project.md found. Architectural checks are DISABLED. "
                "Do not infer architecture from the diff."])
            + ([] if has_l2 else
               ["No L2-org-standards.md found. The org security baseline is "
                "NOT loaded."])
            + ([] if active else
               ["FATAL: the active rule set is EMPTY. The agent cannot raise "
                "any finding and must NOT report a verdict. Reviewing with no "
                "rules produces a clean result for unchecked code. Restore "
                f"context/ (looked in: {context_dir})."])
            + ([] if usable or not active else
               ["FATAL: the context parsed with errors. The agent must NOT "
                "report a verdict until they are resolved."])
            + [f"{d['id']} expired on {d['expires']} - suppression no longer "
               "applied" for d in devs if d["expired"]]
        ),
    }


def norm_path(p: str) -> str:
    """Canonical path form, so suppression cannot be defeated by path shape.

    `a/src/x.cs`, `./src/x.cs` and `src\\x.cs` are the same file. Git diffs
    emit the first form, so not normalising meant suppression silently failed
    on exactly the input this agent is fed in production.
    """
    p = p.replace("\\", "/").strip()
    p = re.sub(r"^[ab]/", "", p)
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def suppressed_for(loaded: dict, path: str) -> list[dict]:
    out = []
    # fnmatchcase, not fnmatch: fnmatch is case-insensitive on Windows and
    # case-sensitive elsewhere, which made suppression platform-dependent.
    p = norm_path(path)
    for d in loaded["deviations"]:
        if not d["active"] or not d["path_glob"]:
            continue
        glob = norm_path(d["path_glob"])
        if (fnmatch.fnmatchcase(p, glob) or fnmatch.fnmatchcase(p, glob + "/*")
                or p == glob or p.startswith(glob + "/")):
            out.append({"rule": d["suppresses"], "deviation": d["id"],
                        "expires": d["expires"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", default=str(pathlib.Path(__file__).parent.parent
                                             / "context"))
    ap.add_argument("--path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args()

    try:
        today = dt.date.fromisoformat(a.today)
    except ValueError:
        print(f"usage: --today expects YYYY-MM-DD, got {a.today!r}",
              file=sys.stderr)
        return 2
    ctx = pathlib.Path(a.context)
    if ctx.exists() and not ctx.is_dir():
        print(f"CONFIG: --context must be a directory, got {ctx}",
              file=sys.stderr)
        return 3

    try:
        loaded = load(ctx, today)
    except (UnicodeDecodeError, OSError) as e:
        print(f"CONFIG: cannot read context under {ctx}: {e}", file=sys.stderr)
        return 3
    if a.path:
        loaded["suppressed_for_path"] = {a.path: suppressed_for(loaded, a.path)}

    if a.json:
        json.dump(loaded, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0 if loaded["usable"] else 3

    print(f"Mode: {loaded['mode']}   ({loaded['counts']['active']} active, "
          f"{loaded['counts']['dormant']} dormant, "
          f"{loaded['counts']['deviations_active']} deviations)")
    for r in loaded["active_rules"]:
        print(f"  [{r['layer']}] {r['id']:<14} {r['text'][:74]}")
    for r in loaded["dormant_rules"]:
        print(f"  [DORMANT]  {r['id']:<14} {r['text'][:74]}")
    for d in loaded["deviations"]:
        state = "active" if d["active"] else ("EXPIRED" if d["expired"] else d["status"])
        tgt = f" suppresses {d['suppresses']} on {d['path_glob']}" if d["suppresses"] else ""
        print(f"  [{state:>7}]  {d['id']}: {d['title'][:52]}{tgt}")
    if a.path:
        s = loaded["suppressed_for_path"][a.path]
        print(f"\nFor {a.path}: " + (", ".join(f"{x['rule']} (via {x['deviation']})"
                                               for x in s) if s else "no suppressions"))
    for w in loaded["warnings"]:
        print(f"  ! {w}")
    return 0 if loaded["usable"] else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # piped into head/less on a non-POSIX shell
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
