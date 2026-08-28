# Eval deltas — code-sentinel

Every defect the harness or an auditor found in this agent, and what
changed because of it. Kept out of `SKILL.md` so the file the model
loads on every run carries instructions rather than history.

**Deltas found and fixed.**

1. **Silent no-op.** With `context/` absent, the loader reported mode `L2-only`
   while loading zero rules: the agent would review nothing, find nothing, and
   return a clean result. Now `NO-CONTEXT`, `FATAL`, exit 3 (case 4).
2. **The same failure, one layer down.** A context file that *existed* but parsed
   to zero rows — a missing trailing pipe was enough — silently dropped all 12 org
   security rules with `usable=True` and no warning. An unparseable context is now
   a CONFIG error, not a smaller rule set.
3. **Draft rules were only dormant if spelled exactly `draft`.** `draft (pending
   ADR-012)`, `not-ratified` and `DRAFT — do not use` all loaded as **active**,
   and findings citing them validated clean. Any provisional wording is now
   dormant, and an unrecognised status fails safe to dormant.
4. **A deviation nobody could read still silenced a rule.** `Expires: TBD`, a
   blank expiry or `2027-6` left the suppression active forever. A deviation is
   only honoured when its expiry and target both parse.
5. **Suppression depended on path shape.** `fnmatch` is case-insensitive on
   Windows and case-sensitive elsewhere, and `a/src/…` — the form a git diff
   actually emits — matched nothing. Paths are normalised and matched
   case-sensitively on every platform.
6. **The refusal marker was a skeleton key.** Any review containing
   `Status: insufficient_input` skipped every check: a document with `APPROVE`,
   three BLOCKERs, severity `CATASTROPHIC`, an invented rule ID and a suppressed
   path passed clean (case 9).
7. **`####` made a finding invisible.** Findings were matched at `###` exactly, so
   one extra `#` removed a finding from validation entirely. Any heading depth is
   now parsed, and finding-shaped bold text is rejected rather than ignored.
8. **`**Verdict:** Approve`** passed a check keyed on uppercase `APPROVE`.
9. **A mixed-format diff parsed as one file.** Keying only on `diff --git` meant
   the second file — carrying a hardcoded production key and a concatenated SQL
   query — was invisible, and the coverage count reported that with confidence
   (case 2).
10. **The coverage invariant was satisfiable by a lie.** Four findings across four
    files while claiming `Reviewed: 0` still summed correctly. Distinct finding
    paths are now checked against the reviewed count and against the diff.
11. **A comment counted as a branch.** `// … hidden button for bookkeepers`
    matched on the word *for*, inflating the test expectation with control flow
    that does not exist. Comments are stripped before branch detection; the golden
    moved 2 → 1 deliberately.
12. **`src/generated/` was not skipped** — only `*.generated.ts` matched. The
    agent was reviewing a generated API client. Reviewable went 3 → 2.
13. **The golden files were read by no code.** `evals/golden/` existed and nothing
    compared against it, so the suite was green while a rule change could alter
    every decision unnoticed. `run_evals.py` now diffs against golden field by
    field, and `audit/run_audit.py` corrupts a golden on a copy to prove the gate
    bites.
