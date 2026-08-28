# Eval deltas — release-archivist

Every defect the harness or an auditor found in this agent, and what
changed because of it. Kept out of `SKILL.md` so the file the model
loads on every run carries instructions rather than history.

**Deltas found and fixed.**

1. **`add regression test for session timeout` classified `FEATURE`.** Rule R-11
   matched the verb *add* before any test rule existed. The ledger still
   reconciled — the item went into the *wrong bucket*, not into nothing — which is
   exactly the error a coverage count alone cannot catch. Added R-09b.
2. **The zero-loss guarantee was a tautology.** Fuzzing 40,000 inputs produced
   zero failures, because the identity checked was true by construction. See
   above: the ledger now reconciles against the raw line count.
3. **Six shipped features vanished into NOISE.** Token heuristics ran ahead of
   conventional-commit prefixes, so `feat: add dashboard widget` was classified
   INTERNAL on the word *dashboard* — silently, with no low-confidence flag.
   `feat:` / `fix:` / `chore:` / `refactor:` now win first, and anything buried by
   a token rule while carrying a capability verb is flagged for human judgment.
4. **Jira CSV rows were not items at all.** A row with no spaces failed the
   two-word test and was dropped before classification: six shipped items reported
   as `in=3 … reconciles=YES`. Lines are now counted first and classified second,
   and a line carrying a ticket key is always an item.
5. **The refusal marker was a skeleton key.** Any document containing
   `Status: insufficient_input` skipped every check including leak detection, so
   notes leaking a commit hash and a ticket key passed clean.
6. **`<!-- INTERNAL` on line 1 emptied the customer section.** `customer_section`
   splits on the marker and takes the first part; with the marker first, every
   leak check silently inspected an empty string.
7. **The leak list was a hardcoded copy of L3.** Nine internal names were
   duplicated from the translation table in `context/L3-project.md`, guaranteed to
   drift the first time L3 grew. The validator reads the table directly.
8. **Two validators were non-deterministic.** Leak findings were emitted from an
   unordered set: twelve runs produced twelve different outputs. Sorted.
9. **`classify.py --json` returned 0 on a broken ledger**, so a pipeline could
   consume a lossy classification and never know.
10. **The Eval Log described a fixture that did not exist.** Row 3 claimed a
    leaky-notes input with "4/4 caught"; the third input was a clean file. The
    fixture now exists and is case 6.
11. **A ticket key leaked with a clean bill of health.** Reading keys from the
    classifier ledger made the check exact and therefore blind: `(tracked as
    ACME-4521)` is plainly a ticket key, was not in this release's log, and
    printed `no internal tokens leaked`. Silence would have been better than a
    false all-clear. Shape detection is back alongside the ledger, without the
    part that made it wrong — `SLA-95` is a service level and `US-2026` a year.
12. **A revert of a revert shipped a feature to nobody.** R-02 called it "net
    zero", which is backwards: reverting a revert re-applies the change. The
    flagship demo log ships `draft invoice autosave` that way; it was filed
    NOISE, accounted for, suppressed, never mentioned, and every check stayed
    green — the zero-loss guarantee reduced to line accounting. It is now
    classified from the subject it restores and handed to the model, because
    whether it is new *to customers* is not something the log can settle.
13. **Shape alone was wrong in both directions.** `PROJ-1234567` leaked (the
    digit bound was too tight) while `RS-232 serial devices`, `RJ-45` and
    `RTX-4090` in genuine release prose were rejected as leaked ticket keys -
    and a validator that rejects correct notes is switched off as fast as one
    that misses leaks. A pasted key arrives announced (`tracked as ACME-4521`);
    a standard is a noun phrase. Ledger keys remain exact and unconditional.
14. **A malformed double revert invented a feature.** `Revert "Revert ""` names
    nothing, fell through to the whole-line fallback, and was filed FEATURE -
    after which the validator demanded a customer entry for it, extracting an
    invented note from a garbage line.
