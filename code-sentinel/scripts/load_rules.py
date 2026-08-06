#!/usr/bin/env python3
"""Rule loader / calibration engine for the Code Sentinel.

Assembles the ACTIVE rule set from the context layers:

    L2 (org)  +  L3 ratified (project)  -  active deviations  =  active rules

Rules marked `draft` are dormant. Deviations past their expiry date are
ignored, so the registry cannot quietly rot into a list of excuses.

This is deliberately code and not prose: which rules are live must be a
fact you can print, diff and put in a test, not something the model decides.

Usage:
    python load_rules.py [--context DIR] [--path src/foo.cs] [--json]

    --path  report which rules are suppressed for that specific file
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
except (AttributeError, ValueError):  # non-POSIX
    pass


ROW = re.compile(r"^\|\s*(L[23]-[A-Z]+-\d+)\s*\|\s*(.+?)\s*(?:\|\s*(\w+)\s*)?\|\s*$")
DEV_HDR = re.compile(r"^###\s+(DEV-\d+)\s*[—:-]\s*(.+?)\s*$", re.M)
SUPPRESS = re.compile(r"do not flag\s+(L[23]-[A-Z]+-\d+)\s+for paths?\s+(?:under\s+)?(\S+)",
                      re.I)


def parse_rules(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    layer = "L2" if path.name.startswith("L2") else "L3"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m or m.group(1).startswith("ID"):
            continue
        rid, text, status = m.group(1), m.group(2), (m.group(3) or "ratified")
        out.append({"id": rid, "layer": layer, "text": text,
                    "status": status.lower()})
    return out


def _field(block: str, name: str) -> str:
    """Extract `Name: value` from a block. Field order is irrelevant."""
    m = re.search(rf"^{name}:\s*(.+?)$", block, re.M | re.I)
    if not m:
        return ""
    val = m.group(1).strip()
    # Fields may share a line separated by pipes: `Status: x | Owner: y`
    return val.split("|")[0].strip()


def parse_deviations(path: pathlib.Path, today: dt.date) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    heads = list(DEV_HDR.finditer(text))
    out = []
    for i, m in enumerate(heads):
        did, title = m.group(1), m.group(2)
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[m.end():end]
        status = _field(block, "Status") or "unknown"
        expires = _field(block, "Expires")
        behaviour = _field(block, "Agent behaviour")
        try:
            exp = dt.date.fromisoformat(expires if len(expires) > 7
                                        else expires + "-01")
        except ValueError:
            exp = None
        expired = bool(exp and exp < today)
        sup = SUPPRESS.search(behaviour.replace("\n", " "))
        out.append({
            "id": did, "title": title.strip(), "status": status.lower(),
            "expires": expires, "expired": expired,
            "active": status.lower() == "accepted" and not expired,
            "suppresses": sup.group(1) if sup else None,
            "path_glob": sup.group(2).rstrip(".") if sup else None,
            "behaviour": " ".join(behaviour.split()),
        })
    return out


def load(context_dir: pathlib.Path, today: dt.date) -> dict:
    rules = (parse_rules(context_dir / "L2-org-standards.md")
             + parse_rules(context_dir / "L3-project.md"))
    devs = parse_deviations(context_dir / "L3-known-deviations.md", today)

    active = [r for r in rules if r["status"] == "ratified"]
    dormant = [r for r in rules if r["status"] != "ratified"]
    has_l2 = (context_dir / "L2-org-standards.md").exists()
    has_l3 = (context_dir / "L3-project.md").exists()
    # "L2-only" must not be reported when L2 is missing too. An agent with an
    # empty rule set cannot flag anything, and would return a clean review of
    # code it never checked - the worst possible failure, because it looks fine.
    mode = "L2+L3" if (has_l2 and has_l3) else "L2-only" if has_l2 else "NO-CONTEXT"

    return {
        "agent": "code-sentinel",
        "mode": mode,
        "usable": bool(active),
        "evaluated_at": today.isoformat(),
        "active_rules": active,
        "dormant_rules": dormant,
        "deviations": devs,
        "expired_deviations": [d["id"] for d in devs if d["expired"]],
        "counts": {"active": len(active), "dormant": len(dormant),
                   "deviations_active": sum(1 for d in devs if d["active"])},
        "warnings": (
            ([] if has_l3 else
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
            + [f"{d['id']} expired on {d['expires']} - suppression no longer "
               "applied" for d in devs if d["expired"]]
        ),
    }


def suppressed_for(loaded: dict, path: str) -> list[dict]:
    out = []
    for d in loaded["deviations"]:
        if not d["active"] or not d["path_glob"]:
            continue
        glob = d["path_glob"].strip("/")
        if fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(path, glob + "/*") \
           or path.startswith(glob.replace("**", "").rstrip("/") + "/"):
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

    loaded = load(pathlib.Path(a.context), dt.date.fromisoformat(a.today))
    if a.path:
        loaded["suppressed_for_path"] = {a.path: suppressed_for(loaded, a.path)}

    if a.json:
        json.dump(loaded, sys.stdout, indent=2)
        print()
        return 0

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
    sys.exit(main())
