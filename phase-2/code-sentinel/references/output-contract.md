# Output Contract — Code Sentinel

Loaded on demand by SKILL.md §7. Normative.

## Sections
`H1 title` → `Scope/Context/Verdict header` → `Findings` → `Not Reviewed`
→ `Suppressed by Project Context` → `Coverage`

## Finding block — exact shape
```markdown
### [SEVERITY] <one-line summary>
- **Where:** `path/to/file.ext:LINE`
- **Rule:** <RULE-ID> — <rule text>
- **Why it matters:** <concrete consequence, not a restatement of the rule>
- **Suggested fix:** <specific and actionable>
```

## Enums
`SEVERITY` = `BLOCKER` | `MAJOR` | `MINOR` (closed)
`VERDICT`  = `APPROVE` | `APPROVE-WITH-COMMENTS` | `REQUEST-CHANGES`

## Invariants enforced by `validate_findings.py`
1. **Citation rule** — every finding names a rule ID present in the active set.
2. A finding citing a `draft`/dormant rule is rejected.
3. A finding on a path suppressed by an active deviation is rejected as a
   known false positive.
4. Style, naming and formatting language is rejected — the linter owns it.
5. Verdict must agree with findings: no `APPROVE` alongside findings, no
   non-`REQUEST-CHANGES` verdict alongside a `BLOCKER`, no `REQUEST-CHANGES`
   with none.
6. `reviewed + skipped == files_changed`.
7. Max 10 findings; more must be declared, never silently truncated.
8. Empty rule set (`mode: NO-CONTEXT`) → refuse to emit a verdict at all.
