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
d29a32c9b5e1f02cd803d44f24191f28
d29a32c9b5e1f02cd803d44f24191f28
d29a32c9b5e1f02cd803d44f24191f28
```

### 2. They are independent

```
=== INDEPENDENCE TEST — the other two agents are DELETED ===
  [OK ] jira-scribe         ran with code-sentinel, release-archivist removed
         9/9 passed
  [OK ] code-sentinel       ran with jira-scribe, release-archivist removed
         17/17 passed
  [OK ] release-archivist   ran with jira-scribe, code-sentinel removed
         12/12 passed
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
$ python code-sentinel/scripts/validate_findings.py \
    code-sentinel/evals/inputs/adversarial-uncited-review.md --today 2026-08-06
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
This is the combined view: **38 cases over 29 input files**, all green.

Corpus: real sprint artefacts from `service-alpha`, anonymised with a fixed
substitution map (service names to `service-alpha`, people to first names,
tickets to `PROJ-`). Mess deliberately preserved: typos, mixed PT/EN, filler,
mid-sentence reversals, duplicate ticket keys.

| Agent | Cases | Golden-gated | Inputs | Covers |
|---|---|---|---|---|
| `release-archivist` | 12 | 4 | 10 | classification, line-level ledger, per-entry attribution, leak detection, refusal |
| `jira-scribe` | 9 | 3 | 8 | transcript refusal, brain-dump happy path, contract validation, fabrication guard |
| `code-sentinel` | 17 | 5 | 11 | diff parsing, rule loading, citation rule, recall, secret detection, NO-CONTEXT refusal |

Run them yourself: `python <agent>/scripts/run_evals.py` in any agent folder, or
`./verify.sh` for everything. `verify.sh` also replays the end-to-end traces in
`demo/`, and runs the auditor regression suite described below.

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
`demo/` holds one end-to-end trace per agent, which is the only place in this
repository where the whole loop is visible.

### Defects found and fixed

Each agent's own list is in `<agent>/references/eval-deltas.md` — **47 in total**,
15 in the Archivist, 8 in the Scribe, 24 in the Sentinel. Eleven were found by
the build-time harness; the rest by **fourteen independent auditors**, each running in a clean context, blind to the others and forbidden from
reading this project's own conclusions. Count them yourself: every check in
`audit/regressions.py` carries the tag of the auditor that found it.

The ones worth naming, because they are the ones a reader will not expect:

| Defect | Why it mattered |
|---|---|
| **A single line disabled every validator.** All three opened with a substring test for `insufficient_input` and returned early | A review declaring APPROVE with three BLOCKERs, an invented rule ID and a suppressed path passed clean |
| **The regression gate did not exist.** `evals/golden/` was read by no code | Sabotaging two rules changed six decisions; every suite stayed green |
| **Zero-loss was a tautology.** The class buckets partition the items, so the identity could not fail | 40,000 fuzzed inputs, zero failures. Deleting a shipped feature passed |
| **A guarantee weakened by its own author.** Letting the model reclassify uncertain lines was implemented as a *count*, which also permitted deleting a shipped feature | Now every published entry names the input line it reports, so the check is about *which* features shipped |
| **Security demands that forced a lie.** The secret scanner fired on `// api_key = "your-key-here"` in a comment | An honest reviewer could not pass without fabricating a finding. It now demands only vendor-issued token formats |
| **A revert of a revert shipped a feature to nobody.** Filed as "net zero" noise, accounted for, suppressed | The zero-loss guarantee reduced to line accounting: the demo's own log ships a feature the notes never mention, with every check green |
| **The compliance audit counted table rows, not inputs** | `35/35 ALL GREEN` while an agent shipped two of the three required eval inputs — a scored requirement, missed by the check meant to catch it |

The pattern across most of them: **the logic was sound and the input parsing
failed open.** A regex that did not match returned "clean" rather than
"unparseable". The defences were real, and reachable only by inputs that agreed
to be caught.

Every one is now a permanent test. `audit/regressions.py` reproduces them as
**125 checks**, each tagged with the auditor and finding it descends from, so a
failure names which defect returned rather than merely that something broke.

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
