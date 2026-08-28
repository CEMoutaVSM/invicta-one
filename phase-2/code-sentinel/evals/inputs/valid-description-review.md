# Code Review

**Verdict:** APPROVE-WITH-COMMENTS

## Findings

### [MAJOR] Reporting service reads the invoice read-model directly

- Where: reporting service
- Rule: L3-ARCH-01
- Why: the description states the new endpoint queries the invoice read-model
  directly. Crossing that ownership boundary is what the rule exists to
  prevent, and it is visible in the described approach rather than in code.
- Fix: read through the owning service's API instead.

## Coverage

No diff was supplied. This review is based on the pull request description
only: it raises architectural risks against the described approach, and cannot
speak to line-level defects or to whether tests were added.
