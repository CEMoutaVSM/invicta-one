# Output Contract — Release Archivist

Loaded on demand by SKILL.md §6. Normative.

## Sections
`H1 title` → one-sentence summary → `Breaking Changes` (only if any) → `New`
→ `Improved` → `Fixed` → internal appendix → coverage comment

Sections with no items are omitted, not left empty.

## Coverage comment — mandatory
```
<!-- Coverage: in=N published=N internal=N suppressed=N accounted=N -->
```
`in` must equal `accounted`, and `published + internal + suppressed` must equal
`accounted`. This is the zero-loss guarantee, and it is what makes "no missing
features" a checkable assertion rather than a promise.

## Classification enum
`FEATURE` | `FIX` | `IMPROVEMENT` → published
`INTERNAL` → appendix only
`NOISE` → suppressed, still counted

## Invariants enforced by `validate_output.py`
1. Coverage present and reconciling; any shortfall is reported as ITEMS LOST.
2. No commit hash, ticket key, branch name or internal component name in the
   customer-facing text.
3. No marketing superlatives (L2-REL-06).
4. Section order New → Improved → Fixed.
5. No item appears in two sections.
6. Empty release → the explicit notice, never padding.
