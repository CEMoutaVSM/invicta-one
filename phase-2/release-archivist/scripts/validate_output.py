#!/usr/bin/env python3
"""Contract validator for the Release Archivist.

Three things the model is not trusted on: the coverage ledger reconciling,
the published entries actually being present, and internal tokens leaking
into customer-facing text.

THE ENTRY COUNT IS THE POINT
----------------------------
Checking that the ledger's own arithmetic adds up proves nothing — the model
writes the ledger. A release note declaring `published=6` while listing two
bullets satisfied every arithmetic check and passed. The zero-loss guarantee
only means something if the *body* is counted against the *claim*.

Usage: python validate_output.py <notes.md> [--ledger classify.json]
Exit:  0 valid / 1 contract violation / 2 usage error
"""
import argparse
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


COVERAGE = re.compile(r"<!--\s*Coverage:\s*in=(\d+)\s+published=(\d+)\s+"
                      r"internal=(\d+)\s+suppressed=(\d+)\s+accounted=(\d+)"
                      r"(?:\s+duplicates=(\d+))?")
# `delegated=11:INTERNAL,14:FEATURE` — the lines the classifier could not place
# and the model resolved. Naming them is what makes the permission auditable.
DELEGATED = re.compile(r"delegated=([\w:,\s-]+?)(?:\s+\w+=|\s*-->)")
# Each published bullet names the input line it came from, in an HTML comment
# the customer never sees: `- **Thing** — text. <!-- src:9 -->`.
#
# Counting bullets is not enough, and neither is a list in the coverage comment.
# Dropping a shipped feature while publishing a suppressed merge commit keeps
# both the count and any summary list intact. The guarantee has to attach to
# each entry individually, so every bullet is traceable to the line it reports.
ENTRY_SRC = re.compile(r"^\s*[-*]\s+\*\*(?P<title>.+?)\*\*.*?"
                       r"<!--\s*src:(?P<line>\d+)\s*-->", re.M | re.S)
PUBLISHED = {"FEATURE", "FIX", "IMPROVEMENT"}
CLASSES = PUBLISHED | {"INTERNAL", "NOISE"}
INTERNAL_MARK = "<!-- INTERNAL"
# A refusal is a whole-document state on its own line, not a substring anyone
# can paste in to skip every check below.
# Matched against emphasis-flattened text: `**Status:** insufficient_input`
# puts the colon inside the bold, and that form was not recognised as a
# refusal at all, so the three agents disagreed about what a refusal looks like.
REFUSAL = re.compile(r"^\s*Status\s*:\s*insufficient_input\s*\.?\s*$", re.M | re.I)

# Structural leaks. Project vocabulary is NOT hardcoded here — see load_leaks.
#
# Each pattern is narrowed to avoid rejecting ordinary English. The loose
# versions flagged "effaced" as a commit hash, "UTF-8" as a ticket key and
# "feature/report card" as a branch name — and a validator that rejects correct
# release notes gets switched off just as fast as one that misses leaks.
STRUCTURAL_LEAKS = [
    # A hash contains at least one digit; `effaced`, `decade` and `facade` are
    # words, not SHAs.
    (re.compile(r"\b(?=[0-9a-f]{7,40}\b)[0-9a-f]*\d[0-9a-f]*\b"), "commit hash"),
    # A ticket key has a letters-only prefix and at least two digits, and is not
    # a standards identifier.
    # Deliberately narrow. Anything letters-dash-digits is also how people
    # write SLA-95, US-2026, COVID-19 and half the standards in existence, and
    # rejecting those made correct release notes fail. When a classifier ledger
    # is supplied, the real ticket keys are read from it instead of guessed —
    # see `ticket_keys_from_ledger`, which is exact rather than shaped.
    (re.compile(r"\b(?:PROJ|JIRA|TICKET|ISSUE|BUG|TASK|STORY|EPIC)-\d{2,}\b"),
     "ticket key"),
    # A branch slug carries a separator or a digit: `feature/bulk-export`, not
    # the phrase "feature/report card".
    (re.compile(r"\b(feature|bugfix|hotfix|release)/(?=[\w.-]*[-_.\d])[\w.-]+"),
     "branch name"),
    (re.compile(r"\b(revolutionary|game-?changing|seamless|cutting-?edge)\b", re.I),
     "marketing superlative (L2-REL-06)"),
]
# Fallback only. Used when L3 is absent, and reported as a warning, because a
# hardcoded copy of the project's vocabulary silently rots as L3 grows.
FALLBACK_TERMS = ["PostingService", "PeriodGuard", "IQueryable", "RabbitMQ",
                  "EF Core", "read-model", "projection", "middleware",
                  "repository"]


