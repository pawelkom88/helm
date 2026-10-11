---
name: vercel-react-best-practices
description: React 19 and Vite performance optimization guidelines tailored from Vercel Engineering. Use when writing, reviewing, or refactoring client-side React code, components, hooks, state management, render lifecycles, and Vite bundle performance.
license: MIT
metadata:
  author: vercel
  version: "1.0.0"
---

# Vercel React Best Practices (Client & Vite / React 19)

Comprehensive performance optimization guide for React 19 applications built with Vite. Focused exclusively on client-side rendering performance, state derive patterns, re-render avoidance, JavaScript efficiency, and client data flows.

## When to Apply

Reference these guidelines when:
- Building or refactoring React 19 components and hooks
- Eliminating client-side async waterfalls and slow data flows
- Optimizing component re-renders, state transitions, and deferred updates
- Reducing client bundle size and tuning Vite / ESM chunk splitting
- Reviewing React component architecture and rendering efficiency

## Rule Categories by Priority

| Priority | Category | Impact | Focus |
|----------|----------|--------|-------|
| 1 | Eliminating Waterfalls | CRITICAL | Promise parallelization, deferred awaits, Suspense boundaries |
| 2 | Bundle Size Optimization | CRITICAL | Direct imports, dynamic imports, code splitting |
| 3 | Client Data & Event Handling | HIGH | Request deduplication, passive event listeners, storage caching |
| 4 | Re-render Optimization | MEDIUM-HIGH | Derived state, functional updates, lazy state, transition boundaries |
| 5 | Rendering Performance | MEDIUM | Hoisting JSX, content-visibility, SVG animations |
| 6 | JavaScript Performance | MEDIUM | Map/Set lookups, loop batching, immutable sorting, early exit |
| 7 | Advanced Patterns | MEDIUM-LOW | `useEffectEvent` alternatives, latest refs, mount guards |

---

## 1. Eliminating Waterfalls (CRITICAL)

### `async-parallel`: Parallelize Independent Promises
Never await independent async operations sequentially.
```tsx
// Bad: Sequential waterfall
const user = await fetchUser();
const config = await fetchConfig();

// Good: Parallel execution
const [user, config] = await Promise.all([fetchUser(), fetchConfig()]);
```

### `async-defer-await`: Defer Await into Branches Where Used
Do not await promises at the top level if they are only needed in conditional branches or error paths.
```tsx
// Good: Await inside condition
async function loadView(mode: string, dataPromise: Promise<Data>) {
  if (mode === "cached") return renderCached();
  const data = await dataPromise;
  return renderFull(data);
}
```

### `async-cheap-condition-before-await`: Check Sync Conditions First
Check cheap local/synchronous variables (e.g. cached memory, feature flags, prop guards) before initiating network queries or awaiting async values.

### `async-suspense-boundaries`: Granular Suspense Boundaries
Wrap distinct visual sections in granular `<Suspense>` boundaries so slow async components stream in without blocking fast interactive headers or navigation.

---

## 2. Bundle Size Optimization (CRITICAL)

### `bundle-barrel-imports`: Direct Module Imports
Avoid importing from monolithic barrel files (`index.ts`) in heavy libraries (e.g. `lucide-react`, `lodash`, design system components).
```tsx
// Bad: Pulls in large index re-exports
import { Search } from "lucide-react";

// Good: Import from leaf path
import Search from "lucide-react/dist/esm/icons/search";
```

### `bundle-dynamic-imports`: Lazy Load Infrequent / Heavy Components
Use `React.lazy()` for heavy modals, rich text editors, charts, and administrative panels not required on first paint.
```tsx
const RichEditor = React.lazy(() => import("./RichEditor"));
```

### `bundle-conditional`: Load Modules Only on Feature Activation
Do not bundle feature libraries statically if the user might never trigger the feature (e.g. PDF export, XLSX parse). Import dynamically inside the click handler:
```tsx
async function handleExport() {
  const { exportToPdf } = await import("./pdfExporter");
  exportToPdf(data);
}
```

---

## 3. Client Data & Event Handling (HIGH)

