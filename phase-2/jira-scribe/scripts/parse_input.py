#!/usr/bin/env python3
"""Deterministic pre-processing for the Jira Scribe.

Does the mechanical work so the model only does judgment:
strips transcript filler, segments the text, extracts candidate
actors/actions/outcomes, and reports what is missing.

No LLM. Same input -> byte-identical output, always.

Usage:  python parse_input.py <file>            # or stdin
Output: JSON on stdout
Exit:   0 parsed (including a correct refusal) / 2 usage error
"""
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


# Filler removed from transcripts before analysis. PT + EN.
FILLER = re.compile(
    r"\b(uh+|um+|erm+|hmm+|like|you know|i mean|sort of|kind of|basically|"
    r"pronto|tipo|entao|então|ok ok|right right|yeah yeah|so so)\b",
    re.IGNORECASE,
)
# A speaker label is a name, not any run of characters ending in a colon. The
# permissive version consumed up to 31 characters of ordinary prose: "The export
# must complete by 23:59" was read as a speaker called "The export must complete
# by 23", which deleted the stated deadline and then failed the story that
# quoted it as a fabrication.
SPEAKER = re.compile(
    r"^[ \t]*(?:\[[\d:]+\][ \t]*)?"
    r"([A-Z][A-Za-z'’-]{1,20}(?:[ ][A-Z][A-Za-z'’-]{1,20})?)"
    r":[ \t]+", re.MULTILINE)
# Transcript clock stamps only: bracketed, or at the very start of a line where
# a speaker prefix would sit. An unanchored version deleted "02:30" from the
# middle of "finish by 02:30", so the deadline the user actually stated was then
# reported as a figure the story had invented.
TIMESTAMP = re.compile(r"\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]|"
                       r"^[ \t]*\d{1,2}:\d{2}(?::\d{2})?(?=\s)", re.M)

ROLES = (r"user|customer|admin|administrator|accountant|bookkeeper|manager|"
         r"developer|auditor|client|utilizador|cliente|contabilista|gestor")

# Only an unambiguous role-declaring construction counts as explicit.
#
# `the|a` used to be accepted here, which turned any noun phrase containing a
# role word into an actor: "the admin console feels sluggish" was reported as
# `actor: admin, actor_source: explicit`. A UI noun became a user role, and the
# story was then written for the wrong person with full confidence.
ACTOR_PAT = re.compile(rf"\b(?:as an?|enquanto)\s+({ROLES})\b", re.IGNORECASE)

# Words that turn a role noun into a compound noun about a *thing*, not a
# person. "admin console", "customer portal", "user guide".
COMPOUND_HEAD = re.compile(
    r"^\s*(console|panel|page|screen|guide|portal|dashboard|settings|area|"
    r"section|menu|view|tab|url|endpoint|api|docs?|documentation|report|"
    r"interface|ui|form|list|table|field|module|service|team|side)\b", re.I)

OUTCOME_PAT = re.compile(
    r"\b(?:so that|so they can|in order to|para que|para poder|to avoid|to stop)\b\s*([^.!?\n]{5,160})",
    re.IGNORECASE,
)
ACTION_PAT = re.compile(
    r"\b(?:want(?:s)? to|need(?:s)? to|should be able to|must be able to|"
    r"quero|precisa de|deve poder)\b\s*([^.!?\n]{3,160})",
    re.IGNORECASE,
)
# Signals that more than one feature is being described.
# `also,\b` never matched: \b after a comma requires a word character next, and
# what follows a comma is a space. The alternative was dead for every realistic
# input, so "Also, bookkeepers should reopen it" never registered as a second
# feature.
SPLIT_PAT = re.compile(r"\b(?:also|and separately|another thing|besides that|"
                       r"outra coisa|além disso|second(?:ly)?|"
                       r"separate ticket)\b[,:]?", re.IGNORECASE)

# Numbers people say out loud. A story rendering spoken "twenty-four" as 24 was
# reported as a fabrication, because only digits counted as "stated".
WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20",
    "twentyfour": "24", "thirty": "30", "sixty": "60", "ninety": "90",
    "hundred": "100", "thousand": "1000",
}

NUMERIC = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|days?|hours?|mins?|minutes?|"
                     r"seconds?|s|ms|EUR|USD|MB|GB|items?|rows?)\b", re.IGNORECASE)


def strip_transcript(text: str) -> tuple[str, list[str]]:
    speakers = sorted(set(m.group(1) for m in SPEAKER.finditer(text)))
    text = SPEAKER.sub("", text)
    # Any timestamp the speaker pattern did not carry away. Leaving these in
    # let `12` and `04` count as figures the speaker had stated, which is a
    # laundering route for invented thresholds.
    text = TIMESTAMP.sub(" ", text)
    text = FILLER.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), speakers


def segment(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text)]
    return [p for p in parts if len(p.split()) >= 3]


def first(pattern: re.Pattern, text: str, group: int = 1):
    m = pattern.search(text)
    return m.group(group).strip() if m else None


