# Output Contract — Release Archivist

Loaded on demand by SKILL.md §6. Normative.

## Sections
`H1 title` → one-sentence summary → `Breaking Changes` (only if any) → `New`
→ `Improved` → `Fixed` → internal appendix → coverage comment

Sections with no items are omitted, not left empty.

## Every published entry names its source line — mandatory

```
- **Bulk invoice export** — export a filtered invoice list to CSV. <!-- src:1 -->
```

`src:N` is the line of the input log this entry reports. The comment is invisible
to the reader and is what makes the guarantee checkable: `validate_output.py`
compares the set of published lines against the classification and reports any
publishable line that no entry covers.

A count cannot do this job. Dropping a shipped feature while publishing a
suppressed merge commit keeps every total identical, so the check has to be
about *which* items were published, not how many.

## Coverage comment — mandatory
```
<!-- Coverage: in=N published=N internal=N suppressed=N accounted=N duplicates=N -->
```
`in` must equal `accounted`, and `published + internal + suppressed` must equal
`accounted`. `duplicates` is the classifier's `duplicates_published` — it is
read from the ledger, never invented here.

## Re-classifying a delegated line

The classifier reports lines it could not place, or placed while unsure, as
`unclassified`. Those are yours to decide. Name each one you moved:

```
<!-- Coverage: in=15 published=5 internal=5 suppressed=5 accounted=15 duplicates=0 delegated=11:INTERNAL -->
```

Only lines the classifier actually delegated may appear in `delegated=`, and the
totals are recomputed from those decisions. Changing the class of a line the
rules were sure about fails the run. This is the zero-loss guarantee, and it is
what makes "no missing features" a checkable assertion rather than a promise.

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
