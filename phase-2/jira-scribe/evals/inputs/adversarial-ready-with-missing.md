## Prevent bookkeepers from posting accounting entries

### Context
Support reports bookkeepers can post entries via the API.

### User Story
As a bookkeeper, I want to be blocked from posting entries, so that permissions are enforced consistently.

### Acceptance Criteria
1. **Given** I am signed in as a bookkeeper **When** I call the posting endpoint **Then** the request is rejected.

### Technical Hints
- MISSING: which layer enforces the check.

### Out of Scope
- Entries posted before this change.

### Open Questions
- [ ] Which layer enforces the check?

### Readiness
**READY FOR DEV** — MISSING: behaviour for entries already posted.
