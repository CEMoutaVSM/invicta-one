#!/usr/bin/env python3
"""Deterministic pre-processing for the Jira Scribe.

Does the mechanical work so the model only does judgment:
strips transcript filler, segments the text, extracts candidate
actors/actions/outcomes, and reports what is missing.

No LLM. Same input -> byte-identical output, always.

Usage:  python parse_input.py <file>            # or stdin
Output: JSON on stdout
"""
import json
import pathlib
import re
import sys
import signal
try:  # do not traceback when piped into head/less
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):  # non-POSIX
    pass


# Filler removed from transcripts before analysis. PT + EN.
FILLER = re.compile(
    r"\b(uh+|um+|erm+|hmm+|like|you know|i mean|sort of|kind of|basically|"
    r"pronto|tipo|entao|então|ok ok|right right|yeah yeah|so so)\b",
    re.IGNORECASE,
)
SPEAKER = re.compile(r"^\s*(?:\[[\d:]+\]\s*)?([A-Z][\w .'-]{1,30}):\s*", re.MULTILINE)

# Candidate actor phrases. Deliberately conservative - a miss is safe
# (the model is told to emit MISSING), a false positive is not.
ACTOR_PAT = re.compile(
    r"\b(?:as an?|enquanto|the|a)\s+"
    r"(user|customer|admin|administrator|accountant|bookkeeper|manager|"
    r"developer|auditor|client|utilizador|cliente|contabilista|gestor)\b",
    re.IGNORECASE,
)
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
SPLIT_PAT = re.compile(r"\b(also,|and separately|another thing|besides that|"
                       r"outra coisa|além disso)\b", re.IGNORECASE)

NUMERIC = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|days?|hours?|mins?|minutes?|"
                     r"seconds?|EUR|USD|MB|GB|items?|rows?)\b", re.IGNORECASE)


def strip_transcript(text: str) -> tuple[str, list[str]]:
    speakers = sorted(set(m.group(1) for m in SPEAKER.finditer(text)))
    text = SPEAKER.sub("", text)
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
    candidates = [r for r in glossary
                  if re.search(rf"\b{re.escape(r)}s?\b", clean, re.I)]
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
        # Every number in the input, so the model can be checked against
        # inventing thresholds that were never stated.
        "actor_source": ("explicit" if first(ACTOR_PAT, clean)
                         else "L3-glossary" if actor
                         else "ambiguous" if ambiguous else None),
        # Computed on cleaned text so transcript timestamps are not mistaken
        # for values the speaker actually stated.
        "stated_values": sorted(set(NUMERIC.findall(clean))) or [],
        "numeric_literals": sorted(set(re.findall(r"\b\d+(?:[.,]\d+)?\b", clean))),
        "segments": segments,
    }


def main() -> int:
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    ctx = pathlib.Path(__file__).parent.parent / "context"
    json.dump(analyse(raw, ctx), sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
