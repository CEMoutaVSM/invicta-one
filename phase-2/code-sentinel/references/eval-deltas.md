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
14. **A published example key demanded a finding.** AWS documents
    `AKIAIOSFODNN7EXAMPLE` on its own site, and a negative test asserting a
    malformed key is rejected legitimately contains a `PRIVATE KEY` header. The
    scanner demanded an `L2-SEC-01` for both, so an honest reviewer could not
    pass without inventing a finding about something that was not a defect.
    Example-shaped tokens are advisory now, never a demand.
15. **A live credential inside a URL was invisible.** Comments were stripped by a
    regex that read the `//` in
    `"postgres://admin:prod-sk-...@db.internal"` as the start of a comment and
    deleted the credential with the rest of the line. It reached neither the
    demand list nor the advisory one. Comments are now stripped by a scanner
    that knows what a string literal is.
16. **Quoting the PR was treated as smuggling.** The check that stops a severity
    hiding in a table cell or a blockquote matched the marker anywhere in the
    row, so a review quoting `> This is a [BLOCKER] for the August release` —
    the PR description, a documented input — was rejected. A smuggled finding
    leads its cell; a quotation mentions it in passing. The check now requires
    that position, and still catches the disguise.
17. **The quoted URL was fixed and the unquoted one was not.** A `.env`, YAML
    or Dockerfile line `DATABASE_URL=postgres://admin:KEY@db.internal` still
    lost its credential to the `//` of the scheme, reaching neither the demand
    list nor the advisory one. A `//` preceded by `:` is a scheme.
18. **Incidental digit runs demoted real keys.** `EXAMPLE_TOKEN` matched
    `0000000`, `AAAAAAAA`, `1234567890` and `deadbeef` anywhere in a token, so a
    genuine `sk_live_00000004Qh8xZ2mPqRsTuVwX` became a judgement call instead
    of a demand. Only a word that says it is an example survives.
19. **A bare PEM header in `docs/` forced a finding.** The "a header with no key
    material is not a key" downgrade was gated on the file being a test, so any
    README showing the format demanded an `L2-SEC-01`.
20. **An emphasised severity escaped every check.** `One aside: **[BLOCKER]**
    the auth check can be bypassed` mid-paragraph, and the same in `<b>` tags,
    passed while reading to a human as exactly what they are. Position cannot
    separate the reviewer's voice from quoted input; emphasis can. Blockquotes
    are now read as input - quoting the PR is legitimate - and an emphasised
    severity is a finding wherever it appears.
21. **The recall claim was not in the scored artefact.** "A review that misses a
    proven defect is a failed review" was asserted in `SKILL.md` and tested only
    in `audit/regressions.py`. Two Eval Log cases now carry it: the same blind
    `APPROVE` passes without `--diff` and fails with it.
22. **Every real private key in production source was demoted to advisory.** My
    own fix from the previous round: removing the "only in a test file"
    condition from the bare-header downgrade was right for `docs/format.md` and
    catastrophic for source, because a real PEM key puts `-----BEGIN ... KEY-----`
    on one line and its base64 body on the NEXT. Testing the header's own line
    demoted the genuine article every time, and a blind `APPROVE` passed
    `--diff`. The header is now judged against the file's whole added text.
23. **Obvious filler forced a fabricated finding.** Narrowing the example test
    to words meant `AKIA0000000000000000` and `sk_live_deadbeefdead` DEMANDED an
    `L2-SEC-01`. A credential's body is high-entropy; filler is a couple of
    characters repeated, or a hex word.
24. **The severity rule was half a convention, three times running.** Anchoring
    to the start of a line let `One aside: [BLOCKER] the auth check can be
    bypassed` pass mid-paragraph; requiring emphasis let the plain form pass and
    exempted blockquotes so completely that `> **[BLOCKER]**` hid inside one.
    Each fix closed one hole and opened another because none of them said what a
    blockquote MEANS. One sentence now does, in `severity_claims` and in §7:
    *inside a blockquote or a fence, text is quoted input; everywhere else a
    bracketed severity is the reviewer's own claim; and emphasising someone
    else's words makes them yours.*
