# L3 — Project Context: service-alpha (Billing)

Status: ratified | Owner: @product-owner-a | Last review: 2026-08-06

## Audience
External accountants and bookkeepers at small and mid-sized firms.
Low tolerance for jargon. High sensitivity to anything touching filed accounts.

## Translation table (internal → customer-facing)
| Internal | Customer-facing |
|---|---|
| PostingService / PeriodGuard | posting entries / period lock |
| auth middleware, session store | signing in |
| IQueryable specification | filtering and search |
| RabbitMQ consumer lag | delays in updates appearing |
| EF Core migration | (do not mention — internal) |
| read-model / projection | reports |
| idempotency key | duplicate protection |

| ID | Rule | Status |
|---|---|---|
| L3-REL-01 | Never imply that posted entries can be edited. Say "reversal entry". | ratified |
| L3-REL-02 | Anything touching period close is called out explicitly — it affects filing. | ratified |
| L3-REL-03 | Amounts always carry a currency. | ratified |
| L3-REL-04 | Permission changes name the affected role in customer terms. | ratified |
| L3-REL-05 | Performance claims quote measured before/after numbers or omit numbers entirely. | ratified |
| L3-REL-06 | Beta features carry a Beta tag. | draft |
