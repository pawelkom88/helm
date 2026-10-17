---
name: state-machines
description: Model multi-step UI or async flows (wizards, auth, checkout, upload, retry/cancel) as explicit state machines instead of boolean flags. Use when a task has 3+ interacting flags, impossible-state bugs, or a flow with named steps. Skip for simple toggles and plain forms.
---

# State machines (use when they pay for themselves)

## Decide first
Use one when ANY holds: 3+ booleans that interact (`isLoading && !isError && hasData`), a flow with named steps, async work that can retry or cancel, a bug report of an "impossible" UI state.
Do not use for a single toggle, a plain form, or data fetching alone (TanStack Query already models idle/loading/error/success).

## Pick the lightest tool
1. **Discriminated union + `useReducer`** (no dependency). Default. Enough for most flows.
2. **XState v5**: only if already in `package.json` or the human approved adding it. Never add it silently.

## Model before coding
Write this in the plan (≤15 lines): states, events, allowed transitions, guards, side effects, initial and final states. Anything not listed is an invalid transition and is ignored, not guessed.

## Rules
- One `status` field that is a union (`'idle' | 'editing' | 'submitting' | 'done' | 'failed'`), never parallel booleans. Carry per-state data inside the state (`{ status: 'failed'; error: string }`).
- The transition function is pure: `(state, event) => state`. Side effects (requests, navigation) live outside it, triggered by state changes or event handlers.
- Exhaustive `switch` with a `never` check so a new state or event fails to compile.
- Server data stays in TanStack Query. The machine owns the flow (step, submitting, dismissed), not the fetched data.
- Validate external event payloads with Zod before they enter the machine.
- Test the transition function directly with Vitest: every valid transition, plus at least one invalid event per state. Add Playwright only for the end-to-end journey.
- If you can't draw it in ≤12 lines, split the flow into smaller machines.
