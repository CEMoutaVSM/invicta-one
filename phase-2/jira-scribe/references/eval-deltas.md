# Eval deltas — jira-scribe

Every defect the harness or an auditor found in this agent, and what
changed because of it. Kept out of `SKILL.md` so the file the model
loads on every run carries instructions rather than history.

**Deltas found and fixed.**

1. **Wrong actor picked silently.** The glossary fallback took the first L3 actor
   appearing in the text. Given *"accountants yes, bookkeepers no"* it chose
   `accountant`, inverting the story. Now reports `actor_ambiguous` and asks.
2. **A noun became a person.** `ACTOR_PAT` accepted `the|a` before a role word,
   so *"the admin console feels sluggish"* yielded `actor: admin,
   actor_source: explicit`. Only `as a/an` now counts as explicit, and a role
   followed by a compound-noun head (`console`, `portal`, `page`) is not an actor.
3. **The refusal marker was a skeleton key.** Any document containing the string
   `insufficient_input` skipped every contract check — a story could declare
   READY FOR DEV, carry three `MISSING:` markers, name an assignee and omit every
   required section, and pass. A refusal is now a whole-document state, and
   refusing while also delivering is itself a violation.
4. **`**READY FOR DEV**` in bold** slipped past a check anchored on `^READY`.
   Emphasis is stripped before the comparison.
5. **The section-order check could never fire.** It compared the found list
   against itself. It now compares document order against contract order.
6. **False positive on quoted prose.** A story quoting a ticket containing the
   words "assigned to" was rejected as carrying assignee metadata. That check is
   now anchored to a metadata line.
7. **The fabrication guard was built but not installed.** `--parsed` catches
   invented figures and nothing passed it; run as documented, the guard was
   inert. It is now wired into `run_evals.py` (case 6), checks *every* section
   rather than three, and ignores list ordinals.
8. **The suite documented three inputs and shipped two.** Case 3 of the previous
   Eval Log described a fixture that did not exist, and `run_evals.py` printed
   `2/2 passed`. Both the fixture and the happy-path brain dump now exist.
