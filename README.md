# Three Agents — Phase 2: The Agentic Shift

**Visma Tech Portugal · AI Program 2026**

Three independent, production-shaped agents, built on one reusable framework.
Each can be pulled down on its own. All three can be chained. Neither fact
depends on the other.

| Agent | Trial | What it does |
|---|---|---|
| [`release-archivist/`](release-archivist/SKILL.md) | 1 — The Archivist | Messy git log + Jira export → client-ready changelog |
| [`jira-scribe/`](jira-scribe/SKILL.md) | 2 — The System Scribe | Brain dump or transcript → Ready-for-Dev story |
| [`code-sentinel/`](code-sentinel/SKILL.md) | 3 — The Code Sentinel | Diff → cited, project-calibrated review |

Read first: **[AGENT-FRAMEWORK.md](AGENT-FRAMEWORK.md)** (the architecture),
then **[INTERCHANGE.md](INTERCHANGE.md)** (how they compose without coupling),
then **[scenario/SCENARIO.md](scenario/SCENARIO.md)** (the end-to-end test).

---

## Run it

```bash
python scenario/run_scenario.py            # composition + independence
python code-sentinel/scripts/load_rules.py # show the active rule set
```

---

## The three claims, and how each is proved

### 1. These are agents, not prompts

Every deterministic step is code. The model is left only with judgment.

| Agent | Deterministic (script) | Judgment (model) |
|---|---|---|
| Archivist | Noise filter, classification, coverage ledger | Customer wording, ambiguous items only |
| Scribe | Filler stripping, field extraction, contract validation | Acceptance criteria, edge-case forecasting |
| Sentinel | Diff parsing, rule loading, citation enforcement | Is this a defect or the design? |

Determinism is therefore architectural. We do not ask the model to be consistent;
we remove the places where it could be inconsistent.

```
$ for i in 1 2 3; do python release-archivist/scripts/classify.py sprint42.log | md5sum; done
a29a6d175ebe356817d89a562d9bb1d3
a29a6d175ebe356817d89a562d9bb1d3
a29a6d175ebe356817d89a562d9bb1d3
```

### 2. They are independent

```
=== INDEPENDENCE TEST — the other two agents are DELETED ===
  [OK ] jira-scribe         ran with code-sentinel, release-archivist removed
  [OK ] code-sentinel       ran with jira-scribe, release-archivist removed
  [OK ] release-archivist   ran with jira-scribe, code-sentinel removed
```

The runner physically copies each agent into an empty tree and runs it there.
No agent imports another. The only shared thing is a **data convention**, and
conformance to it is checked by each agent's own validator.

### 3. They can be calibrated to a project

The reason generic review bots get muted: they flag your architecture as a bug.
Fixed with three context layers and one hard rule.

**No finding without a citation.** If no loaded rule covers a concern, the agent
may not raise it. It has no free-floating opinions.

```
$ python code-sentinel/scripts/load_rules.py --path legacy/billing/InvoiceController.cs
For legacy/billing/InvoiceController.cs: L3-ARCH-01 (via DEV-004)

$ python code-sentinel/scripts/load_rules.py --path src/onboarding/Saga.cs
For src/onboarding/Saga.cs: no suppressions
  ! DEV-006 expired on 2026-06 - suppression no longer applied
```

Deviations carry an owner and an expiry, so the registry cannot rot into a list
of excuses. When one expires, the agent starts flagging again on its own.

And the citation rule is enforced by code, not by hope:

```
$ python code-sentinel/scripts/validate_findings.py bad-review.md
FAIL (6 violation(s))
  - [BLOCKER] Controller talks straight to the repository: L3-ARCH-01 is
    SUPPRESSED on legacy/billing/InvoiceController.cs by DEV-004 - this is a
    false positive the project context already ruled out
  - [CRITICAL] This method is too long...: invalid severity
  - [CRITICAL] This method is too long...: NO RULE CITED
  - [CRITICAL] This method is too long...: style/formatting comment - the linter owns this
  - [MAJOR] New endpoint has no idempotency key: cites L3-ARCH-04 which is DRAFT/dormant
  - coverage does not reconcile: 9 + 1 != 12
```

---

## Eval Log

Per-agent eval logs live at the bottom of each `SKILL.md`, as the brief requires.
This is the combined view.

Corpus: real sprint artefacts from `service-alpha`, anonymised with a fixed
substitution map (service names → `service-alpha`, people → first names,
tickets → `PROJ-`). Mess deliberately preserved: typos, mixed PT/EN, filler,
mid-sentence reversals, duplicate ticket keys. Date: 2026-08-06.

