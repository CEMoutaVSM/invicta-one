# Output Contract — Jira Scribe

Loaded on demand by SKILL.md §6. Normative: if this file and prose disagree, this wins.

## Sections — all required, this order
`Title (H2)` → `Context` → `User Story` → `Acceptance Criteria` → `Technical Hints`
→ `Out of Scope` → `Open Questions` → `Readiness`

## Field rules
| Field | Rule |
|---|---|
| Title | Imperative, ≤ 80 chars, no ticket prefix |
| Context | 2–4 sentences. Why it exists, who asked, what breaks today |
| User Story | Exactly `As a <actor>, I want <action>, so that <outcome>.` |
| Acceptance Criteria | Numbered. Each `**Given** … **When** … **Then** …`. No compound When |
| Technical Hints | Bullets. Components from the L3 stack. Directions, not designs |
| Out of Scope | Bullets. Explicit exclusions |
| Open Questions | `- [ ]` checkboxes, each addressed to a named role |
| Readiness | `READY` or `BLOCKED — <reason>` |

## Invariants enforced by `validate_output.py`
1. `READY` is forbidden while any `MISSING:` marker is present.
2. Every `MISSING:` marker has a matching Open Question.
3. No estimate, story points, t-shirt size or assignee anywhere.
4. Every numeric value in Context / User Story / AC appears in the input
   (small ordinals 1–10 exempted). Anything else is treated as fabrication.
5. Every AC is Given-When-Then; a compound `When … and …` must be split.

## Markers
`MISSING: <field>` — a required field the input did not supply. Never inferred.
`AMBIGUOUS: actor` — several glossary actors present; the agent must ask, not choose.
