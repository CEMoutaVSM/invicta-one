# Requirements — Phase 2, as testable assertions

Derived from `AI Program 2026_Phase2_V1`. `[AUTO]` is checked by `run_audit.py`;
`[JUDGE]` needs a human or a reasoning agent.

Auditors: judge against the requirement text only. Do not assume a previous session's
conclusions are correct.

## A. Submission requirements (scored — failing any of these loses the stamp)

| ID | Requirement | Kind |
|---|---|---|
| A1 | A `SKILL.md` exists for each of the three trials | AUTO |
| A2 | Each `SKILL.md` contains an "Eval Log" section | AUTO |
| A3 | The Eval Log is at the **bottom** of the file | AUTO |
| A4 | The Eval Log evidences **at least 3 separate** inputs | AUTO |
| A5 | The inputs are **messy**, not sanitised | JUDGE |
| A6 | Outputs are shown to be **deterministic** | AUTO+JUDGE |
| A7 | Files ready to commit to the Drive folder | JUDGE |
| A8 | Form submission still to be done by a human | MANUAL |

## B. Trial 1 — The Archivist

| ID | Requirement | Kind |
|---|---|---|
| B1 | Accepts a messy dump of raw git commits AND raw Jira logs | AUTO |
| B2 | Filters internal noise (e.g. "fixed typo", "merge branch main") | AUTO |
| B3 | Groups remaining items **by user impact** | JUDGE |
| B4 | Produces polished, client-ready **markdown** changelog | JUDGE |
| B5 | Guarantees **zero missing features** | AUTO |
| B6 | Formats technical jargon into **business value** | JUDGE |

## C. Trial 2 — The System Scribe

| ID | Requirement | Kind |
|---|---|---|
| C1 | Accepts a single-sentence brain dump **or a raw audio transcript** | AUTO |
| C2 | Generates **Context** | AUTO |
| C3 | Generates **Acceptance Criteria in Given-When-Then Gherkin** | AUTO |
| C4 | Generates **Technical Implementation Hints** | AUTO |
| C5 | Behaves as a strict QA/Tech Lead **refusing vague instructions** | JUDGE |
| C6 | Performs **edge-case forecasting** | JUDGE |
| C7 | Enforces structure; result is "Ready for Dev" | JUDGE |

## D. Trial 3 — The Code Sentinel

| ID | Requirement | Kind |
|---|---|---|
| D1 | Analyses a git diff (`.diff`) or a PR description | AUTO |
| D2 | Maps against **team-specific engineering standards** | AUTO |
| D3 | Uses a **"negative prompting" guardrail** approach | AUTO |
| D4 | Does **not** nitpick code style — leaves that to the linter | AUTO |
| D5 | Looks for logical fallacies, security anti-patterns, architectural compliance | JUDGE |
| D6 | Flags **missing unit test coverage** | AUTO |
| D7 | Acts as an automated first-pass reviewer | JUDGE |

## E. The rubric

Quoted: a winner builds *"a skill that behaves like a reliable, production-ready
utility script — not a chatbot that requires constant hand-holding"*, and Phase 2 is
*"software engineering principles applied to natural language."*

| ID | Requirement | Kind |
|---|---|---|
| E1 | Behaves like a utility script: defined interface, contract, failure mode, tests | JUDGE |
| E2 | Requires no hand-holding — no clarifying chat needed for a valid input | JUDGE |
| E3 | Reliable: same input produces the same decisions | AUTO |
| E4 | Not merely a long prompt | JUDGE |

## F. Self-imposed claims — the submission asserts these, so verify them

| ID | Claim | Kind |
|---|---|---|
| F1 | Agents are independent; each works with the others deleted | AUTO |
| F2 | No agent imports or references a sibling | AUTO |
| F3 | Citation rule holds: no finding without a loaded rule ID | AUTO |
| F4 | Suppressed paths produce no findings | AUTO |
| F5 | Expired deviations stop suppressing | AUTO |
| F6 | Refusal (`insufficient_input`) is treated as success | AUTO |
| F7 | Golden sets record decisions, not prose | JUDGE |
| F8 | Every documented file path exists | AUTO |
