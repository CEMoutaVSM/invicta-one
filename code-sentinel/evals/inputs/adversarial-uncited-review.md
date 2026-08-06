# Code Review — PROJ-2841 billing tweaks

**Verdict:** REQUEST-CHANGES

## Findings

### [BLOCKER] Controller talks straight to the repository
- **Where:** `legacy/billing/InvoiceController.cs:88`
- **Rule:** L3-ARCH-01 — Controllers must not reference a Repository type
- **Why it matters:** Bypasses the service layer.
- **Suggested fix:** Introduce a service.

### [CRITICAL] This method is too long and hard to read
- **Where:** `src/billing/PostingService.cs:210`
- **Why it matters:** Naming convention here is inconsistent and indentation is off.
- **Suggested fix:** Rename this and split it up.

### [MAJOR] New endpoint has no idempotency key
- **Where:** `src/billing/RefundController.cs:12`
- **Rule:** L3-ARCH-04 — New endpoints must expose an idempotency key
- **Why it matters:** Retries could double-refund.
- **Suggested fix:** Add the header.

## Coverage
Files changed: 12 · Reviewed: 9 · Skipped: 1 · Findings: 3
