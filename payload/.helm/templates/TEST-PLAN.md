---
status: draft
task: {{TASK_ID}}
---
# Test plan — {{TASK_ID}}

<!-- <=100 lines. Input: WORK.md, PLAN.md, .helm/repo/testing.md. Behaviour-level, not implementation-level. Never change production code. -->

## Behaviours
- {{observable behaviour that must hold}} → AC {{n}}

## Fixtures And Utilities
- `{{path}}` — {{reuse for ...}}

## Test Cases
| # | Behaviour | Level | File | Notes |
|---|---|---|---|---|
| 1 | {{...}} | unit | `{{path}}` | {{...}} |

## Gaps
{{What cannot be covered and why; untestable acceptance criteria; missing fixtures. "None" needs a reason.}}
