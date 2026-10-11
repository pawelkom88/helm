---
name: tanstack-query
description: TanStack Query v5 client-state best practices for data fetching, caching, mutations, optimistic updates, and cache invalidation in React 19 applications.
license: MIT
metadata:
  upstream: DeckardGer/tanstack-agent-skills
  commit: b2fc14c974b2ca09b38de09c28237f240175205b
  version: "5.0.0"
---

# TanStack Query v5 Best Practices (Client State)

Comprehensive guidelines for implementing TanStack Query v5 (React Query) in React applications. Focused exclusively on client-side data management, caching strategies, mutations, optimistic updates, and render optimization.

## When to Apply

Reference these guidelines when:
- Creating queries and data-fetching hooks with `useQuery` or `useQueries`
- Configuring `QueryClient`, `staleTime`, and `gcTime`
- Writing mutations with `useMutation` and managing cache updates or optimistic rollbacks
- Structuring query keys and designing Query Key Factories
- Implementing pagination or infinite lists with `useInfiniteQuery`

## Core Concepts & Priority Guidelines

| Area | Focus | Key v5 Conventions |
|------|-------|-------------------|
| **Query Keys** | Structure & Uniqueness | Keys MUST be arrays; include all parameters; use factories |
| **Caching** | Freshness & Memory | `staleTime` vs `gcTime` (renamed from `cacheTime`); default `0` |
| **Mutations** | Data Consistency | `onSuccess` invalidation; `onMutate` optimistic rollback |
| **Query Cancellation**| Request Lifecycle | Pass `signal` from QueryFunctionContext to fetch/axios |
| **Performance** | Render Discipline | Use `select` for fine-grained subscriptions; avoid extra renders |

---

## 1. Query Keys (v5 Standard)

### Keys Must Always Be Arrays
In TanStack Query v5, query keys must always be an array:
```tsx
// ❌ Invalid in v5
useQuery({ queryKey: "todos", queryFn: fetchTodos });

// ✅ Valid in v5
useQuery({ queryKey: ["todos"], queryFn: fetchTodos });
```

### Query Key Factory Pattern
Organize query keys centrally using factory objects to prevent typo-driven cache misses:
```tsx
export const todoKeys = {
  all: ["todos"] as const,
  lists: () => [...todoKeys.all, "list"] as const,
  list: (filters: TodoFilters) => [...todoKeys.lists(), filters] as const,
  details: () => [...todoKeys.all, "detail"] as const,
  detail: (id: string) => [...todoKeys.details(), id] as const,
};

// Usage:
useQuery({
  queryKey: todoKeys.detail(id),
  queryFn: ({ signal }) => fetchTodoById(id, { signal }),
});
```

### Include All Dependencies in Keys
Every variable that affects the query function's output must be included in the query key:
```tsx
// ✅ Correct: page and filter are part of the key
useQuery({
  queryKey: todoKeys.list({ status, page }),
  queryFn: ({ signal }) => fetchTodos({ status, page, signal }),
});
```

---

## 2. Caching & Freshness (`staleTime` vs `gcTime`)

- **`staleTime`**: Duration (ms) data is considered fresh. Fresh data is served directly from cache without background refetch. Default is `0` (instantly stale).
- **`gcTime`** *(formerly `cacheTime`)*: Duration (ms) inactive/unmounted query data stays in memory before garbage collection. Default is 5 minutes (`5 * 60 * 1000`).

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute freshness
      gcTime: 10 * 60 * 1000, // 10 minutes before memory purge
      refetchOnWindowFocus: false, // Turn off for predictable developer experience
      retry: (failureCount, error) => {
        // Do not retry 4xx client errors
        if ((error as any)?.status >= 400 && (error as any)?.status < 500) return false;
        return failureCount < 3;
      },
    },
  },
});
```

---

## 3. Mutations & Invalidation

### Always Invalidate Related Queries
After mutation success, invalidate queries to fetch fresh server state:
```tsx
const queryClient = useQueryClient();

const createTodoMutation = useMutation({
  mutationFn: createTodo,
  onSuccess: () => {
    // Invalidate all todo lists hierarchically
    queryClient.invalidateQueries({ queryKey: todoKeys.lists() });
  },
});
```

### Optimistic Updates with Rollback
Use `onMutate` to snapshot previous data and update the cache immediately. Roll back in `onError`:
```tsx
const updateTodoMutation = useMutation({
  mutationFn: updateTodo,
  onMutate: async (newTodo) => {
    // 1. Cancel outgoing queries so they don't overwrite optimistic update
    await queryClient.cancelQueries({ queryKey: todoKeys.detail(newTodo.id) });

    // 2. Snapshot previous value
    const previousTodo = queryClient.getQueryData(todoKeys.detail(newTodo.id));

    // 3. Optimistically update cache
    queryClient.setQueryData(todoKeys.detail(newTodo.id), (old: any) => ({
      ...old,
      ...newTodo,
    }));

    // 4. Return rollback context
    return { previousTodo };
  },
  onError: (err, newTodo, context) => {
    // 5. Rollback on failure
    if (context?.previousTodo) {
      queryClient.setQueryData(todoKeys.detail(newTodo.id), context.previousTodo);
    }
  },
  onSettled: (newTodo) => {
    // 6. Always refetch on settlement to ensure canonical state
    if (newTodo?.id) {
      queryClient.invalidateQueries({ queryKey: todoKeys.detail(newTodo.id) });
    }
  },
});
```

---

## 4. Query Cancellation

Always consume `signal` from `QueryFunctionContext` to allow TanStack Query to abort in-flight requests when components unmount or queries change:
```tsx
useQuery({
  queryKey: todoKeys.detail(id),
  queryFn: async ({ signal }) => {
    const response = await fetch(`/api/todos/${id}`, { signal });
    if (!response.ok) throw new Error("Network error");
    return response.json();
  },
});
```

---

## 5. Infinite Queries (v5 Standard)

In v5, `initialPageParam` is **required** in `useInfiniteQuery`:
```tsx
useInfiniteQuery({
  queryKey: todoKeys.lists(),
  initialPageParam: 1, // Required in v5
  queryFn: ({ pageParam, signal }) => fetchTodos({ page: pageParam, signal }),
  getNextPageParam: (lastPage) => lastPage.nextPage ?? undefined,
  maxPages: 5, // Prevent unbounded DOM / memory growth
});
```

---

## 6. Fine-Grained Subscriptions with `select`

Use `select` to transform data and subscribe only to derived fields. The component will only re-render if the selected value changes:
```tsx
// Component re-renders ONLY when todoCount changes, not when other todo attributes change
const { data: todoCount } = useQuery({
  queryKey: todoKeys.lists(),
  queryFn: fetchTodos,
  select: (data) => data.todos.length,
});
```
