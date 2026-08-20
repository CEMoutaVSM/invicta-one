# L3 — Project Context: service-alpha (Billing)

Status: ratified | Owner: @tech-lead-a | Last review: 2026-08-06
Bootstrapped from README + 6 ADRs + human comments on 40 merged PRs, then corrected.
Rules marked `draft` are DORMANT and produce no findings.

## Architecture (from ADR-001, ADR-004)
Strict layering: `Controller → Service → Repository`. Controllers hold no business
logic and never touch a repository directly. Domain events published via RabbitMQ.
Postings are immutable: corrections are reversal entries, never updates.

## Intentional patterns a generic reviewer would wrongly flag
- Repositories return `IQueryable` by design (ADR-004, composable specifications).
  This looks like a leaky abstraction. It is deliberate.
- Money is `decimal` with an explicit `Currency`, never `double`, never bare.
- Period-close checks live in the Service layer, not the database. Deliberate:
  the rule is jurisdiction-dependent and changes faster than schema.

| ID | Rule | Status |
|---|---|---|
| L3-ARCH-01 | Controllers must not reference a Repository type. | ratified |
| L3-ARCH-02 | Business logic must not live in a Controller. | ratified |
| L3-ARCH-03 | Writes to postings after period close must go through PeriodGuard. | ratified |
| L3-DATA-01 | Monetary values use decimal with an explicit Currency. Never double. | ratified |
| L3-DATA-02 | Postings are never updated in place. Corrections are reversals. | ratified |
| L3-EVENT-01 | Domain events are published after the transaction commits, not inside it. | ratified |
| L3-PERF-01 | Repository calls inside a loop over invoice lines are forbidden. | ratified |
| L3-ARCH-04 | New endpoints must expose an idempotency key. | draft |
