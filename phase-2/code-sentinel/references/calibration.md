# Calibration — adopting this agent on a new project


The reason a generic reviewer fails is that it does not know which deviations are
deliberate. Fix that in four steps:

1. **Bootstrap** — `python scripts/bootstrap_context.py <repo>` drafts `L3-project.md`
   from the README, ADRs, folder structure and the human comments on recent merged PRs.
   Every inferred rule is written with a confidence level and the evidence behind it.
2. **Ratify** — a tech lead corrects the draft. **The agent cannot ratify its own
   context.** Rules left as `draft` stay dormant.
3. **Shadow** — run advisory-only for one sprint. Humans tag findings
   `useful` / `noise` / `missed`.
4. **Learn** — each `noise` becomes a deviation entry or a rule correction; each `missed`
   becomes a candidate rule. Re-run the golden set after every context change to confirm
   you removed a false positive without losing a true one.

Promote from advisory to required check once precision ≥ 80% on the golden set.
