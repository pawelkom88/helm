---
status: draft
task: {{TASK_ID}}
test_first: false
specialists:
---
# Plan — {{TASK_ID}}

<!-- <=120 lines. Built ONLY from WORK.md (+ files it references). No production code. test_first: true lets the test analyst write tests (test globs only) before implementation. specialists: comma list of security, accessibility, performance (only if genuinely relevant). -->

## Objective
{{One sentence, matching WORK.md.}}

## Approach
{{The intended implementation, step by step, in the smallest correct form.}}

## Affected Areas
- {{package / feature}} — {{how}}

## Files Likely To Change
<!-- One backticked path per line; directory prefixes allowed. The final gate flags changed files not listed here. -->
- `{{path}}`

## Testing Strategy
{{Behaviours to cover, level (unit/integration/e2e), which existing utilities to reuse.}}

## Risks
- {{risk}} — {{mitigation}}

## Alternatives Considered
- {{option}} — {{why not}}   <!-- If two options are materially different, STOP and ask via BLOCKED.md. -->

## Open Questions
None (evidence: {{what you checked}})

## Required Skills
<!-- Names from `helm skills list` only; the implementer will read exactly these. -->
- {{skill-name | none}}
