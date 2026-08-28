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

Every agent emits JSON with the same three identifying fields, then whatever its
own work produced at the top level.

```json
{
  "agent": "release-archivist",
  "version": "1.0",
  "status": "ok | insufficient_input | unparseable",
  "coverage": { "items_in": 15, "items_accounted": 15, "reconciles": true }
}
```

| Field | Meaning |
|---|---|
| `agent` | Which agent produced this. Checked by the scenario runner. |
| `version` | Envelope version, so a consumer can refuse a shape it does not know. |
| `status` | `insufficient_input` is a **success** — the agent correctly refused to invent. Never an error. `unparseable` means the input looked like the right kind of thing and could not be read; that is a failure, and it exits non-zero. |
| `coverage` | Present where the agent counts something. `items_in` must equal `items_accounted`. |

**There is deliberately no timestamp.** Every envelope is a pure function of its
input, which is what lets the eval suites assert byte-identical output across
runs. A `produced_at` field would break that on the first run.

Agent-specific data sits at the top level rather than under a `payload` key —
`files` and `test_expectation` for the Sentinel, `candidates` and
`missing_fields` for the Scribe, `items` and `unclassified` for the Archivist.
Each is defined in that agent's own `references/output-contract.md`.

Each parser also accepts `--brief`, which emits the same envelope reduced to the
decisions still open. It keeps the identifying fields and the keys the
downstream validator reads, so a brief envelope can be passed anywhere a full
one can.


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