def load_leak_terms(context_dir: pathlib.Path) -> tuple[list[str], list[str]]:
    """Read the internal vocabulary from the L3 translation table.

    The forbidden-name list used to be a hardcoded copy of the left-hand
    column of that table. Two lists, one meaning: they diverge the first time
    someone extends L3 and the validator keeps passing text it should catch.
    """
    f = context_dir / "L3-project.md"
    if not f.exists():
        return FALLBACK_TERMS, [
            f"L3-project.md not found under {context_dir}; falling back to a "
            "built-in vocabulary list, which may be out of date"]
    terms, in_table, seen_row = [], False, False
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.lower().startswith("## translation table"):
            in_table = True
            continue
        if not in_table:
            continue
        if s.startswith("#"):
            break
        # The table ends at the first non-row line after it started. Without
        # this the loop ran straight on into the rules table below and treated
        # its header cell as vocabulary, so any note containing the word "ID"
        # was rejected as an internal-name leak.
        if not s.startswith("|"):
            if seen_row:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: "):
            continue
        if cells[0].lower() in ("internal", "id"):
            continue
        if re.fullmatch(r"L\d-[A-Z]+-\d+", cells[0]):
            continue
        seen_row = True
        for part in re.split(r"[/,]", cells[0]):
            t = part.strip()
            if t and t.lower() not in ("internal",):
                terms.append(t)
    if not terms:
        return FALLBACK_TERMS, [
            "L3-project.md has no readable translation table; falling back to "
            "a built-in vocabulary list"]
    return sorted(set(terms)), []


