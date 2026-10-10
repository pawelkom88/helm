---
status: draft
task: {{TASK_ID}}
verdict: {{APPROVE or CHANGES_REQUIRED or BLOCKED}}
diff_sha: {{value of diff_sha from `helm status --json`}}
---
# Review — {{TASK_ID}}

<!-- <=150 lines. Independent: judge the diff against WORK.md acceptance criteria and PLAN.md, not against IMPL.md claims. Never modify code. diff_sha binds this review to the exact diff; any later change makes it stale. -->

## Verdict
{{APPROVE | CHANGES_REQUIRED | BLOCKED}} — {{one-line reason}}

## Findings
<!-- Format: - [blocker|major|minor|nit] `path#Lx-y` — issue → suggested fix. Group under bold area labels (Correctness, Architecture, React, TypeScript, State, Testing, Accessibility, Security, Performance). Do not use ### headings here. -->
**Correctness**
- {{none | finding}}

## Traceability
<!-- One row per acceptance criterion in WORK.md, in order (1..N). Test = a backticked file path that exists, or `manual: reason`. Result = pass | fail | unproven. APPROVE requires every row `pass`. `helm check REVIEW` and the final gate verify this mechanically. -->
| AC | Implementation | Test | Result |
|---|---|---|---|
| 1 | {{implementation path#Lx-y}} | {{test path in backticks, or manual: reason}} | {{pass, fail or unproven}} |

## Scope
Changed files vs plan: {{all within plan | unplanned: ...}}
New dependencies: {{none | ...}}   Unrelated refactors: {{none | ...}}

## Residual Risk
{{What the configured checks and this review cannot establish.}}
