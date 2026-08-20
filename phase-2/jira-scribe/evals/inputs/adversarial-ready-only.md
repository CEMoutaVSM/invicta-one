## Prevent bookkeepers from posting accounting entries

### Context
Support reports bookkeepers can post entries via the API even though the UI hides the button.

### User Story
As a bookkeeper, I want to be blocked from posting entries, so that permissions are enforced consistently.

### Acceptance Criteria
1. **Given** I am signed in as a bookkeeper **When** I call the posting endpoint **Then** the request is rejected.
2. **Given** I am signed in as a bookkeeper **When** I open the entries list **Then** I can view all entries.

### Technical Hints
- Enforce in the Service layer, not the Controller.

### Out of Scope
- Entries posted before this change.

### Open Questions
- [ ] None.

### Readiness
READY — MISSING: behaviour after period close.
