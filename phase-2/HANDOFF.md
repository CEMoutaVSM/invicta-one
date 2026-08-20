# Handoff to Claude Code

Written at the end of a claude.ai session. Everything below is state you need to
resume without re-deriving it.

---

## 1. The brief (source: `AI Program 2026_Phase2_V1`, Google Drive)

Visma Tech Portugal, AI Program 2026, **Phase 2: The Agentic Shift**. The stated
shift is *from Prompting to Agentic Engineering* — teaching an AI to think and act
like a specialist, not asking it to write something.

**Three trials, one `SKILL.md` each:**

| Trial | Name | Task |
|---|---|---|
| 1 | The Archivist | Messy git commits + Jira logs → filter noise, group by user impact, client-ready changelog. Goal: zero missing features, jargon → business value. |
| 2 | The System Scribe | Brain dump or refinement transcript → full Jira story with Context, Gherkin AC, technical hints. Mindset: strict QA lead refusing vague input. |
| 3 | The Code Sentinel | `.diff` or PR description vs team standards → architectural risk, missing tests. "Negative prompting": *not* style, that's the linter. |

**Submission requirements — all three are scored:**
1. Submit the `SKILL.md` link via the official Google Form.
2. Commit the file to the shared Google Drive folder.
3. **An "Eval Log" at the bottom of the markdown file**, proving at least
   **3 separate messy inputs** with **deterministic outputs**.

**The rubric, quoted from the closing slide:** a winner builds *"a skill that behaves
like a reliable, production-ready utility script — not a chatbot that requires
constant hand-holding."* And: *"Phase 2 isn't about who writes the longest prompt;
it's about software engineering principles applied to natural language."*

**Deadline: today.**

---

## 2. What exists and why

Three agents on one reusable framework. Read in this order:
`AGENT-FRAMEWORK.md` → `INTERCHANGE.md` → `scenario/SCENARIO.md` → any `SKILL.md`.

### The three design decisions worth preserving

**Determinism is architectural.** Everything mechanical lives in `scripts/` — noise
classification, diff parsing, field extraction, contract validation, coverage
accounting. The model is left only genuine judgment. We don't ask the model to be
consistent; we remove the places it could be inconsistent. This is the whole answer
to the brief's "utility script, not a chatbot."

**Three-layer context solves project specificity.** A generic reviewer flags your
architecture as a bug and gets muted within two weeks. So: L1 core (never edited),
L2 org (Visma-wide), L3 project (per repo — architecture, glossary, intentional
deviations). Plus the hard rule: **no finding without a citation.** An agent that can
only speak in rule IDs cannot invent opinions about your design. Deviations carry an
owner and an expiry, so the registry can't rot into a list of excuses — when one
expires the agent resumes flagging by itself.

**Independent but composable.** Coupling is a data convention only; no agent imports
another. Orchestration lives outside, in `scenario/run_scenario.py`. This matters
because the brief asks for a repository any engineer can *pull down* — pulling down
one agent must be enough.

---

## 3. Verified state

All green as of handoff:

```
jira-scribe        2/2 evals passed
code-sentinel      5/5 evals passed
release-archivist  3/3 evals passed
composition        PASS
independence       PASS   (each agent alone in an empty tree)
```

Each eval case runs 3× with output md5-compared. 48 files, 11 scripts, no
dependencies beyond the Python standard library.

---

## 4. Eleven bugs already found and fixed — do not reintroduce

The harness found every one of these; none was caught by reading the code.

| # | Bug | Fix |
|---|---|---|
| 1 | `add regression test` classified FEATURE — verb "add" matched before any test rule | Added R-09b ahead of the FEATURE rules |
| 2 | `src/generated/` not skipped; agent reviewed a generated API client | Directory added to the skip patterns |
| 3 | Scribe found no actor in natural speech ("bookkeepers can post entries") | Falls back to the L3 actor glossary |
| 4 | Runner scored `insufficient_input` as failure, contradicting the convention | Fixed in the runner, not the agent |
| 5 | **Silent no-op**: no `context/` → mode `L2-only` with zero rules → clean review of unchecked code | `NO-CONTEXT` mode, FATAL warning, exit 3, refuse to emit a verdict |
| 6 | `APPROVE` verdict possible alongside a BLOCKER | Verdict/finding consistency check |
| 7 | Empty rule set blamed on each finding, burying the real cause | Single `CONFIG` error |
| 8 | `run_evals.py` documented but never written | Written, per agent |
| 9 | **Wrong actor picked silently**: "accountants yes, bookkeepers no" → chose `accountant`, inverting the story | `actor_ambiguous` — agent asks instead of choosing |
| 10 | `<agent>/references/output-contract.md` cited as normative but absent | Written, per agent |
| 11 | **No Eval Log in any `SKILL.md`** — existed only in README, which isn't submitted | Appended to all three |