### `client-swr-dedup`: Automatic Request Deduplication
Deduplicate client queries for the same resources across multiple mounted components using TanStack Query or SWR rather than raw `useEffect` fetches.

### `client-event-listeners`: Deduplicate Global Listeners
Never bind duplicate `window.addEventListener('resize')` or scroll listeners across child components. Register a single listener in a root hook or provider.

### `client-passive-event-listeners`: Use Passive Listeners for Touch/Scroll
Always pass `{ passive: true }` when adding scroll or touch event listeners to ensure smooth 60fps main-thread scrolling.

---

## 4. Re-render Optimization (MEDIUM-HIGH)

### `rerender-derived-state-no-effect`: Derive State During Render
If a value can be computed from current props or state, never store it in state or synchronize it via `useEffect`. Calculate it inline during render.
```tsx
// Bad
const [fullName, setFullName] = useState("");
useEffect(() => { setFullName(first + " " + last); }, [first, last]);

// Good
const fullName = first + " " + last;
```

### `rerender-functional-setstate`: Functional Updates for Stable Handlers
Pass updater functions `setState(prev => ...)` so callbacks don't depend on changing state variables.
```tsx
// Good: Handler does not need `count` in dependency array
const increment = useCallback(() => setCount(c => c + 1), []);
```

### `rerender-lazy-state-init`: Pass Function to useState for Expensive Values
Never compute expensive initialization inline in `useState(expensiveCompute())`. Pass an initializer function: `useState(() => expensiveCompute())`.

### `rerender-no-inline-components`: Never Define Components Inside Components
Defining a component inside another component creates a new component reference on every render, destroying its state and remounting child DOM.
```tsx
// Bad
function Parent() {
  function Child() { return <div />; }
  return <Child />;
}

// Good: Hoist outside
function Child() { return <div />; }
function Parent() { return <Child />; }
```

### `rerender-transitions`: Use startTransition for Non-Urgent State Updates
Keep user typing, clicking, and tab navigation snappy by wrapping secondary visual updates or filter updates in React's `startTransition`:
```tsx
function onSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
  setInput(e.target.value); // Urgent: keeps typing fluid
  startTransition(() => {
    setSearchQuery(e.target.value); // Non-urgent: deferred update
  });
}
```

### `rerender-use-deferred-value`: Defer Heavy List Renders
Use `useDeferredValue` when filtering or re-rendering large datasets in response to interactive input.

---

## 5. Rendering Performance (MEDIUM)

### `rendering-hoist-jsx`: Hoist Static Elements
Extract static JSX elements (icons, badges, headers that never change) outside the render function to avoid recreating React element objects on every tick.

### `rendering-content-visibility`: Use CSS content-visibility for Long Lists
For long vertical documents or feeds, apply `content-visibility: auto; contain-intrinsic-size: 0 500px;` so browsers skip layout calculations for offscreen elements.

### `rendering-animate-svg-wrapper`: Animate Container Div, Not SVG
Animate wrapper `<div>` with GPU-accelerated CSS transforms (`translate3d`, `scale`) instead of mutating SVG attributes directly.

---

## 6. JavaScript Performance (MEDIUM)

### `js-set-map-lookups`: Use Set/Map for Frequent Lookups
Replace `array.includes(id)` with `set.has(id)` (O(1) instead of O(N)) when filtering or matching across datasets.

### `js-tosorted-immutable`: Use toSorted() Instead of slice().sort()
In modern JavaScript runtimes, use `array.toSorted()` and `array.toReversed()` for immutable sorting without copying arrays first.

### `js-early-exit`: Early Exit in Render and Calculations
Place guard clauses and cheap short-circuit checks at the start of functions to minimize wasted compute.

---

## 7. Advanced Patterns (MEDIUM-LOW)

### `advanced-use-latest`: Use Ref for Transient Callback Values
When an event listener or interval needs access to the latest prop or state without re-subscribing, store the value in a ref that updates on each render:
```tsx
function useLatest<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
```

### `advanced-init-once`: Guard Against Duplicate Mounts
For external subscriptions or third-party SDK initializations, use a ref flag or effect cleanup to guarantee idempotent initialization.
