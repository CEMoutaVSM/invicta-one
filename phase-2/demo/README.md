# End-to-end traces

`verify.sh` exercises the deterministic layer — the scripts. It never invokes a
model, so it can prove the scaffolding is reproducible and cannot show an agent
working end to end.

These traces close that gap. One per agent, four files each:

| File | What it is |
|---|---|
| `1-input.*` | The raw, messy input, exactly as it arrives |
| `2-parsed.json` / `2-ledger.json` | What the deterministic script decided |
| `3-*.md` | The artefact a model produced from that |
| `4-verdict.txt` | What the validator said about the artefact |

Nothing here is written by hand except the model's artefact. Run
`python demo/refresh.py` to regenerate every trace and re-record every verdict;
it exits non-zero if any artefact no longer satisfies its contract, and
`verify.sh` runs it.

That guard exists because these went stale once already. The archivist trace
was committed with a stored verdict of `PASS` while its notes actually failed
validation with seven violations — per-entry `src:N` attribution had been added
to the contract afterwards, and the trace was never re-run. A stale trace that
claims success is worse than no trace at all, so the verdicts are now recorded
by the validator rather than typed.

## What each one shows

- **release-archivist** — fifteen lines of git log, with merges, a
  revert-of-revert and duplicate ticket keys, become six customer-facing
  entries. The ledger reconciles line-for-line, and every published bullet names
  the input line it reports.
- **jira-scribe** — a brain dump becomes a story with Given-When-Then criteria.
  The parse shows the actor was recovered from the project glossary, not from
  the words on the page.
- **code-sentinel** — a three-file diff becomes a review in which every finding
  cites a live rule, the generated file is skipped, and the deliberate
  architectural deviation is declared rather than flagged.
