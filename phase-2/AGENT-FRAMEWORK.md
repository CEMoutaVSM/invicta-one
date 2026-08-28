# The Agent Framework
### A reusable architecture for building, calibrating and testing production agents
*Visma Tech Portugal — AI Program 2026, Phase 2: The Agentic Shift*

---

## 0. Thesis

> A prompt asks a model to do a thing.
> An **agent** is a system that does the thing the same way every time, knows what it is not allowed to do, and can be taught the specifics of your project without being rewritten.

Phase 2 asks for `SKILL.md` files. This framework treats each one as the entry point to an agent, not as a document. Three agents are built on it — the Archivist, the Scribe, the Sentinel — but the framework is the deliverable that outlives them.

---

## 1. Skill vs. Agent

| | Skill (a prompt in a file) | Agent (this framework) |
|---|---|---|
| Logic | Described in prose, re-derived every run | Deterministic work in `scripts/`, judgment in the model |
| Consistency | Hoped for | Enforced by an output validator |
| Bad input | Guesses | Declared failure mode, refuses to invent |
| Project fit | One-size-fits-all | Three-layer context, calibrated per repo |
| Improvement | Someone edits the prompt | Feedback loop writes to project context |
| Proof it works | "It looked good" | Golden set + regression + precision metrics |

**The move that matters:** anything a script can do deterministically must not be done by the model. Parsing, classifying by pattern, counting, schema validation, coverage accounting — all of that goes to code. The model is reserved for genuine judgment: *is this change user-visible? is this acceptance criterion testable? is this a logical fallacy or an intentional design?*

Determinism then stops being a promise about model behaviour and becomes a property of the architecture: you shrink the surface where variance can occur.

---

## 2. Anatomy

```
<agent-name>/
├── SKILL.md                    # Entry point: identity, routing, contracts
│                               # The Eval Log lives at the BOTTOM of this file
├── scripts/                    # Deterministic work only. No LLM call in here.
│   ├── <parser>.py             # Messy input → normalised envelope
│   └── <validator>.py          # Output must satisfy the contract or fail loudly
├── references/
│   └── output-contract.md      # Exact schema, section order, enums
├── context/                    # ← THE CALIBRATION LAYER
│   ├── L2-org-standards.md     # Visma-wide, shared across all projects
│   ├── L3-project.md           # This repo: architecture, glossary, specs
│   │                           # …including the jargon → customer-language table
│   └── L3-known-deviations.md  # "Looks wrong, is intentional" registry
└── evals/
    ├── inputs/                 # Real, anonymised, messy
    ├── golden/                 # Expected decisions (not expected prose)
    └── (run with scripts/run_evals.py, which compares against golden/)
```

The script names are per-agent, because the mechanical work is per-agent:

| Agent | Parser | Validator |
|---|---|---|
| `release-archivist` | `classify.py` | `validate_output.py` |
| `jira-scribe` | `parse_input.py` | `validate_output.py` |
| `code-sentinel` | `parse_diff.py` + `load_rules.py` | `validate_findings.py` |

Two files this tree used to list do not exist and should not:

- **references/translation-table.md** — the jargon-to-customer-language table is
  project vocabulary, so it belongs in the agent's `context/` layer alongside
  the rest of it. A second copy under `references/` is the duplication that made
  the Archivist's leak list drift from L3 in the first place; the validator now
  reads the table out of L3 directly.
- **evals/eval-log.md** — the brief requires the Eval Log *at the bottom of the*
  `SKILL.md`, which is the file that gets submitted. A separate copy is one more
  thing to leave stale.

### SKILL.md skeleton

Every agent uses the same skeleton, in the same order. Sections 1-10 below
are common to all three; an agent adds numbered sections after them when it
has more to say (the Sentinel has a severity taxonomy and a calibration
pointer, for instance). The Eval Log is always last:

```markdown
---
name: <agent-name>
description: <what it does AND when to trigger — be explicit, agents under-trigger>
---

## 1. Identity          The persona and its bias (e.g. "strict QA lead, not a helpful assistant")
## 2. When to use       Trigger conditions and, equally, when NOT to
## 3. Input contract    Accepted formats, tolerated mess, rejected input
## 4. Context loading   Which L2/L3 files to read before reasoning — mandatory step
## 5. Operating rules   Numbered, deterministic. Which step is script, which is judgment
## 6. The Eval Log

Every `SKILL.md` ends with one, and it is generated from the runner rather than
written, so it cannot describe a case the suite does not run. That mattered: an
earlier hand-maintained table claimed three inputs for an agent that shipped two.

Each row records one case and what it asserts:

| # | Case | Runs | Output digest | Golden-gated | Result |
|---|---|---|---|---|---|

Three assertions per case — the expected exit code, byte-identical output across
three runs, and, where a golden file exists, an exact match on the recorded
decisions. Only the third can fail on a logic change; the first two are close to
tautological on a pure function of a fixed file.

**The digests cover the scripts, not the model.** No suite in this repository
invokes an LLM, so nothing here evidences the quality of what the model writes —
only that everything around it is reproducible. `demo/` holds one end-to-end
trace per agent for the rest.

Below the table, each agent summarises the defects found against it and links to
`references/eval-deltas.md` for the full list.

## 7. Constraints       Negative prompting: what it must never do
## 8. Failure mode      What it emits when input is insufficient. Never a guess
## 9. Self-check        Verify own output against §6 before returning
## Eval Log             Evidence
```

Sections 7, 8 and 9 are what separate an agent from a chatbot. Most submissions will not have them.

---

## 3. The three-layer context model

The core problem with any generic engineering agent: **what looks like a defect may be the architecture.** A reviewer that does not know your specs will flag your design decisions as bugs, and a reviewer that cries wolf gets muted — at which point it has negative value.

The fix is to separate the invariant from the contextual.

| Layer | Scope | Owner | Change rate | Example content |
|---|---|---|---|---|
| **L1 Core** | Universal | Framework author | Never | What a review *is*; severity taxonomy; output schema |
| **L2 Org** | All Visma projects | Platform / security | Quarterly | GDPR handling, secret management, auth baseline |
| **L3 Project** | One repo | The owning team | Continuously | Architecture, intentional deviations, glossary, spec links |

L1 ships with the agent and is never edited. L2 is written once and shared. L3 is where each team makes the agent theirs.

### The citation rule

> **No finding without a citation.** Every flag must reference the layer and rule ID it violates (`L2-SEC-03`, `L3-ARCH-07`). If the agent cannot cite a rule, it is not permitted to raise the finding.

This single constraint eliminates most false positives, because it forbids the agent from having free-floating opinions. It also makes every output auditable: a reviewer can check the rule rather than argue with a model.

### The deviation registry

`L3-known-deviations.md` is the pressure valve. When the agent flags something intentional, nobody argues with it — someone adds an entry:

```markdown
### DEV-004 — Direct repository access from controllers in `/legacy/billing`
Status: accepted | Owner: @tech-lead | Reviewed: 2026-Q3
Rationale: Pre-dates the service layer. Migration tracked in PROJ-2841.
Agent behaviour: do not flag L3-ARCH-01 for paths under /legacy/billing.
Expires: 2027-01 (re-evaluate)
```

Entries carry an owner and an expiry so the file does not silently become a list of excuses.

---

## 4. Calibration protocol — how a team trains it on their project

L3 is **generated, then ratified** — never written from a blank page. This is the reusable onboarding path for any team adopting the agent.

**Step 1 — Bootstrap (agent works, ~10 min).**
Point the agent at the repo. It reads the README, ADRs, folder structure, dependency manifest, and the human comments on the last 30–50 merged PRs. It drafts `L3-project.md`, marking every inferred rule with a confidence level and the evidence it inferred it from.

**Step 2 — Ratify (human works, ~20 min).**
A tech lead reviews the draft: confirm, correct, delete. **The agent may not approve its own context.** Unratified rules stay dormant and produce no findings.

**Step 3 — Shadow run (1 sprint).**
The agent posts findings, but as advisory only. Humans mark each one `useful` / `noise` / `missed`. Zero blocking authority during this phase.

**Step 4 — Learn.**
- Every `noise` finding → a deviation entry or a rule correction in L3.
- Every `missed` item that a human raised → a new candidate L3 rule.
- Re-run the golden set after each context change to confirm the fix did not cost a true positive.

**Step 5 — Promote.**
Once precision clears the threshold (see §5), the agent moves from advisory to a required first-pass check.

The loop never closes — L3 is a living file, and its growth is the visible evidence that the agent is being trained rather than merely used.

---

## 5. The harness

### 5.1 Golden sets, not golden text

Never assert on exact prose — LLM wording varies and asserting on it produces a brittle, useless test suite. Assert on **decisions**, which are stable:

| Agent | What the golden file records |
|---|---|
| Archivist | Each input line's classification (`FEATURE`/`FIX`/`IMPROVEMENT`/`INTERNAL`/`NOISE`) + total coverage count |
| Scribe | Fields extracted vs. fields flagged missing; count and structure of acceptance criteria |
| Sentinel | Set of rule IDs fired, with severity, per file |