def load_actors(context_dir: pathlib.Path) -> list[str]:
    """Read the actor glossary from L3. Absent L3 -> fall back to generic roles.

    This is why the parser finds an actor in natural speech: real people say
    "bookkeepers can post entries", not "as a bookkeeper I want to". Only the
    project context knows that `bookkeeper` is an actor here.
    """
    f = context_dir / "L3-project.md"
    if not f.exists():
        return []
    return re.findall(r"^\|\s*([a-z][a-z-]{2,20})\s*\|",
                      f.read_text(encoding="utf-8"), re.M)


def role_mentioned(role: str, text: str) -> bool:
    """Is this role named as a person, rather than as part of a thing's name?"""
    for m in re.finditer(rf"\b{re.escape(role)}s?\b", text, re.I):
        if not COMPOUND_HEAD.match(text[m.end():]):
            return True
    return False


def analyse(raw: str, context_dir: pathlib.Path | None = None) -> dict:
    clean, speakers = strip_transcript(raw)
    segments = segment(clean)
    words = len(clean.split())

    actor = first(ACTOR_PAT, clean)
    # Fall back to the L3 actor glossary: bare role mentions in natural speech.
    #
    # Found during golden-set generation: taking the FIRST glossary role that
    # appears picks whatever L3 happens to list first. A transcript saying
    # "accountants yes, bookkeepers no" mentions both, and the wrong one wins.
    # Guessing here is the exact fabrication this agent exists to prevent, so
    # ambiguity is surfaced rather than resolved.
    glossary = load_actors(context_dir) if context_dir else []
    candidates = [r for r in glossary if role_mentioned(r, clean)]
    ambiguous = False
    if not actor:
        if len(candidates) == 1:
            actor = candidates[0]
        elif len(candidates) > 1:
            ambiguous = True   # actor stays unset - the model must ask
    action = first(ACTION_PAT, clean)
    outcome = first(OUTCOME_PAT, clean)

    missing = [k for k, v in
               (("actor", actor), ("action", action), ("outcome", outcome))
               if not v]

    # A reversal late in a transcript overrides an earlier decision.
    reversals = [s for s in segments if re.search(
        r"\b(actually|scratch that|forget|no wait|na verdade|esquece)\b", s, re.I)]

    status = "insufficient_input" if words < 10 or len(missing) == 3 else "ok"

    return {
        "agent": "jira-scribe",
        "version": "1.0",
        "status": status,
        "stats": {"words_in": len(raw.split()), "words_clean": words,
                  "segments": len(segments)},
        "speakers": speakers,
        "candidates": {"actor": actor, "action": action, "outcome": outcome},
        "actor_candidates": candidates,
        "actor_ambiguous": ambiguous,
        "missing_fields": missing,
        "multi_feature": bool(SPLIT_PAT.search(clean)),
        "reversals": reversals,
        "actor_source": ("explicit" if first(ACTOR_PAT, clean)
                         else "L3-glossary" if actor
                         else "ambiguous" if ambiguous else None),
        # Every number in the input, so the model can be checked against
        # inventing thresholds that were never stated. Computed on cleaned text
        # with timestamps removed, so transcript clock values are not mistaken
        # for figures the speaker actually gave.
        "stated_values": sorted(set(NUMERIC.findall(clean))) or [],
        "numeric_literals": sorted(
            set(re.findall(r"\b\d+(?:[.,]\d+)?\b", clean))
            | {v for w, v in WORD_NUMBERS.items()
               if re.search(rf"\b{w}\b", clean.replace("-", ""), re.I)}),
        "segments": segments,
    }


def brief(res: dict) -> dict:
    """The same analysis, reduced to what the model actually has to decide.

    The full envelope repeats the cleaned transcript back as `segments` and
    lists every digit in it — the model already has the input, so that is paid
    for twice. What it cannot work out for itself is which fields are missing,
    whether the actor is ambiguous, and which figures were genuinely stated.
    """
    return {
        "agent": res["agent"],
        "version": res["version"],
        "status": res["status"],
        "candidates": res["candidates"],
        "actor_source": res["actor_source"],
        "actor_candidates": res["actor_candidates"] if res["actor_ambiguous"] else [],
        "actor_ambiguous": res["actor_ambiguous"],
        "missing_fields": res["missing_fields"],
        "multi_feature": res["multi_feature"],
        "reversals": res["reversals"],
        "stated_values": res["stated_values"],
        # Kept deliberately. `validate_output.py --parsed` reads this and
        # nothing else to decide whether a figure was invented, so dropping it
        # to save tokens turned every correctly-quoted number into a
        # fabrication finding.
        "numeric_literals": res["numeric_literals"],
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--brief"]
    want_brief = "--brief" in sys.argv
    try:
        raw = open(args[0], "rb").read() if args else sys.stdin.buffer.read()
    except OSError as e:
        print(f"usage: cannot read {args[0]}: {e}", file=sys.stderr)
        return 2
    text = raw.decode("utf-8", errors="replace")
    ctx = pathlib.Path(__file__).parent.parent / "context"
    res = analyse(text, ctx)
    json.dump(brief(res) if want_brief else res, sys.stdout,
              indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