Bugs 5, 9 and 11 are the ones worth understanding. #5 is the worst class of failure
(silent success on unchecked code), #9 was caught *only* because golden files record
decisions rather than prose, and #11 would have cost the passport stamp outright.

---

## 5. Pending work, in priority order

### P0 — Compliance audit (this is what the session ended on)

The user asked for a full audit against the brief, run by independent agents. This
was **not completed** — claude.ai has no subagents. In Claude Code it is
straightforward, and the independence is real because each auditor gets a clean
context.

`audit/REQUIREMENTS.md` holds the brief's requirements as testable assertions, and
`audit/run_audit.py` runs the mechanical subset. What is missing is judgment-based
auditing. Suggested invocation:

```
Spawn four independent subagents. Give each ONLY the brief requirements in
audit/REQUIREMENTS.md plus the artefacts — do not tell them what the previous
session concluded, and do not let them see each other's findings.

  Auditor A — compliance: does each SKILL.md satisfy every scored requirement?
              Eval Log present, at the bottom, 3+ messy inputs, determinism claimed
              and evidenced?
  Auditor B — adversarial: try to make each agent fabricate, contradict itself, or
              approve unchecked code. Write new hostile inputs; do not reuse the
              existing fixtures.
  Auditor C — independence: verify no cross-agent coupling by inspection AND by
              deleting folders. Check for hidden coupling via shared filenames,
              copied code, or assumptions about sibling paths.
  Auditor D — rubric: judge against "production-ready utility script, not a chatbot."
              Where would a sceptical staff engineer say this is still a prompt?

Then reconcile: report only findings at least two auditors independently raised, plus
any single finding rated severity BLOCKER. Do not fix anything until I have read it.
```

That last instruction matters — the value is in the disagreement between auditors, and
auto-fixing destroys the evidence.

### P1 — Real data

Fixtures are synthetic-but-realistic. Replacing them with a real anonymised sprint log
would materially strengthen the eval logs. Use a fixed substitution map
(services → `service-alpha`, people → first names, tickets → `PROJ-`,
domains → `example.com`); keep the map local and **never commit it**. Preserve the
mess — typos, mixed PT/EN, contradictions. A sanitised corpus proves nothing.
Regenerate golden sets afterwards and re-read the diffs rather than accepting them.

### P2 — The presentation

Branding: **Visma Tech Portugal**. Suggested arc:

1. Open on the failure, not the solution — a generic bot flagging our own architecture
   as a bug. The three-layer model then answers a problem the room already feels.
2. Live demo, ~2 minutes: `./verify.sh`, then `validate_findings.py` on the adversarial
   review (6 planted violations, 6 caught), then
   `load_rules.py --path src/onboarding/Saga.cs` — no suppression, because `DEV-006`
   expired in June and the agent resumed flagging with no human involved.
3. Close on the bug count. **Eleven bugs in a codebase written to be exemplary, every
   one found by the harness rather than by reading it.** That argues for the framework
   better than any claim that the agents work.

### P3 — Nice to have

- `bootstrap_context.py` is deliberately shallow: it reads README/ADRs/dirs. Reading
  human comments on recent merged PRs via the GitHub API would make L3 drafts far
  better, and is the most valuable remaining feature.
- No CI. A GitHub Action running `verify.sh` on PR would make the regression gate real
  rather than described.

---

## 6. Traps

- **Don't regenerate a golden file to make a test pass.** A golden diff is a finding.
  Bug #9 hid behind exactly that temptation.
- **Don't let an agent learn about its siblings.** It is easy to "helpfully" import
  a shared util. That breaks the independence test and the core claim with it.
- **`insufficient_input` is a pass.** Any new runner or CI step must treat it as
  success, or you will reintroduce bug #4.
- **Resist tidying the prose in `SKILL.md`.** Validators key off specific markers
  (`MISSING:`, `**Rule:**`, `**Verdict:**`, the coverage comment). Re-run evals after
  any edit.
- The `code-sentinel` context contains a deliberately **expired** deviation
  (`DEV-006`). It is not a mistake — it is the demo that the calibration layer has a
  clock. Leave it.
