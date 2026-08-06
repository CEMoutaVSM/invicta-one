#!/usr/bin/env python3
"""Deterministic unified-diff parser for the Code Sentinel.

Segments a diff into files and hunks, classifies each file, and flags
paths that must not be reviewed. No LLM anywhere in this file.

Usage:  python parse_diff.py <file.diff>   # or stdin
"""
import json
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX
    pass


FILE_HDR = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.M)
HUNK_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

# Paths the agent is forbidden from reviewing. Reviewing generated code
# is the fastest way to fill an output with noise.
SKIP = [
    (re.compile(r"(^|/)(dist|build|out|bin|obj|node_modules|vendor|generated|autogen)/"), "generated/vendored"),
    (re.compile(r"\.(lock|min\.js|min\.css|map)$"), "lockfile/minified"),
    (re.compile(r"(^|/)__snapshots__/|\.snap$"), "snapshot"),
    (re.compile(r"\.(designer|g|generated)\.(cs|ts|js)$"), "generated"),
    (re.compile(r"(^|/)migrations?/.*\.(sql|Designer\.cs)$"), "migration artefact"),
    (re.compile(r"\.(png|jpg|jpeg|gif|svg|ico|woff2?|ttf|pdf)$"), "binary asset"),
]
TEST_PAT = re.compile(r"(^|/)(tests?|spec|__tests__)/|"
                      r"\.(test|spec)\.[jt]sx?$|Tests?\.cs$|_test\.py$", re.I)

# New conditional branches introduced by the diff. Used to compute the
# test-coverage expectation deterministically.
BRANCH = re.compile(r"^\+.*\b(if|else if|elif|switch|case|catch|when|"
                    r"\?\?|\|\||&&|for|while)\b")


def classify(path: str) -> tuple[str, str | None]:
    for pat, reason in SKIP:
        if pat.search(path):
            return "skip", reason
    if TEST_PAT.search(path):
        return "test", None
    return "review", None


def parse(text: str) -> dict:
    files, cur = [], None
    for line in text.splitlines():
        m = FILE_HDR.match(line)
        if m:
            path = m.group(2)
            kind, reason = classify(path)
            cur = {"path": path, "kind": kind, "skip_reason": reason,
                   "added": 0, "removed": 0, "hunks": [], "new_branches": 0}
            files.append(cur)
            continue
        if cur is None:
            continue
        h = HUNK_HDR.match(line)
        if h:
            cur["hunks"].append({"new_start": int(h.group(3)),
                                 "context": (h.group(5) or "").strip()})
            continue
        if line.startswith("+") and not line.startswith("+++"):
            cur["added"] += 1
            if BRANCH.match(line):
                cur["new_branches"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            cur["removed"] += 1

    reviewable = [f for f in files if f["kind"] == "review"]
    tests = [f for f in files if f["kind"] == "test"]
    skipped = [f for f in files if f["kind"] == "skip"]
    branches = sum(f["new_branches"] for f in reviewable)

    total = sum(f["added"] + f["removed"] for f in files)
    return {
        "agent": "code-sentinel",
        "version": "1.0",
        "status": "ok" if files else "insufficient_input",
        "files": files,
        "coverage": {
            "files_changed": len(files),
            "reviewable": len(reviewable),
            "test_files": len(tests),
            "skipped": len(skipped),
        },
        # Deterministic input to rule L2-TEST-01: new branches with no test change.
        "test_expectation": {
            "new_branches": branches,
            "test_files_touched": len(tests),
            "expectation_met": branches == 0 or len(tests) > 0,
        },
        "large_diff": total > 2000,
        "total_lines_changed": total,
    }


def main() -> int:
    text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    json.dump(parse(text), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
