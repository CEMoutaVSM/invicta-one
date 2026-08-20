# Code Review — PROJ-2822

**Verdict:** REQUEST-CHANGES

## Findings

### [MAJOR] Nullable value dereferenced on a new path
- **Where:** `src/billing/PostingController.cs:51`
- **Why it matters:** The caller can pass null and the new branch dereferences it.
- **Suggested fix:** Guard the value before use.

## Coverage
Files changed: 1 · Reviewed: 1 · Skipped: 0 · Findings: 1 (0 BLOCKER, 1 MAJOR, 0 MINOR)
