---
name: grill-with-docs
description: A relentless, structured interview to sharpen a plan or design before coding, automatically creating domain documentation (GLOSSARY.md) and Architecture Decision Records (ADRs) as decisions are settled.
license: MIT
disable-model-invocation: true
---

# Grill With Docs (Plan & Architecture Stress-Testing)

`grill-with-docs` conducts a rigorous, multi-round interview to stress-test your plan or architecture before touching code. As domain terms and technical decisions resolve, it records durable artifacts directly to the repository:
1. **Domain Terms** → Appended immediately to `GLOSSARY.md`.
2. **Architecture Decisions** → Recorded as numbered ADRs in `docs/adr/`.

This skill is **user-invoked only** (`/grill-with-docs` or explicitly requested). The AI agent must never invoke it autonomously.

---

## Operating Protocol

### 1. The Design Tree & The Frontier
Model the problem as a **design tree**: decisions that branch into dependent decisions.
* **The Frontier**: Identify the set of decisions whose prerequisites are already settled.
* **The Round**: Ask all open questions on the current frontier in a single batch (do not ask one-by-one, and do not ask questions that depend on unresolved decisions).
* Repeat in rounds until the frontier is empty and the plan is watertight.

### 2. Question Format
Inside each round, format every question with a numbered question prompt and an explicit recommendation:
```markdown
### ❓ Question 1: [Short Title]
[Detailed context and the decision to be made, including trade-offs.]

➡️ **Recommendation**: [Agent's recommended option and rationale.]
```
This enables the user to respond rapidly (e.g., `"1: accept recommendation, 2: choose option B"`).

### 3. Concrete Artifact Generation

#### A. GLOSSARY.md
Whenever a domain term, entity name, or concept is clarified or agreed upon, append or update it immediately in `GLOSSARY.md` at the repository root:
```markdown
### Term Name
**Definition**: What the term means in this project.
**Context**: Where and how it is used.
**Constraints**: Invariants or forbidden usages.
```

#### B. Architectural Decision Records (ADRs)
When a decision is **hard to reverse**, **surprising without context**, or involves a **significant trade-off**, write an ADR to `docs/adr/XXXX-title.md` (e.g., `docs/adr/0001-use-sqlite-for-local-cache.md`):
```markdown
# ADR [Number]: [Decision Title]

## Status
Accepted

## Context
[What problem needed solving and why the decision arose.]

## Decision
[What was chosen and how it will be implemented.]

## Consequences
- **Positive**: [Benefits gained]
- **Negative / Trade-offs**: [Costs, complexity, or constraints introduced]
```

### 4. Grounding in Repository Reality
Before asking questions, inspect existing code and architecture to ensure discussions are grounded in actual codebase facts rather than theoretical assumptions.

### 5. Completion Gate
Once the frontier is exhausted:
1. Summarize all resolved decisions and new glossary terms.
2. Verify that `GLOSSARY.md` and any ADRs are cleanly written to disk.
3. Stop and await user confirmation before proceeding to planning or implementation.
