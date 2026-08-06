# CLAUDE.md

Project instructions for Claude Code. Read `HANDOFF.md` for full context and the
pending work queue.

## What this is

Three independent AI agents submitted to **Visma Tech Portugal's AI Program 2026,
Phase 2: The Agentic Shift**. Deliverable is a `SKILL.md` per agent, committed to a
shared repo, each with an Eval Log proving deterministic behaviour on messy inputs.

**Deadline: today.** Prefer finishing over refactoring. Do not restructure working code.

## Non-negotiable invariants

Breaking any of these breaks the submission. Verify with `./verify.sh` after every change.

1. **Agents are independent.** No agent imports, calls, or reads files from another.
   The only coupling is a data convention (`INTERCHANGE.md`), which nobody imports.
   Test: each agent must pass its own evals when the other two folders are deleted.
2. **The citation rule.** The Sentinel may not raise a finding it cannot attach a
   loaded rule ID to. No free-floating opinions about someone's architecture.
3. **Determinism is architectural, not requested.** Anything a script can do
   deterministically must not be done by the model. If you find yourself writing
   "the model should consistently...", write code instead.
4. **Refusal is success.** `status: insufficient_input` is a *passing* run. An agent
   that invents a missing field has failed, even if the output looks complete.
5. **Every `SKILL.md` ends with an Eval Log.** This is a scoring requirement from the
   brief, not a nicety.
6. **Golden sets record decisions, never prose.** Asserting on LLM wording produces a
   brittle suite that proves nothing. Assert on classifications, rule IDs, coverage.

## Layout

```
<agent>/
  SKILL.md      entry point; 9 fixed sections + Eval Log at the bottom
  scripts/      deterministic work; no LLM calls anywhere in here
  context/      L2 (org) + L3 (project) calibration layers
  references/   loaded on demand
  evals/        inputs/ (messy, real, anonymised) + golden/ (decisions)
```

## Conventions

- Python 3, standard library only. No dependencies — the agents must run anywhere.
- Every CLI: `--json` where useful, SIGPIPE-guarded, exit 0 pass / 1 fail / 2 usage
  / 3 config error.
- Rule IDs: `L<layer>-<DOMAIN>-<NN>`. Rules marked `draft` are dormant and must
  produce no output. Deviations carry an owner and an expiry.
- British spelling in prose. Keep the tone plain; no marketing language.

## Do not

- Add dependencies, package managers, or a build step.
- Make one agent aware of another.
- "Improve" prose in `SKILL.md` files without re-running the evals — several
  sentences are load-bearing and referenced by validators.
- Regenerate golden files to make a failing test pass. Investigate first; a golden
  diff is a finding, not an inconvenience.

## Verify

```bash
./verify.sh          # everything: evals, independence, composition, audit
```