def mask_fences(text: str) -> str:
    """Blank fenced code blocks, preserving line numbering.

    The two sibling agents had this; the archivist did not, so a refusal that
    quoted the coverage template inside a ``` block was read as publishing a
    ledger and rejected.
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


# Ticket-shaped. Shape alone is not enough in either direction: `PROJ-1234567`
# leaked (the digit bound was too tight) while `RS-232 serial devices` was
# rejected as a leak. What separates them is not the prefix but the context - a
# pasted ticket key arrives announced, because whoever pasted it was pointing at
# a tracker.
TICKET_SHAPE = re.compile(r"\b(?P<prefix>[A-Z][A-Z0-9]{1,9})-(?P<num>\d{1,7})\b")
# The announcement: a tracking word just before the key, or the key standing
# alone inside brackets - `(ACME-4521)`, `[PROJ-2811]`.
# Tracker words only. `fix`, `close` and `resolve` are the ordinary verbs of a
# release note - `fixed RJ-45 detection`, `fixes DDR-4 timing` - and reading
# them as announcements put hardware standards back on the leak list.
ANNOUNCED = re.compile(
    r"(?i)\b(track\w*|ticket|issue|bug|story|epic|task|card|"
    r"ref\w*|see|jira|backlog)"
    r"(?:\s+(?:as|in|to|at|by|for|under|via|on))?\W{0,4}$")
# Years and service levels are never keys, announced or not.
# Prefixes that name a standard, a measurement, a place or a piece of hardware.
NOT_TRACKERS = {"SLA", "ISO", "RFC", "GDPR", "CVE", "PCI", "SOC", "ITIL",
                "IEEE", "ANSI", "UTF", "SHA", "AES", "RSA", "TLS", "SSL",
                "HTTP", "API", "OKR", "KPI", "EU", "US", "UK", "PT", "DK",
                "NO", "SE", "FI", "NL", "DE", "FY", "IE", "COVID",
                "RS", "RJ", "RTX", "GTX", "RX", "GT", "DDR", "HDR", "UHD",
                "USB", "HDMI", "SATA", "NVME", "ARM", "IPV", "MW", "KW",
                "KB", "MB", "GB", "TB", "IP", "AC", "DC"}


def ticket_keys_in(text: str) -> list[str]:
    """Ticket keys the ledger does not know about, announced as such."""
    out = []
    for m in TICKET_SHAPE.finditer(text):
        prefix, num = m.group("prefix"), m.group("num")
        if len(num) == 4 and 1900 <= int(num) <= 2100:
            continue                      # a year, not a ticket
        before = text[max(0, m.start() - 24):m.start()]
        opener = text[m.start() - 1:m.start()]
        closer = text[m.end():m.end() + 1]
        # ...or standing alone in brackets, with enough digits to be a ticket
        # number rather than a standard: `[US-4521]` yes, `(RJ-45)` no.
        # ...or standing alone in brackets, with enough digits to be a ticket
        # number rather than a standard: `[US-4521]` yes, `(RJ-45)` no.
        announced = bool(ANNOUNCED.search(before)) or (
            opener in "([" and closer in ")]" and len(num) >= 3)
        # A project key also has a shape a standard does not: three or more
        # letters, no digits among them, and a ticket-length number. Requiring
        # an announcement as the ONLY signal let `Fixed ACME-4521:` and a bare
        # `the ACME-4521 integration` leak, because `fix` and `close` had to be
        # dropped from the tracker words - they are the ordinary verbs of a
        # release note and were dragging RJ-45 and DDR-4 onto the leak list.
        keyish = (len(prefix) >= 3 and prefix.isalpha() and len(num) >= 3
                  and prefix not in NOT_TRACKERS)
        if not (announced or keyish):
            continue
        if prefix in NOT_TRACKERS and len(num) <= 2:
            continue                      # SLA-95, KPI-77: a level, not a key
        if m.group(0) not in out:
            out.append(m.group(0))
    return out

def ticket_keys_from_ledger(ledger: dict | None) -> list[str]:
    """The ticket keys this release actually touched.

    Pattern-matching for anything ticket-shaped cannot tell PROJ-2811 from
    SLA-95. The classifier already extracted every key in the input, so when a
    ledger is available the check becomes exact: these specific keys must not
    appear in customer-facing text.
    """
    if not ledger:
        return []
    keys: set[str] = set()
    for item in ledger.get("items", []):
        keys.update(item.get("tickets", []))
    return sorted(keys)


def customer_section(md: str) -> str:
    return md.split(INTERNAL_MARK)[0]


CUSTOMER_HEADING = re.compile(r"^##\s+\*{0,2}(New|Improved|Fixed)\*{0,2}\s*$", re.M)


def hidden_behind_marker(md: str) -> list[str]:
    """Customer content parked after the INTERNAL marker, where nothing checks it.

    Guarding only against the marker being the *first* thing in the document was
    not enough: one line of prose in front of it moved the entire customer
    section into the unchecked half, and every leak check then inspected that
    one harmless line. Hashes, ticket keys, branch names and internal component
    names all went out unreported.
    """
    if INTERNAL_MARK not in md:
        return []
    after = md.split(INTERNAL_MARK, 1)[1]
    errs = []
    heads = CUSTOMER_HEADING.findall(after)
    if heads:
        errs.append(f"customer sections ({', '.join(heads)}) appear AFTER the "
                    "INTERNAL marker, where they are published but never "
                    "checked - move them above it")
    entries = published_entries(after)
    if entries and not heads:
        errs.append(f"{len(entries)} published entr"
                    f"{'y' if len(entries) == 1 else 'ies'} appear after the "
                    "INTERNAL marker and would escape every leak check")
    return errs


def published_entries(body: str) -> list[str]:
    """Bulleted entries under the customer-facing headings."""
    return re.findall(r"^\s*[-*]\s+\*\*(.+?)\*\*", body, re.M)


def validate(md: str, ledger: dict | None,
             context_dir: pathlib.Path | None = None) -> list[str]:
    errs: list[str] = []
    terms, warns = (load_leak_terms(context_dir) if context_dir
                    else (FALLBACK_TERMS, []))
    errs.extend(f"WARNING: {w}" for w in warns)

    md = mask_fences(md)
    flat = re.sub(r"[*`]+", "", md)
    if REFUSAL.search(flat):
        # A refusal is still a document that must not leak, and must not also
        # claim to have published something.
        if COVERAGE.search(md) or published_entries(customer_section(md)):
            return errs + ["declares insufficient_input but also publishes "
                           "entries or a coverage ledger - a refusal releases "
                           "nothing"]
        # Liberal in what it accepts. The SKILL's own refusal template says
        # `Needed:`, and this demanded `Missing:` — so a refusal written exactly
        # to spec was rejected. Where our components disagree about a word, the
        # checker should widen rather than the author memorise a magic string.
        if not re.search(r"(Missing|Needed|Required|Reason)\s*:", flat, re.I):
            return errs + ["refusal does not state what was missing - give a "
                           "`Missing:` or `Needed:` line"]
        return errs

    if md.lstrip().startswith(INTERNAL_MARK):
        # Splitting on the marker yielded an empty customer section, so every
        # leak check below silently inspected nothing.
        errs.append("document begins with the INTERNAL marker - there is no "
                    "customer-facing section to publish or check")
    errs.extend(hidden_behind_marker(md))

    m = COVERAGE.search(md)
    if not m:
        errs.append("missing coverage audit comment - the zero-loss guarantee "
                    "is unverifiable without it")
    else:
        i, p, n, s, a = (int(x) for x in m.groups()[:5])
        dups = int(m.group(6)) if m.group(6) else 0
        if p + n + s != a:
            errs.append(f"ledger internally inconsistent: {p}+{n}+{s} != {a}")
        if i != a:
            errs.append(f"ITEMS LOST: in={i} but accounted={a} "
                        f"({i - a} item(s) vanished)")
        expected = p - dups
        if ledger:
            lc = ledger.get("coverage", {})
            if lc.get("items_in") != i:
                errs.append(f"declared in={i} but classifier saw "
                            f"{lc.get('items_in')}")
            if not lc.get("reconciles", True):
                errs.append("classifier ledger does not reconcile - the notes "
                            "must not be published from a lossy classification")

            # PER-LINE DELEGATION.
            #
            # An earlier version allowed the published total to drift by the
            # *number* of lines the rules could not place. That is not the same
            # permission: a count with no identity attached lets a settled
            # feature be deleted and a fabricated one invented, because both
            # keep the total inside the band. It also degenerated - every vague
            # line widened the allowance, so on a woolly sprint log the
            # guarantee evaporated entirely.
            #
            # The model must now name the lines it re-classified. Only lines the
            # classifier actually delegated may be named, and the published
            # total is recomputed from those specific decisions rather than
            # trusted.
            allowed = {u["line"]: u["provisional"]
                       for u in ledger.get("unclassified", [])}
            claimed = {}
            for mm in DELEGATED.finditer(md):
                for pair in mm.group(1).split(","):
                    if ":" not in pair:
                        continue
                    ln, cls = pair.split(":", 1)
                    try:
                        claimed[int(ln.strip())] = cls.strip().upper()
                    except ValueError:
                        errs.append(f"delegated entry {pair.strip()!r} is not "
                                    "<line>:<CLASS>")

            recomputed = lc.get("published", p)
            rec_internal = lc.get("internal", n)
            rec_suppressed = lc.get("suppressed", s)
            for ln, cls in sorted(claimed.items()):
                if ln not in allowed:
                    errs.append(
                        f"line {ln} is declared re-classified, but the "
                        "classifier did not delegate it - a settled "
                        "classification may not be overridden")
                    continue
                if cls not in CLASSES:
                    errs.append(f"line {ln} re-classified as {cls!r}, which is "
                                f"not one of {', '.join(sorted(CLASSES))}")
                    continue
                was, now = allowed[ln], cls
                recomputed += ((now in PUBLISHED) - (was in PUBLISHED))
                rec_internal += ((now == "INTERNAL") - (was == "INTERNAL"))
                rec_suppressed += ((now == "NOISE") - (was == "NOISE"))

            # Every bucket is checked, not just `published`. Only these two were
            # verified before, so a net-zero swap - drop a settled FEATURE,
            # publish a settled NOISE line - kept the published total intact and
            # passed while a shipped feature went unannounced.
            for label, declared, computed in (("internal", n, rec_internal),
                                              ("suppressed", s, rec_suppressed)):
                if declared != computed:
                    errs.append(
                        f"declared {label}={declared} but the classifier and "
                        f"your declared re-classifications give {computed}")
            if p != recomputed:
                errs.append(
                    f"declared published={p} but the classifier saw "
                    f"{lc.get('published')} and the re-classifications you "
                    f"declared give {recomputed}. Every change to the total "
                    "must be a delegated line, named in `delegated=`.")
            # duplicates comes from the classifier, never from the prose: the
            # model writing its own `duplicates=` could delete a feature with no
            # slack at all.
            expected = recomputed - lc.get("duplicates_published", 0)
            if dups and dups != lc.get("duplicates_published", 0):
                errs.append(f"declared duplicates={dups} but the classifier "
                            f"found {lc.get('duplicates_published', 0)}")

        # WHICH items were published, not merely how many.
        if ledger and ledger.get("items"):
            cls_by_line = {it["line"]: it["class"] for it in ledger["items"]}
            dup_lines = {it["line"] for it in ledger["items"]
                         if it.get("duplicate_of_line")
                         and it["class"] in PUBLISHED
                         and cls_by_line.get(it["duplicate_of_line"]) in PUBLISHED}
            for ln, cls in claimed.items():
                if ln in cls_by_line:
                    cls_by_line[ln] = cls
            should = {ln for ln, c in cls_by_line.items()
                      if c in PUBLISHED} - dup_lines

            body_cs = customer_section(md)
            titles = published_entries(body_cs)
            attributed = {int(m.group("line")): m.group("title")
                          for m in ENTRY_SRC.finditer(body_cs)}
            if len(attributed) != len(titles):
                errs.append(
                    f"{len(titles)} published bullet(s) but {len(attributed)} "
                    "carry a `<!-- src:N -->` attribution. Every entry must name "
                    "the input line it reports, or it cannot be checked against "
                    "the classification.")
            for ln in sorted(set(attributed) - should):
                errs.append(
                    f"line {ln} is published as \"{attributed[ln]}\" but it is "
                    f"{cls_by_line.get(ln, 'not an item')} - only publishable "
                    "items may appear in the customer-facing sections")
            for ln in sorted(should - set(attributed)):
                errs.append(
                    f"MISSING FEATURE: line {ln} ({cls_by_line.get(ln)}) is "
                    "publishable and no entry reports it - it was dropped")

        # The arithmetic check, kept as a cheap backstop.
        entries = published_entries(customer_section(md))
        if len(entries) > expected:
            errs.append(f"{len(entries)} published entries but only {expected} "
                        "expected - an entry was invented")
        elif len(entries) < expected:
            errs.append(f"MISSING FEATURES: {expected} publishable item(s) but "
                        f"only {len(entries)} entr"
                        f"{'y is' if len(entries) == 1 else 'ies are'} present "
                        "in the customer-facing sections")

    body = customer_section(md)
    ledger_keys = ticket_keys_from_ledger(ledger)
    for key in ledger_keys:
        if re.search(rf"\b{re.escape(key)}\b", body):
            errs.append(f"ticket key leaked into customer-facing text: {key!r} "
                        "(it appears in the input log)")
    # Keys the ledger has never heard of still leak. Reading the ledger made
    # the check exact and therefore blind to `(tracked as ACME-4521)`, which
    # passed with `no internal tokens leaked` printed over it.
    for key in ticket_keys_in(body):
        if key not in ledger_keys:
            errs.append(f"ticket key leaked into customer-facing text: "
                        f"{key!r} (ticket-shaped; not from this release's log)")
    for pat, label in STRUCTURAL_LEAKS:
        for hit in sorted({h if isinstance(h, str) else h[0]
                           for h in pat.findall(body)}):
            errs.append(f"{label} leaked into customer-facing text: {hit!r}")
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", body, re.I):
            errs.append(f"internal name leaked into customer-facing text: "
                        f"{term!r} (L3 translation table)")

    heads = re.findall(r"^##\s+\*{0,2}(New|Improved|Fixed)\*{0,2}\s*$", body, re.M)
    if heads != [h for h in ["New", "Improved", "Fixed"] if h in heads]:
        errs.append("sections out of contract order (New / Improved / Fixed)")

    items = published_entries(body)
    dupes = sorted({x for x in items if items.count(x) > 1})
    if dupes:
        errs.append(f"item appears in more than one section: {dupes}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("notes")
    ap.add_argument("--ledger", help="classify.py --json output")
    ap.add_argument("--context", default=str(pathlib.Path(__file__).parent.parent
                                             / "context"))
    a = ap.parse_args()

    try:
        md = open(a.notes, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"usage: cannot read {a.notes}: {e}", file=sys.stderr)
        return 2
    ledger = None
    if a.ledger:
        try:
            ledger = json.load(open(a.ledger, encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"usage: cannot read --ledger {a.ledger}: {e}", file=sys.stderr)
            return 2

    errs = validate(md, ledger, pathlib.Path(a.context))
    hard = [e for e in errs if not e.startswith("WARNING:")]
    if hard:
        print(f"FAIL ({len(hard)} violation(s))")
        for e in errs:
            print(f"  - {e}")
        return 1
    for e in errs:
        print(f"  - {e}")
    # Without the classifier's ledger this cannot check what was published
    # against what was classified — it can only read the numbers the notes
    # assert about themselves. Saying "ledger reconciles" there was a false
    # reassurance: notes hiding five features printed it and exited 0.
    if ledger:
        print("PASS - ledger reconciles against the classifier, every "
              "publishable item is present, no internal tokens leaked")
    else:
        print("PASS - self-consistent and no internal tokens leaked. "
              "NOT CHECKED: whether anything was dropped. Re-run with "
              "--ledger <classify.py --json> to verify the zero-loss guarantee.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
