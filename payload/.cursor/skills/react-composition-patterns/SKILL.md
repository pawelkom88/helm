---
name: react-composition-patterns
description: React 19 composition patterns that scale. Use when architecting or refactoring React components to eliminate boolean prop proliferation, designing compound components, organizing state with Context and custom hooks, and adopting React 19 component conventions.
license: MIT
metadata:
  author: vercel
  version: "1.0.0"
---

# React Composition Patterns

Composition patterns for building flexible, maintainable React components. Avoid boolean prop proliferation by using compound components, lifting state, explicit variants, and composing internals.

## When to Apply

Reference these guidelines when:
- Designing new React components or UI building blocks
- Refactoring components with excessive boolean props (`isCompact`, `showFooter`, `hasBorder`)
- Building reusable component libraries and design system primitives
- Implementing compound components or context-driven UI assemblies
- Leveraging React 19 ref-as-prop conventions

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Component Architecture | HIGH | `architecture-` |
| 2 | State Management | MEDIUM-HIGH | `state-` |
| 3 | Implementation Patterns | MEDIUM | `patterns-` |
| 4 | React 19 Primitives | MEDIUM | `react19-` |

## Quick Reference

### 1. Component Architecture
- `architecture-avoid-boolean-props`: Replace boolean configuration flags with compound components or explicit variants.
- `architecture-compound-components`: Use compound components (`Menu.Root`, `Menu.Item`) with React Context to share state implicitly.

### 2. State Management
- `state-context-interface`: Design explicit Context interfaces with typed state and updater functions, guarding against missing providers.
- `state-decouple-implementation`: Separate state orchestration into headless hooks (`useMenuState`) for reuse and testability.

### 3. Implementation Patterns
- `patterns-children-over-render-props`: Prefer composition via `children` over render props where possible; reserve render props for parameterized slot rendering.
- `patterns-explicit-variants`: Use explicit string unions (`variant="primary" | "secondary" | "danger"`) instead of multiple boolean flags (`primary`, `secondary`).

### 4. React 19 Primitives
- `react19-no-forwardref`: In React 19, `ref` is a standard prop. Pass `ref` directly as a prop; do not wrap components in `forwardRef`.
