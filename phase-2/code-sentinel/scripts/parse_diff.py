#!/usr/bin/env python3
"""Deterministic unified-diff parser for the Code Sentinel.

Segments a diff into files and hunks, classifies each file, and flags
paths that must not be reviewed. No LLM anywhere in this file.

Accepts both `diff --git a/x b/x` headers and bare `--- a/x` / `+++ b/x`
pairs, including a diff that mixes the two. Keying only on `diff --git`
meant a mixed-format diff parsed to one file and the rest of the change —
secrets and all — was never seen by the reviewer.

Usage:  python parse_diff.py <file.diff>   # or stdin
Exit:   0 parsed (including a clean refusal) / 2 usage error
"""
import json
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


GIT_HDR = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$")
OLD_HDR = re.compile(r"^--- (?:a/)?(.+?)\s*$")
NEW_HDR = re.compile(r"^\+\+\+ (?:b/)?(.+?)\s*$")
HUNK_HDR = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
DIFFISH = re.compile(r"^(@@ |\+\+\+ |--- |diff --git )", re.M)
# Enough prose to be a pull-request description rather than an empty file
# or a stray fragment: six or more words on one line.
PROSE = re.compile(r"^\s*(?:\S+\s+){5,}\S+", re.M)

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
# `test_calc.py` is pytest's default naming and was classified reviewable, so a
# diff that added a branch *and its test* was still reported as untested and the
# review was rejected for missing a defect that did not exist.
TEST_PAT = re.compile(r"(^|/)(tests?|spec|__tests__)/|"
                      r"\.(test|spec)\.[jt]sx?$|Tests?\.cs$|"
                      r"(^|/)test_[\w.-]+\.py$|_test\.(py|go|rb)$|"
                      r"_spec\.rb$|Test\.java$|Spec\.scala$", re.I)

# High-confidence secrets. These need no judgement at all, and the recall check
# used to hinge only on new branches — so a diff that added a live key while
# touching no control flow triggered nothing, and an APPROVE sailed through.
# A test file counts: a production credential in a test is still a production
# credential.
# Only vendor-issued token formats. Each is unambiguous: nothing but a real
# credential looks like this, so demanding a finding cannot be wrong.
#
# A broader `password = "..."` rule was here and had to go. It fired on
# `// api_key = "your-key-here"` in a comment, on `password = "changeme"`, and
# on `secret = "billing-api-key"` naming a vault entry. The reviewer then could
# not pass without raising a finding about something that was not a defect —
# an agent that forces you to fabricate is worse than one that stays quiet.
# Anything requiring judgement now lands in `possible_secrets`, which the model
# is asked to look at and the validator does not demand.
SECRET_PAT = [
    (re.compile(r"\bsk_live_[A-Za-z0-9]{12,}"), "Stripe live secret key"),
    (re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bprod-sk-[A-Za-z0-9]{6,}"), "production secret key"),
]

# Worth a human's eye, never a demand. Placeholders are excluded so the model is
# not sent to look at `changeme`.
MAYBE_SECRET = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token|conn(?:ection)?"
    r"[_-]?string)\b\s*[:=]\s*[\"'][^\"'\s]{6,}[\"']")
PLACEHOLDER = re.compile(
    r"(?i)your[-_ ]?(key|secret|token)|changeme|placeholder|example|dummy|sample|"
    r"redacted|xxx+|\.\.\.|<[^>]+>|\$\{|%s|\{\{|TODO|FIXME|test[-_]?key|"
    r"fake|not[-_]?a[-_]?real")
# A token split across a concatenation still ships a credential.
SPLIT_SECRET = re.compile(r"[\"'](?:sk_live_|ghp_|AKIA|prod-sk-|xox[baprs]-)"
                          r"[A-Za-z0-9_-]*[\"']\s*[+.,]\s*[\"']")

# Conditional branches touched by the diff. Both directions matter: adding a
# branch needs a test, and *removing* one (a deleted guard) changes control
# flow just as much.
BRANCH_TOKENS = (r"\b(if|else if|elif|switch|case|catch|when|for|foreach|"
                 r"while|do|until)\b|\?\?|\|\||&&")
