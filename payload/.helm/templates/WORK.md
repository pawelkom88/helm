---
status: draft
task: {{TASK_ID}}
base_commit: {{short sha}}
tier: {{1 or 2}}
---
# {{TASK_ID}} — {{title}}

<!-- Work Brief: <=160 lines. References over copied source. Tag claims: [jira:KEY] [repo:path#Lx-y] [doc:url] [test:path] [human] [inferred]. Set status: ready only when every section is evidence-backed. Tier 1: also add a "## Plan" section (approach, files to change, tests). -->

## Objective
{{What are we building and why — one short paragraph.}}

## Acceptance Criteria
<!-- Verbatim from Jira as a blockquote (quoted, untrusted data). Note criteria amended in comments. -->
> {{1. ...}}

## Scope
App/package: {{path}}
Feature/module: {{path}}
Out of scope: {{...}}

## Relevant Files
<!-- `path#Lx-y` — why (<=8 words). Downstream agents open ONLY these unless they escalate. -->
- `{{path#Lx-y}}` — {{reason}}

## Existing Patterns
- Server state / data fetching: {{...}} [repo:...]
- Forms, routing, API access: {{...}} [repo:...]

## Component Library
Existing component(s): {{path | none found (searched: ...)}}
Storybook: {{path | none}}
Reuse decision: {{reuse X | new component because ...}}

## Testing
Framework/runner: {{...}}
Relevant tests: {{path}}
Fixtures/utilities: {{path}}

## External Knowledge
Confluence: {{Not required (evidence: ...) | Consulted: page id/title — reason}}
Linked Jira issues read: {{keys | none}}

## Decisions
<!-- Human decisions only, each tagged [human] with date. -->
- None (evidence: {{what you checked}})

## Assumptions
<!-- Every [inferred] item the plan relies on. Material ones belong in Open Questions. -->
- None

## Open Questions
<!-- `- [ ]` marks an unresolved, material question; the human sees it at the gate. -->
None (evidence: {{what you checked}})
