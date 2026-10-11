# Repository Architectural Conventions & Skill Guidance

This document defines core repository patterns and conventions. It provides authoritative guidance for the **Planner** when selecting skills under `## Required Skills` in `PLAN.md`.

---

## 🧭 Planner Skill Selection Rubric

When planning tasks, select only skills from `helm skills list` that are strictly necessary for the scope of the change. Never select skills speculatively.

### 1. React 19 & Frontend Architecture
* **`react-composition-patterns`**:
  * **When to select**: Creating or refactoring React components; building reusable component primitives or design systems; untangling boolean prop proliferation (e.g. replacing `isHeader`, `showFooter`, `isCompact` with compound components or explicit variants); managing component-level shared state with React Context; adopting React 19 conventions (such as `ref` as a normal prop instead of `forwardRef`).
  * **When NOT to select**: Non-React tasks, pure backend/CLI logic, or simple single-file markup changes that have no component architecture decisions.

* **`vercel-react-best-practices`**:
  * **When to select**: Any React 19 + Vite task where render performance, bundle footprint, or async data flow is relevant. Covers eliminating client-side async waterfalls (`Promise.all`), optimizing re-renders (calculating derived state during render rather than in `useEffect`, functional `setState`, `startTransition`, `useDeferredValue`), and Vite bundle optimizations (`React.lazy`, direct leaf imports).
  * **Note**: Pruned specifically for client-side Vite/React 19 SPAs; does not apply to server-rendered Next.js/RSC.

### 2. Client Data Fetching & Server State
* **`tanstack-query`**:
  * **When to select**: Tasks involving asynchronous data fetching, caching, pagination, or mutations in React.
  * **Key conventions to plan**: Query Key Factories (array query keys), explicit `staleTime` and `gcTime` (v5 naming), request cancellation passing `signal`, optimistic mutations with snapshot rollback in `onMutate`/`onError`.

### 3. Testing & Verification
* **`playwright-best-practices`**:
  * **When to select**: Tasks that write, modify, or debug end-to-end browser tests, integration user flows, or Playwright configuration.
  * **Key conventions to plan**: User-facing accessible locators (`getByRole`, `getByLabel`), web-first auto-retrying assertions (`expect(locator).toBeVisible()`), zero hardcoded timeouts (`page.waitForTimeout` is forbidden), network mocking via `page.route()`, and `@axe-core/playwright` accessibility audits.
  * **When NOT to select**: Unit test tasks (Vitest, Jest, Python unittest).

### 4. Code Quality & Refactoring
* **`fowler-code-craft`**:
  * **When to select**: Tasks focused on refactoring, technical debt reduction, eliminating code smells (Mysterious Name, Long Function, Primitive Obsession, Feature Envy), improving naming standards, or introducing enterprise architectural patterns (Value Object, Repository, Gateway, Service Layer).
  * **Core rule**: Enforces the **Two Hats** discipline: never combine structural refactoring with functional behavior changes or feature additions in the same step.

### 5. Interactive Workflows
* **`grill-with-docs`**:
  * **Note**: A user-invoked workflow skill (`disable-model-invocation: true`). Never select as an autonomous required skill in `PLAN.md`.

---

## 📋 Skill Selection Matrix for Common Tasks

| Task Type | Recommended Required Skills |
|-----------|----------------------------|
| New React 19 UI Component / Primitive | `react-composition-patterns`, `vercel-react-best-practices` |
| Data-Driven React View (Fetching & API) | `tanstack-query`, `vercel-react-best-practices` |
| Complex UI Feature with Data & Component Hierarchy | `react-composition-patterns`, `tanstack-query`, `vercel-react-best-practices` |
| End-to-End User Flow & Browser Tests | `playwright-best-practices` |
| Refactoring Smelly / Complex Modules | `fowler-code-craft` |
| Refactoring React Component Tree | `fowler-code-craft`, `react-composition-patterns` |
