---
name: fowler-code-craft
description: >-
  Audits code quality, diagnoses Fowler code smells, enforces intent-revealing naming,
  and applies Martin Fowler's Refactoring and Enterprise Application Architecture (PoEAA) patterns
  using a safe, backward-compatible, propose-before-touching workflow.
  Use when asked to refactor code, clean up technical debt, eliminate code smells, improve naming,
  or introduce architectural patterns like Value Object, Repository, Gateway, or Service Layer.
license: MIT
---

# Fowler Code Craft: Refactoring, Smell Elimination & Intent-Revealing Naming

This skill provides an authoritative, systematic workflow for assessing code quality, diagnosing code smells, elevating naming clarity, and applying refactoring patterns from Martin Fowler's foundational works:
* ***Refactoring: Improving the Design of Existing Code* (2nd Edition)**
* ***Patterns of Enterprise Application Architecture* (PoEAA)**

---

## 🧭 Foundational Operating Principles

1. **Zero Regressions & Backward Compatibility**:
   * Refactoring preserves observable software behavior 100%.
   * Public APIs, component props, function signatures, and return structures must remain strictly backward-compatible unless breaking changes are explicitly requested.
2. **Propose Before Touching (Execution Gate)**:
   * Always present a comprehensive **Refactoring & Naming Proposal** (Smell Triage, Before/After Diff, Risk Assessment) before modifying code files.
   * Never modify existing files without user agreement on the proposed plan.
3. **The Two Hats Discipline**:
   * Never combine refactoring with adding new features or altering business requirements. Wear one hat at a time: either restructure code *or* add functionality.
4. **Intent-Revealing Naming**:
   * Code must read as executable documentation. Eliminate ambiguous names (`data`, `temp`, `val`), boolean argument traps, and generic noise words (`Manager`, `Helper`, `Processor`).
5. **Architectural Coherence**:
   * Connect micro-level refactorings (e.g., *Extract Function*, *Replace Conditional with Lookup*) with macro enterprise patterns (e.g., *Value Object*, *Repository*, *Gateway*, *Service Layer*).

---

## 🔄 The 7-Step Refactoring Workflow

```
[1. Target Inspection & Scope Definition]
                  ↓
[2. Code Smell Triage & Naming Audit]
                  ↓
[3. Fowler & PoEAA Pattern Mapping]
                  ↓
[4. Draft Refactoring Proposal (Before/After)]
                  ↓
[5. User Approval Gate (Review & Adjust)]
                  ↓
[6. Safety Harness (Characterization Tests)]
                  ↓
[7. Incremental Refactor & Automated Verification]
```

### Step 1: Target Inspection & Scope Definition
Identify the exact files, modules, or functions targeted for refactoring. Determine:
* What callers depend on this module?
* What are the public contracts and interfaces that must remain stable?
* Are automated tests currently covering this code?

### Step 2: Code Smell Triage & Naming Audit
Analyze the code against the Fowler catalogs:
* **Check for the 24 Fowler Smells**: (See [references/code-smells-catalog.md](./references/code-smells-catalog.md))
  * Micro smells: *Mysterious Name*, *Long Function*, *Primitive Obsession*, *Feature Envy*, *Repeated Switches*, *Data Clumps*.
  * Architectural smells: *Anemic Domain Model*, *Shotgun Surgery*, *Divergent Change*, *Large Class*.
* **Naming Audit**: (See [references/naming-conventions.md](./references/naming-conventions.md))
  * Does every identifier answer *why it exists*, *what it does*, and *how it is used*?
  * Are there forbidden noise words (`Data`, `Info`, `Manager`, `Helper`)?
  * Are boolean variables and predicates written as assertions (`isEligible`, `hasExpired`, `canCancel`)?

### Step 3: Fowler & PoEAA Pattern Mapping
Map each diagnosed smell to its precise remedy:
* Micro refactoring patterns: (See [references/refactoring-patterns.md](./references/refactoring-patterns.md))
  * *Extract Function / Variable*, *Introduce Parameter Object*, *Split Phase*, *Replace Conditional with Polymorphism/Lookup Table*.
* Enterprise architecture patterns: (See [references/enterprise-patterns.md](./references/enterprise-patterns.md))
  * *Value Object / Money*, *Repository*, *Gateway*, *Service Layer*, *Special Case (Null Object)*, *DTO*.

### Step 4: Draft Refactoring Proposal
Produce a structured report containing:
1. **Smells & Naming Issues Found**: Precise lines, symptom descriptions, and impact.
2. **Proposed Patterns & Naming Strategy**: Specific refactorings to apply.
3. **Before & After Design Comparison**: Clear, focused code snippets showing how the code will evolve.
4. **Impact & Risk Assessment**: Public contract preservation, risk rating (Low/Medium/High), and test verification strategy.

### Step 5: User Approval Gate
Present the proposal to the user and await explicit confirmation. If the user suggests tweaks or alternative boundaries, incorporate them before writing any code.

### Step 6: Safety Harness (Characterization Tests)
Before refactoring logic:
* If comprehensive tests exist: run them and ensure they pass.
* If tests are absent or incomplete: write minimal characterization (golden-master) tests to pin down the existing behavior. Refactoring without tests is guesswork.

### Step 7: Incremental Refactor & Automated Verification
Apply refactorings in small, isolated steps:
1. Rename and extract variables/functions.
2. Introduce parameter objects and value objects.
3. Decouple persistence or external dependencies via gateways/repositories.
4. Run linters, type checks, and automated tests after each step to guarantee zero regressions.

---

## 📚 Reference Library

* **[Code Smells Catalog](./references/code-smells-catalog.md)**: Exhaustive guide to all 24 Fowler code smells with detection heuristics, symptoms, and remedies.
* **[Intent-Revealing Naming Conventions](./references/naming-conventions.md)**: Fowler and Clean Code naming rubrics, forbidden noise words, predicate guidelines, and ubiquitous language standards.
* **[Enterprise Architecture Patterns (PoEAA)](./references/enterprise-patterns.md)**: Applying Domain Model, Value Object, Repository, Gateway, Service Layer, and DTOs to eliminate architectural rot.
* **[Refactoring Patterns Catalog](./references/refactoring-patterns.md)**: Catalog of behavior-preserving micro-refactorings with modern idioms.
* **[Before & After Case Studies](./examples/before-after-refactoring.md)**: Concrete real-world examples in TypeScript and Python demonstrating end-to-end smell removal.
