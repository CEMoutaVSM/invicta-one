# L3 — Known Deviations (Archivist)

### DEV-010 — Compliance changes are published even when internal-only
Status: accepted | Owner: @product-owner-a | Reviewed: 2026-Q3
Rationale: Customers' auditors ask for evidence of regulatory changes.
Agent behaviour: items matching "compliance", "SAF-T", "e-invoicing" or a
regulation name are published even if classified INTERNAL.
Expires: 2027-06

### DEV-011 — Dependency bumps published when they close a public CVE
Status: accepted | Owner: @security-lead | Reviewed: 2026-Q3
Rationale: Customers run vulnerability scanners against our published notes.
Agent behaviour: INTERNAL items citing a CVE identifier are published under
Fixed as a security improvement, without exploit detail.
Expires: 2027-06
