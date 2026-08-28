# Scenario: One Sprint, Three Agents

A single feature followed from a mumbled sentence in a refinement meeting to a line in
customer-facing release notes. Every agent is exercised, and **none of them knows the
others exist.**

---

## The story

Sprint 42 on `service-alpha` (Billing). A bookkeeper at a customer firm has been able to
post accounting entries they should not have permission to post. Someone mentions it in
refinement. Three weeks later it ships.

| Stage | Agent | Input | Output |
|---|---|---|---|
| Refinement | **jira-scribe** | `fixtures/01-refinement.txt` — a rambling transcript | PROJ-2815 story, Gherkin AC |
| Code review | **code-sentinel** | `fixtures/02-permissions.diff` | Findings, cited and scoped |
| Release | **release-archivist** | `fixtures/03-sprint42.log` | Customer-facing notes |

---

## What each stage is designed to prove

**Stage 1 — the Scribe refuses.** The transcript never says what happens when a
bookkeeper *attempts* a forbidden post. The agent must not invent the behaviour. It
raises `MISSING` and asks. A story that guessed here would have shipped the wrong error
handling.

**Stage 2 — the Sentinel stays quiet where it should.** The diff touches
`legacy/billing/`, where controllers call repositories directly. That violates
`L3-ARCH-01` — and `DEV-004` says it is deliberate. The agent must **not** flag it, and
must say in *Suppressed by Project Context* that it knew. It must still flag the real
defect: an authorisation check on the client only, violating `L2-SEC-05`.

**Stage 3 — the Archivist accounts for everything.** The sprint log has 15 lines, of
which 5 are pure noise and 4 internal. The published notes carry 6 items and the coverage
comment reconciles to 15. Nothing vanishes.

---

## Composition rules

Chaining is **data-only**. No agent imports another, calls another, or reads another's
files. The only thing shared is an envelope shape (`INTERCHANGE.md`), which nothing
imports.

**What the chain actually runs today.** `run_scenario.py --mode chained` runs each
agent's parser and feeds that envelope into that same agent's validator through the
flag that consumes it — `--parsed`, `--diff`, `--ledger`. That is a real pipeline and
it is what the test asserts: the envelope is written to disk, read back, and the
downstream step either accepts it or fails.

**What it does not run.** No script accepts a *sibling's* envelope. There is no
`--story` flag on the Sentinel and no `--review` flag on the Archivist. Three
cross-agent behaviours used to be listed here as though they existed:

- Sentinel + story → check the diff against the story's acceptance criteria
- Archivist + story → prefer the story's customer wording over the commit's
- Archivist + review → warn when an unresolved BLOCKER is shipping

They are what the interchange convention is *for*, and each is a few lines of argument
parsing away. None is implemented, none is evaluated, and listing them as behaviour
overstated what a reader can run. They are kept here as the roadmap they are.

Remove any envelope and every agent still runs on raw input. **With less context, never
with an error.** That part is tested, in both modes.

---

## The two tests

### Composition test
```bash
python scenario/run_scenario.py --mode chained
```
All three run in sequence, each envelope passed into the step that consumes it.
Expected: 3/3 stages complete, every envelope matching the interchange shape, and
every downstream validator exiting 0.

### Independence test — the important one
```bash
python scenario/run_scenario.py --mode independent
```
Each agent runs on raw input with **the other two folders moved out of the tree**. Every
agent must still complete, unmodified. An agent that fails this is not independent and
does not ship.

Run both. Composition proves they are useful together; independence proves each one is
worth pulling down on its own — which is what the Phase 2 brief actually asked for.
