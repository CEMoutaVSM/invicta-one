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
$ for i in 1 2 3; do python release-archivist/scripts/classify.py release-archivist/evals/inputs/03-sprint42.log | md5sum; done
ab2eca44da29875d7110d1cd2cc26f5d
ab2eca44da29875d7110d1cd2cc26f5d
ab2eca44da29875d7110d1cd2cc26f5d
```

### 2. They are independent

```
=== INDEPENDENCE TEST — the other two agents are DELETED ===
  [OK ] jira-scribe         ran with code-sentinel, release-archivist removed
         6/6 passed
  [OK ] code-sentinel       ran with jira-scribe, release-archivist removed
         10/10 passed
  [OK ] release-archivist   ran with jira-scribe, code-sentinel removed
         7/7 passed
```

The runner physically copies each agent into an empty tree and runs that
agent's **entire** eval suite there. Running one parser script would not be a
test: a tree with every validator, every context file and every golden set
deleted passed the earlier version of this check.
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
This is the combined view: **23 cases over 18 input files**, all green.

Corpus: real sprint artefacts from `service-alpha`, anonymised with a fixed
substitution map (service names to `service-alpha`, people to first names,
tickets to `PROJ-`). Mess deliberately preserved: typos, mixed PT/EN, filler,
mid-sentence reversals, duplicate ticket keys. Date: 2026-08-06.

| Agent | Cases | Golden-gated | Covers |
|---|---|---|---|
| `release-archivist` | 7 | 2 | classification, line-level ledger, leak detection, missing-entry detection, refusal |
| `jira-scribe` | 6 | 2 | transcript refusal, brain-dump happy path, contract validation, fabrication guard |
| `code-sentinel` | 10 | 3 | diff parsing, rule loading, citation rule, recall, suppression, NO-CONTEXT refusal |

Run them yourself: `python <agent>/scripts/run_evals.py` in any agent folder, or
`./verify.sh` for everything.

### What each case actually asserts

Three things, not one: the expected **exit code**, **byte-identical output across
3 runs**, and, where a golden file exists, an **exact match on the recorded
decisions**.

The third is the only one that can fail on a logic change, and it is worth being
blunt about why. `evals/golden/` previously existed and **no code read it**. The
suite was green while any classification rule could be changed freely; sabotaging
two rules altered six decisions and every check still passed. The runners now
diff against golden field by field, and `audit/run_audit.py` corrupts a golden on
a throwaway copy to prove the gate bites.

### Scope of the determinism claim

These suites exercise the **deterministic layer**: the scripts. That is the
design. Every mechanical decision is code, so it cannot vary. The model's
contribution (customer wording, acceptance criteria, judging defect vs design) is
not executed here and is not covered by the md5 comparison. It is constrained
instead by the contracts the validators enforce on whatever the model produces.
Claiming "3 runs, fresh context" for a pipeline that never invokes a model would
assert more than the harness measures.

### Deltas found and fixed

Reported rather than hidden, because the fixes are the evidence that the harness
works. The first eleven were found by the build-time harness. The rest came from
a four-auditor adversarial sweep, each auditor in a clean context, blind to the
others and to this repository's own conclusions.

**Found while building (11).** `add regression test` classified FEATURE;
`src/generated/` not skipped; the Scribe finding no actor in natural speech; the
runner scoring a correct refusal as a failure; the **silent no-op** where a
missing `context/` produced a clean review of unchecked code; `APPROVE` alongside
a BLOCKER; an empty rule set blamed on each finding; `run_evals.py` documented but
never written; the **wrong actor picked silently** from an ambiguous transcript;
`references/output-contract.md` cited as normative but absent; and no Eval Log in
any `SKILL.md`.

**Found by the adversarial sweep (16).** Grouped by root cause:

| # | Defect | Why it mattered |
|---|---|---|
| 1 | **The refusal marker was a skeleton key.** All three validators opened with a substring test for `insufficient_input` and returned early | A review declaring APPROVE with three BLOCKERs, an invented rule ID and a suppressed path passed clean. Same for notes leaking a hash and a ticket key |
| 2 | **The golden sets were read by no code** | The regression gate did not exist. Sabotaging two rules changed six decisions; every suite stayed green |
| 3 | **"Zero missing features" was a tautology** | The buckets partition the items, so the identity could not fail. 40,000 fuzzed inputs, zero failures. Deleting a shipped feature from the notes passed |
| 4 | **Six features silently reclassified as NOISE** | Token heuristics ran ahead of `feat:`, so `feat: add dashboard widget` was buried on the word *dashboard*, unflagged |
| 5 | **Jira CSV rows were never items** | Six shipped items reported as `in=3 ... reconciles=YES` |
| 6 | **An unparseable context loaded zero rules and reported `usable`** | A missing trailing pipe dropped all 12 org security rules with no warning: the silent no-op again, one layer down |
| 7 | **Draft rules were dormant only if spelled exactly `draft`** | `draft (pending ADR-012)` and `not-ratified` loaded as active and validated findings clean |
| 8 | **An unreadable expiry suppressed forever** | `Expires: TBD` kept a deviation alive past any date, rejecting a real SQL-injection BLOCKER as a false positive |
| 9 | **Suppression depended on path shape** | `a/src/...`, the form a git diff actually emits, matched nothing; `fnmatch` also made matching case-sensitive on Linux and not on Windows |
| 10 | **`####` made a finding invisible**, and `Approve` beat a check keyed on `APPROVE` | One extra `#` removed a finding from validation entirely |
| 11 | **A mixed-format diff parsed as one file** | The second file, carrying a hardcoded production key and a concatenated SQL query, was invisible, and the coverage count said so confidently |
| 12 | **Recall was enforced by nothing** | A blind "APPROVE, no findings" on a diff with a planted hole passed. `validate_findings.py --diff` now fails a review that misses what the parser proved |
| 13 | **The fabrication guard was built but not installed** | `--parsed` catches invented figures; nothing passed it, and it only checked three of seven sections |
| 14 | **Two validators were non-deterministic** | Leak findings came from an unordered set: twelve runs, twelve outputs. The headline reliability claim was false where nobody had looked |
| 15 | **The independence test was near-vacuous** | It ran one parser per agent. A tree with every validator, context file and golden set deleted still printed `independence PASS` |
| 16 | **The compliance audit counted table rows, not inputs** | `35/35 ALL GREEN` while `jira-scribe` shipped two of the three required eval inputs: a scored requirement, missed by the check meant to catch it |

Two smaller ones worth naming: `<!-- INTERNAL` on line 1 emptied the customer
section, so every leak check inspected an empty string; and a code comment
reading *"hidden button for bookkeepers"* was counted as a new branch on the
word *for*.

The pattern across almost all sixteen: **the logic was sound and the input
parsing failed open.** A regex that did not match returned "clean" rather than
"unparseable". The defences were real, and reachable only by inputs that agreed
to be caught.

### Failure modes verified

- Scribe on the transcript: reports `MISSING: actor, action, outcome` and refuses
  to invent the forbidden-post behaviour the meeting never decided. **This is the
  point of the agent.** A separate case asserts that a correct refusal *passes*
  validation rather than scoring as a failure.
- Sentinel on `legacy/billing`: silent on `L3-ARCH-01`, and says so under
  *Suppressed by Project Context*, while still flagging the real defect
  (client-side-only authorisation, `L2-SEC-05`).
- Sentinel with no context: `NO-CONTEXT`, `FATAL`, exit 3, no verdict.
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
