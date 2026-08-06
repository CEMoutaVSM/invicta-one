# L2 — Visma Org Standards (Code Review)

Scope: all Visma Tech Portugal projects. Owner: Platform & Security. Review: quarterly.
Applies regardless of project. Never overridden by L3 — only narrowed by a deviation.

| ID | Rule | Status |
|---|---|---|
| L2-SEC-01 | No secrets, tokens, keys or connection strings in source or config. | ratified |
| L2-SEC-02 | Personal data must not be written to logs, traces or error messages. | ratified |
| L2-SEC-03 | User input crossing a trust boundary is validated at that boundary. | ratified |
| L2-SEC-04 | Database access uses parameterised queries. No string-concatenated SQL. | ratified |
| L2-SEC-05 | Authorisation is checked server-side. Client-side checks are not sufficient. | ratified |
| L2-LOGIC-01 | Error paths are handled, not swallowed. An empty catch block is a defect. | ratified |
| L2-LOGIC-02 | Nullable values are checked before dereference on newly added paths. | ratified |
| L2-LOGIC-03 | Off-by-one and boundary conditions on new loops and slices. | ratified |
| L2-LOGIC-04 | Resources acquired in a new path are released on every exit, including errors. | ratified |
| L2-TEST-01 | New conditional branches are covered by a test in the same change. | ratified |
| L2-DATA-01 | Schema migrations are reversible, or state explicitly why they are not. | ratified |
| L2-PERF-01 | No query inside a loop over a collection of unbounded size. | ratified |

## Out of scope for this agent — the linter owns these
Formatting, indentation, naming conventions, import ordering, line length,
trailing whitespace, brace style, var vs explicit types.
Raising any of these is a defect in the agent, not in the code.