BRANCH = re.compile(BRANCH_TOKENS)
# String literals and comments are stripped before branch detection, in that
# order. Two false readings came from skipping this:
#   - a prose comment "hidden button for bookkeepers" counted as a branch on
#     the word "for", demanding a test for control flow that does not exist;
#   - a colour literal `"#101010"` looked like the start of a comment, which
#     erased the real `if` after it and disarmed the recall check entirely.
STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
COMMENT = re.compile(r"(//|#|--\s).*$|/\*.*?\*/", re.S)


def strip_comments(s: str) -> str:
    """Remove comments, leaving string literals intact.

    A regex cannot do this. `COMMENT` treated the `//` in
    `"postgres://admin:prod-sk-9f8e@db"` as the start of a comment and deleted
    the credential with the rest of the line, so a live key reached neither the
    demand list nor the advisory one. Anything inside quotes is text, `//` and
    `#` included.
    """
    out, i, n, quote = [], 0, len(s), None
    while i < n:
        c = s[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote, i = c, i + 1
            out.append(c)
            continue
        if s.startswith("/*", i):
            end = s.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        # A `//` preceded by `:` is a URL scheme, not a comment. Fixing
        # only the quoted form left `DATABASE_URL=postgres://admin:KEY@h`
        # - a .env, YAML or Dockerfile line - still losing its credential.
        if (s.startswith("//", i) and not (i and s[i - 1] == ":")) \
                or c == "#" or s.startswith("-- ", i):
            break
        out.append(c)
        i += 1
    return "".join(out)


# Vendors publish sample credentials that are syntactically perfect and
# deliberately dead: AWS documents AKIAIOSFODNN7EXAMPLE on its own site, and a
# negative test asserting that a malformed key is rejected legitimately contains
# a PRIVATE KEY header. Demanding a finding for either forces an honest reviewer
# to fabricate one, which is the failure this scanner exists to prevent.
EXAMPLE_TOKEN = re.compile(r"(?i)example|dummy|sample|fake|redacted|"
                           r"not[-_]?a[-_]?real|placeholder|changeme")
# A PRIVATE KEY header with no key material after it is a header, not a key:
# `docs/format.md` showing the format is documentation. The material is on
# the FOLLOWING line in real PEM, which is why this is matched against the
# file's added text rather than the header's own line.
PEM_HEADER = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
PEM_BODY = re.compile(r"^[\s+]*[A-Za-z0-9+/=]{32,}[\s]*$", re.M)


def is_filler(tok: str) -> bool:
    """A token whose body is padding rather than a credential.

    `AKIA0000000000000000` and `sk_live_deadbeefdead` are obviously dead, and
    demanding a finding for one forces a reviewer to invent a defect. A real
    credential's body is high-entropy; filler is a handful of characters
    repeated, or a hex word. `sk_live_00000004Qh8xZ2mPqRsTuVwX` is a real key
    that merely contains a run of zeros, and must NOT be caught here.
    """
    body = re.sub(r"^(sk_live_|ghp_|gho_|ghs_|github_pat_|AKIA|prod-sk-|"
                  r"xox[baprs]-)", "", tok)
    if len(body) < 4:
        return False
    if len(set(body)) <= 2:                       # 0000000000, aaaaaaaa
        return True
    # entirely hexadecimal and built from very few distinct characters:
    # deadbeefdead, cafebabecafe. A real key mixes the whole alphabet.
    return bool(re.fullmatch(r"[0-9a-fA-F]+", body)) and len(set(body.lower())) <= 6


def is_branch(line: str) -> bool:
    body = STRING.sub(" ", line[1:])     # strings first: they can contain # and //
    return bool(BRANCH.search(COMMENT.sub("", body)))


def norm(p: str) -> str:
    p = p.replace("\\", "/").strip()
    p = re.sub(r"^[ab]/", "", p)
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def classify(path: str) -> tuple[str, str | None]:
    for pat, reason in SKIP:
        if pat.search(path):
            return "skip", reason
    if TEST_PAT.search(path):
        return "test", None
    return "review", None


def parse(text: str) -> dict:
    files, cur = [], None
    pending_old = None
    in_hunk = False

    def start(path: str):
        nonlocal cur, in_hunk
        in_hunk = False
        kind, reason = classify(path)
        cur = {"path": path, "kind": kind, "skip_reason": reason,
               "added": 0, "removed": 0, "hunks": [],
               "new_branches": 0, "removed_branches": 0,
               "secrets": [], "possible_secrets": [], "added_text": []}
        files.append(cur)

    lines = text.splitlines()
    for n, line in enumerate(lines):
        if m := GIT_HDR.match(line):
            start(m.group(2).strip())
            pending_old = None
            continue
        # A real file header is the triple `--- a/x`, `+++ b/x`, `@@ ... @@`.
        # Requiring the hunk line is what separates it from in-hunk content: a
        # removed SQL comment `-- x` arrives as `--- x` and an added `++ x` as
        # `+++ x`, and treating that pair as a header opened a phantom file
        # that corrupted every count the reviewer depends on. Checking "not
        # inside a hunk" instead is wrong — in a multi-file diff every file
        # after the first is inside the previous file's hunk.
        if (m := OLD_HDR.match(line)) and n + 2 < len(lines) \
                and NEW_HDR.match(lines[n + 1]) \
                and HUNK_HDR.match(lines[n + 2]):
            pending_old = m.group(1).strip()
            continue
        if (m := NEW_HDR.match(line)) and pending_old is not None:
            new = m.group(1).strip()
            # `+++ /dev/null` is a deletion; the real path is on the --- line.
            path = pending_old if new == "/dev/null" else new
            pending_old = None
            if path and path != "/dev/null":
                # Do not double-count when `diff --git` already opened this file.
                if cur is None or norm(cur["path"]) != norm(path):
                    start(path)
            continue
        if cur is None:
            continue
        if h := HUNK_HDR.match(line):
            in_hunk = True
            cur["hunks"].append({"new_start": int(h.group(3)),
                                 "context": (h.group(5) or "").strip()})
            continue
        if line.startswith("+"):
            cur["added"] += 1
            if is_branch(line):
                cur["new_branches"] += 1
            # Comments are stripped first: an example credential written in a
            # comment is documentation, not a leak, and demanding a finding for
            # it made an honest review impossible to write.
            code = strip_comments(line[1:])
            cur["added_text"].append(code)
            for pat, what in SECRET_PAT:
                if not (m2 := pat.search(code)):
                    continue
                tok = m2.group(0)
                # A vendor's published example key is not a credential, and
                # neither is a token built from filler. Advisory, never a
                # demand: forcing a reviewer to invent a finding about a
                # non-defect is the worse of the two failure modes.
                if what == "private key":
                    # Deferred. A real PEM key puts its material on the NEXT
                    # line, so judging the header's own line demoted every
                    # genuine key in production source to advisory.
                    continue
                if EXAMPLE_TOKEN.search(tok) or is_filler(tok):
                    note = f"{what} (reads as an example): {tok[:40]}"
                    if note not in cur["possible_secrets"]:
                        cur["possible_secrets"].append(note)
                elif what not in cur["secrets"]:
                    cur["secrets"].append(what)
            if SPLIT_SECRET.search(code) and "split credential" not in cur["secrets"]:
                cur["secrets"].append("split credential")
            if (m2 := MAYBE_SECRET.search(code)) and not PLACEHOLDER.search(code):
                snippet = m2.group(0).strip()[:60]
                if snippet not in cur["possible_secrets"]:
                    cur["possible_secrets"].append(snippet)
        elif line.startswith("-"):
            cur["removed"] += 1
            if is_branch(line):
                cur["removed_branches"] += 1

    reviewable = [f for f in files if f["kind"] == "review"]
    tests = [f for f in files if f["kind"] == "test"]
    skipped = [f for f in files if f["kind"] == "skip"]
    added_branches = sum(f["new_branches"] for f in reviewable)
    deleted_branches = sum(f["removed_branches"] for f in reviewable)

    total = sum(f["added"] + f["removed"] for f in files)
    # Text that is clearly a diff but yielded no files is a parse failure, not
    # an empty change. Reporting `ok` there is the silent-no-op failure mode.
    if files:
        status = "ok"
    elif DIFFISH.search(text):
        status = "unparseable"
    elif PROSE.search(text):
        # A PR description with no diff. The brief asks for this input, and
        # refusing it was over-correction: an approach described in prose can
        # offend an architectural rule, and that finding is citable. What it
        # cannot support is a line number or a test-coverage claim, which is
        # what the validator enforces for this status.
        status = "description_only"
    else:
        status = "insufficient_input"

    # A PRIVATE KEY header is judged against the whole file's added text, not
    # the line it sits on: standard PEM puts `-----BEGIN ... KEY-----` on one
    # line and its base64 body on the next. Testing the header's own line
    # demoted every real key in production source to advisory - and a blind
    # APPROVE then passed `--diff` validation.
    for f in files:
        body = "\n".join(f.pop("added_text", []))
        if not PEM_HEADER.search(body):
            continue
        if PEM_BODY.search(body):
            if "private key" not in f["secrets"]:
                f["secrets"].append("private key")
        else:
            note = "private key header, no key material (reads as documentation)"
            if note not in f["possible_secrets"]:
                f["possible_secrets"].append(note)

    return {
        "agent": "code-sentinel",
        "version": "1.0",
        "status": status,
        "files": files,
        "coverage": {
            "files_changed": len(files),
            "reviewable": len(reviewable),
            "test_files": len(tests),
            "skipped": len(skipped),
        },
        # Deterministic input to rule L2-TEST-01: branches touched, no test change.
        "test_expectation": {
            "new_branches": added_branches,
            "removed_branches": deleted_branches,
            "test_files_touched": len(tests),
            "expectation_met": (added_branches + deleted_branches == 0
                                or len(tests) > 0),
        },
        # Defects the parser is certain about, so the review cannot omit them.
        # Test files are included: a live key committed to a test is still live.
        # Every file, including generated and vendored ones. A live key
        # committed to `dist/bundle.min.js` is exactly as live as one in source,

        # and restricting this to reviewable paths let it through untouched.
        "must_flag": [{"path": f["path"], "rule": "L2-SEC-01", "what": w}
                      for f in files for w in f["secrets"]],
        # For the model to judge, never demanded by the validator.
        "possible_secrets": [{"path": f["path"], "text": s}
                             for f in files for s in f["possible_secrets"]],
        "large_diff": total > 2000,
        "total_lines_changed": total,
    }


def brief(res: dict) -> dict:
    """The same parse, reduced to what the model actually has to review.

    The full envelope lists every file with its hunks, including the generated
    and vendored ones the agent is forbidden from reviewing — then the SKILL
    tells the model to skip them. Skipped paths collapse to a count and a
    reason; what is left is the surface a reviewer is allowed to touch.
    """
    # `files` keeps its name and its `kind`, because `validate_findings.py
    # --diff` reads exactly that to check recall and scope. Renaming it to
    # `review` made the brief envelope unreadable by our own validator, which
    # then rejected a correct review for raising findings "not in the diff".
    # What the brief actually drops is per-file line counts and hunk offsets
    # for paths the agent is forbidden to review.
    return {
        "agent": res["agent"],
        "version": res["version"],
        "status": res["status"],
        "files": [
            {"path": f["path"], "kind": f["kind"], "skip_reason": f["skip_reason"],
             **({"added": f["added"], "removed": f["removed"],
                 "new_branches": f["new_branches"],
                 "removed_branches": f["removed_branches"],
                 "secrets": f["secrets"],
                 "hunks": [{"new_start": hh["new_start"],
                            "context": hh["context"]} for hh in f["hunks"]]}
                if f["kind"] in ("review", "test") else {})}
            for f in res["files"]],
        "coverage": res["coverage"],
        "must_flag": res["must_flag"],
        "possible_secrets": res["possible_secrets"],
        "test_expectation": res["test_expectation"],
        "large_diff": res["large_diff"],
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--brief"]
    want_brief = "--brief" in sys.argv
    if args:
        try:
            raw = open(args[0], "rb").read()
        except OSError as e:
            print(f"usage: cannot read {args[0]}: {e}", file=sys.stderr)
            return 2
    else:
        raw = sys.stdin.buffer.read()
    if b"\x00" in raw:
        print("usage: input is binary, not a unified diff", file=sys.stderr)
        return 2
    text = raw.decode("utf-8", errors="replace")

    res = parse(text)
    json.dump(brief(res) if want_brief else res, sys.stdout,
              indent=2, ensure_ascii=False)
    print()
    # Text that looks like a diff but yielded no files is a failure, not an
    # empty change. Exiting 0 let a pipeline treat "I could not read this" as
    # "there was nothing to read".
    return 1 if res["status"] == "unparseable" else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
