# Interchange Convention

**Status:** convention, not a library. No agent imports this file. No agent imports another agent.

Each agent independently declares its own input and output contract in its own `SKILL.md`.
They happen to agree on the shapes below, which is what lets them be chained. Agreement is
verified by each agent's own validator, not by a shared runtime.

---

## Why this is a convention and not a module

If the agents shared code, deleting one would break the others, and a team could not adopt
just the Sentinel without also taking the Archivist. The whole point of Phase 2 is a
*repository of skills any engineer can pull down* — pulling down one must be enough.

So the coupling is at the level of **data shape only**, and it is one-directional and optional:

| Agent | Accepts | Also accepts (optional) |
|---|---|---|
| Jira Scribe | raw brain dump / transcript | — |
| Code Sentinel | raw `.diff` / PR description | a Scribe `story` envelope, as extra context |
| Release Archivist | raw git log + Jira export | Scribe `story` + Sentinel `review` envelopes |

Every "also accepts" is strictly additive. **No agent ever requires another agent's output.**
Remove the upstream envelope and the downstream agent still runs on raw input alone — with
less context, never with an error.

---

## The envelope

```json
{
  "agent": "jira-scribe",
  "version": "1.0",
  "produced_at": "2026-08-06T10:00:00Z",
  "source": "sprint-42-refinement-notes.txt",
  "status": "ok | insufficient_input | no_output_required",
  "payload": { },
  "coverage": { "items_in": 47, "items_accounted": 47 },
  "citations": ["L2-SEC-03", "L3-ARCH-07"]
}
```

| Field | Meaning |
|---|---|
| `status` | `insufficient_input` is a **success** — the agent correctly refused to invent. Never an error. |
| `coverage` | `items_in` must equal `items_accounted`. This is the zero-loss guarantee, checked by code. |
| `citations` | Every rule the agent invoked. Empty list = no findings, which is a valid outcome. |

`payload` is agent-specific and defined in that agent’s own `<agent>/references/output-contract.md`.

---

## Shared vocabulary

Closed enums. Agents that use these must use exactly these values.

```
CHANGE_CLASS  = FEATURE | FIX | IMPROVEMENT | INTERNAL | NOISE
SEVERITY      = BLOCKER | MAJOR | MINOR
CONTEXT_LAYER = L1 | L2 | L3
RULE_ID       = L<layer>-<DOMAIN>-<NN>          e.g. L2-SEC-03, L3-ARCH-07
```

---

## Independence test

Part of every agent's eval suite:

```bash
mv code-sentinel release-archivist /tmp/    # remove the other two
cd jira-scribe && python scripts/run_evals.py
# must pass its full suite, unmodified
```

`scenario/run_scenario.py --mode independent` automates this: it copies one agent
into an empty tree and runs that agent's **entire** eval suite there. Running a
single parser would not be a test — a tree with every validator, every context
file and every golden set deleted passed that version.

An agent that fails this is not independent and does not ship.
