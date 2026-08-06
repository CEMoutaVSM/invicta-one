# L3 — Project Context: service-alpha (Billing)

Status: ratified | Owner: @tech-lead-a | Last review: 2026-08-06
Bootstrapped by agent from README + ADRs + 40 merged PRs, then human-corrected.
Rules marked `draft` are dormant and produce no output until ratified.

## Actors (closed list — an actor outside this list must be named in the input)
| Actor | Meaning |
|---|---|
| accountant | External customer, prepares and files accounts |
| bookkeeper | External customer, day-to-day entry, reduced permissions |
| admin | Customer-side administrator, manages users and subscriptions |
| support-agent | Internal Visma staff, read-mostly with audit trail |

## Glossary
- **Posting** — an immutable accounting entry. Never edited, only reversed.
- **Period close** — monthly lock; after close, entries are read-only.
- **Draft invoice** — mutable until issued; issuing is irreversible.

## Stack
API: .NET 8, layered (Controller → Service → Repository). UI: React 18 + TypeScript.
Data: PostgreSQL, EF Core migrations. Async: RabbitMQ. Auth: OIDC via Visma Connect.

| ID | Rule | Status |
|---|---|---|
| L3-STORY-01 | Any story touching postings states behaviour after period close. | ratified |
| L3-STORY-02 | Money is always accompanied by a currency. No bare amounts. | ratified |
| L3-STORY-03 | Stories affecting bookkeepers state the permission boundary explicitly. | ratified |
| L3-STORY-04 | Irreversible actions require a confirmation criterion. | ratified |
| L3-STORY-05 | Bulk operations state the behaviour on partial failure. | draft |