This is the honest and defensible definition of determinism for an LLM system, and it is a stronger claim than "the output was identical."

### 5.2 The input corpus

Nine real, anonymised, deliberately messy inputs — three per agent. Preserve the mess: typos, half-sentences, mixed Portuguese and English, contradictions, duplicates. Sanitised inputs produce a test suite that proves nothing.

Anonymise mechanically with a fixed substitution map (service names → `service-alpha`, people → `dev-a`, tickets → `PROJ-`, domains → `example.com`). Keep the map local; never commit it.

Every corpus must include at least one **adversarial** case:
- an input that should produce *no* output (all noise / nothing to review),
- an input too vague to process — the agent must invoke its failure mode rather than invent,
- an input containing an intentional deviation already listed in L3 — the agent must stay silent.

That last one is the test that proves calibration works.

### 5.3 Metrics

| Metric | Definition | Target |
|---|---|---|
| **Structural determinism** | Identical section structure and ordering across 3 runs of the same input | 100% |
| **Decision stability** | Identical classifications / rule IDs across 3 runs | ≥ 95% |
| **Coverage** | Input items accounted for (published + explicitly suppressed) | 100% |
| **Precision** | Findings a human accepts ÷ total findings | ≥ 80% |
| **Hallucination rate** | Claims not traceable to input or a cited rule | 0% |
| **Refusal correctness** | Under-specified inputs that trigger the failure mode instead of a guess | 100% |

Coverage is how the Archivist proves "zero missing features": every input line is either published or suppressed with a reason, and the totals must reconcile.

**Precision is the headline metric for the Sentinel**, and it is deliberately weighted above recall. A reviewer that raises ten findings of which three are noise will be switched off; one that raises four solid findings will be trusted. Optimise for trust.

### 5.4 Run protocol

```
for each agent:
  for each of 3 inputs:
    run 3 times and the output compared byte for byte
    diff structure  → must be identical
    diff decisions  → log any delta with an explanation
    validate output against the schema validator
    check every finding carries a rule citation
```

Log the deltas honestly. A framework that reports "2 features worded differently, identical classification" is more credible than one claiming perfection, and it demonstrates that you understand what determinism means in a probabilistic system.

### 5.5 Regression gate

The golden set is a regression suite. Any change to a `SKILL.md`, an L2 standard or an L3 context file re-runs it before merge. This is what makes the agents maintainable rather than a one-off demo — the context can evolve for years without anyone fearing they broke it.

---

## 6. Eval Log format

Appended to the bottom of each `SKILL.md` at submission:

```markdown
## Eval Log

Corpus: anonymised real inputs. 3 runs each, output compared byte for byte.

| # | Input | Runs | Structural variance | Decision variance | Coverage | Verdict |
|---|-------|------|--------------------|--------------------|----------|---------|
| 1 | 47-commit sprint dump, mixed PT/EN | 3 | None | None — 47/47 identical | 47/47 | PASS |
| 2 | Jira export w/ 6 duplicate keys | 3 | None | 1 item FIX↔IMPROVEMENT on run 2 | 31/31 | PASS* |
| 3 | Adversarial: all-noise commit log | 3 | None | None — empty changelog, 12 suppressed | 12/12 | PASS |

*Delta on #2 is a genuine boundary case (a perf fix for a reported bug). Rule R-07
was tightened afterwards; re-run stable across 3 further runs.

Failure mode verified: input #3 returned an explicit "no client-facing changes
this sprint" notice rather than manufacturing content.
```

Reporting a real delta and what you did about it is stronger evidence of engineering than a table of clean passes.

---

## 7. Adoption checklist

For any team taking this framework to a new agent or a new repo:

- [ ] Fork the agent folder; leave L1 untouched
- [ ] Confirm L2 org standards are current
- [ ] Run bootstrap to draft `L3-project.md`
- [ ] Tech lead ratifies L3 — unratified rules stay dormant
- [ ] Build a 3-input golden set from real, anonymised project data
- [ ] Include one adversarial and one known-deviation case
- [ ] Shadow-run for one sprint, tagging findings `useful` / `noise` / `missed`
- [ ] Feed the tags back into L3, re-run the golden set
- [ ] Promote to required check once precision ≥ 80%

---

## 8. What this is really claiming

Phase 2 says the winner builds *"a reliable, production-ready utility script — not a chatbot that requires constant hand-holding."*

A utility script has an interface, a contract, a failure mode, and a test suite. This framework gives an agent all four, and adds the one thing a script cannot have: a way to be taught the specifics of a project without being rewritten.

The three agents are the demonstration. The framework is the deliverable.
