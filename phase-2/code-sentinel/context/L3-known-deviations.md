# L3 — Known Deviations (Sentinel)

The pressure valve. When the agent flags something intentional, nobody argues
with the model — someone adds an entry here and the agent goes quiet for good.
Every entry has an owner and an expiry.

### DEV-004 — Direct repository access from controllers in /legacy/billing
Status: accepted | Owner: @tech-lead-a | Reviewed: 2026-Q3
Rationale: Pre-dates the service layer. Migration tracked in PROJ-2841.
Agent behaviour: do not flag L3-ARCH-01 for paths under /legacy/billing
Expires: 2027-01

### DEV-005 — Raw SQL in the reporting read-model
Status: accepted | Owner: @data-lead | Reviewed: 2026-Q3
Rationale: Hand-tuned analytical queries; EF Core generated plans were 40x slower.
All inputs are parameterised and reviewed by the data team.
Agent behaviour: do not flag L2-SEC-04 for paths under src/reporting/readmodel
Expires: 2027-06

### DEV-006 — Synchronous event publish in the onboarding saga
Status: accepted | Owner: @tech-lead-a | Reviewed: 2025-Q4
Rationale: Temporary while the outbox pattern was being introduced.
Agent behaviour: do not flag L3-EVENT-01 for paths under src/onboarding
Expires: 2026-06

<!-- Status stays `accepted`. Nobody retired this deviation; its expiry date
     passed and the loader retired it. Writing `expired` here by hand would
     mean a human noticed, which is precisely the thing this mechanism exists
     to avoid relying on. Run load_rules.py with --today before and after
     2026-06-30 to see the suppression disappear on its own. -->

