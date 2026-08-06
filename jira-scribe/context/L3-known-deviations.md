# L3 — Known Deviations (Scribe)

Accepted exceptions. Each has an owner and an expiry so this file cannot
quietly become a list of excuses.

### DEV-001 — Support-agent stories may omit the outcome clause
Status: accepted | Owner: @tech-lead-a | Reviewed: 2026-Q3 | Expires: 2027-01
Rationale: internal tooling stories are driven by an audit obligation, not user value.
Agent behaviour: do not raise MISSING: outcome when the actor is `support-agent`;
instead require a reference to the obligation.

### DEV-002 — Migration stories are exempt from L2-A11Y-01
Status: accepted | Owner: @tech-lead-a | Reviewed: 2026-Q3 | Expires: 2027-06
Rationale: no user-facing surface.
Agent behaviour: skip the accessibility criterion when the title begins `Migrate`.