| # | Agent | Input | Runs | Structural variance | Decision variance | Coverage | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | Archivist | 15-line sprint log: merges, reverts, WIP, dup keys, PT/EN | 3 | None | None — md5-identical | 15/15 | PASS |
| 2 | Sentinel | 3-file diff incl. generated file + suppressed path | 3 | None | None — 2 reviewable, 1 skipped | 3/3 | PASS |
| 3 | Scribe | 12-turn refinement transcript, one mid-sentence reversal | 3 | None | None — actor found, action/outcome MISSING | n/a | PASS |
| 4 | Sentinel | Adversarial: hand-written review with 6 planted violations | 3 | None | None — 6/6 caught | — | PASS |
| 5 | Sentinel | Expired-deviation case (`src/onboarding`) | 3 | None | None — suppression correctly *not* applied | — | PASS |
| 6 | Sentinel | Adversarial: APPROVE verdict with a BLOCKER present | 3 | None | None — contradiction caught | — | PASS |
| 7 | Sentinel | Valid review (must NOT be rejected) | 3 | None | None — no false positives | — | PASS |
| 8 | Archivist | Adversarial: all-noise log, zero publishable | 3 | None | None — empty-release notice | 5/5 | PASS |
| 9 | Archivist | Leaky notes: hash + ticket key + internal name | 3 | None | None — 4/4 leaks caught | — | PASS |
| 10 | Scribe | Valid story (must NOT be rejected) | 3 | None | None — no false positives | — | PASS |

Run them yourself: `python <agent>/scripts/run_evals.py` in any agent folder.
Each case is executed 3 times and the output md5 compared.

### Deltas found and fixed during evaluation

Reported rather than hidden, because the fixes are the evidence that the harness works.

1. **`add regression test` classified FEATURE.** Rule R-11 matched the verb "add"
   before any test rule existed. Added R-09b ahead of the FEATURE rules. Re-ran:
   stable across 3 further runs. *(This is exactly the false positive the coverage
   ledger is designed to surface — it reconciled, but into the wrong bucket.)*
2. **`src/generated/` not skipped.** The skip pattern only matched
   `*.generated.ts`, not a `generated/` directory. Sentinel was reviewing a
   generated API client. Fixed; reviewable went 3 → 2.
3. **Scribe found no actor in natural speech.** Real people say "bookkeepers can
   post entries", not "as a bookkeeper I want to". The parser now falls back to the
   **L3 actor glossary** — the fix is itself a demonstration of why the context
   layer exists, since only project context knows `bookkeeper` is an actor here.
4. **The runner contradicted the framework.** It scored `insufficient_input` as a
   failure, when the convention says a correct refusal is a *successful* run.
   Fixed in the runner, not in the agent.

A second sweep, exercising every script on success, failure, empty and piped
inputs, found four more — including the most dangerous bug in the codebase:

5. **Silent no-op with no context.** With `context/` absent, `load_rules` reported
   mode `L2-only` while loading **zero** rules. The Sentinel would then review
   nothing, find nothing, and return a clean result — telling a team their code
   was checked when it was not. A green result nobody investigates is worse than
   a crash. Now reports `NO-CONTEXT`, warns `FATAL`, exits 3, and the agent is
   instructed to refuse to emit a verdict.
6. **No verdict/finding consistency check.** A review could declare `APPROVE`
   while carrying a BLOCKER — the same class of bug as READY-with-MISSING, which
   was already guarded in the Scribe but never in the Sentinel. Now caught.
7. **Config errors blamed on the findings.** With an empty rule set, every finding
   was reported as "cites a rule not in the loaded set", burying the real cause.
   Now fails once, as a `CONFIG` error.
8. **`run_evals.py` did not exist.** `INTERCHANGE.md` documented the independence
   test as invoking it. The documentation described a script nobody had written.
   Now present in all three agents, and it is what the independence test runs.

A third pass — auditing every file path referenced in the docs, and generating the
golden sets — found the last three:

9.  **Wrong actor picked silently.** The Scribe's glossary fallback took the first
    L3 actor appearing in the text. Given *"accountants yes, bookkeepers no"* it
    chose `accountant`, inverting the whole story. Surfacing the ambiguity beat
    resolving it: the agent now reports `actor_ambiguous` and asks. Found only
    because the golden set records the *decision*, not the prose.
10. **`<agent>/references/output-contract.md` did not exist** in any agent, though two
    documents cited it as normative. Same failure as `run_evals.py`: documentation
    describing files nobody wrote.
11. **No Eval Log in any `SKILL.md`.** The brief requires it *at the bottom of the
    markdown file*. It existed only in this README — which is not what gets
    submitted. This one would have cost the passport stamp outright.

Every one of these was found by testing paths that had never been executed —
`jira-scribe/validate_output.py` had never been run once. Exit codes alone were
not enough: several scripts returned the right code for the wrong reason.

### Failure modes verified

- Scribe on the transcript: reports `MISSING: action, outcome` and refuses to
  invent the forbidden-post behaviour the meeting never decided. **This is the
  point of the agent** — a story that guessed here would have shipped the wrong
  error handling.
- Sentinel on `legacy/billing`: silent on `L3-ARCH-01`, and says so in
  *Suppressed by Project Context*, while still flagging the real defect
  (client-side-only authorisation, `L2-SEC-05`).
- Archivist on an all-noise log: emits the "no customer-facing changes" notice
  rather than manufacturing content.

---

## Adopting this on your project

```bash
cp -r code-sentinel/ your-repo/.agents/
python code-sentinel/scripts/bootstrap_context.py your-repo   # drafts L3
# tech lead ratifies L3-project.md — the agent cannot ratify its own context
# shadow-run one sprint, tag findings useful / noise / missed
# feed tags back into L3, re-run the golden set
# promote to required check once precision >= 80%
```

Full protocol in [AGENT-FRAMEWORK.md §4](AGENT-FRAMEWORK.md).
