# Code Review — PROJ-2815 permissions

**Verdict:** REQUEST-CHANGES

## Findings

### [BLOCKER] Authorisation decided by a client-supplied flag
- **Where:** `src/billing/PostingController.cs:44`
- **Rule:** L2-SEC-05 — Authorisation is checked server-side
- **Why it matters:** A caller can set the flag directly and post entries.
- **Suggested fix:** Resolve the role server-side from the token.

### [MAJOR] New permission branch ships without a test
- **Where:** `src/billing/PostingController.cs:44`
- **Rule:** L2-TEST-01 — New conditional branches are covered by a test in the same change
- **Why it matters:** The change adds a branch and touches no test file. A regression here silently re-opens the permission hole.
- **Suggested fix:** Add a test asserting a bookkeeper receives 403 from the endpoint.

## Suppressed by Project Context
- `L3-ARCH-01` on `legacy/billing/**` — DEV-004 (accepted, expires 2027-01)

## Coverage
Files changed: 3 · Reviewed: 2 · Skipped: 1 · Findings: 2 (1 BLOCKER, 1 MAJOR, 0 MINOR)
