# Decouple State Logic from UI (`state-decouple-implementation`)

Separate state management and business logic into headless custom hooks so logic can be tested without mounting DOM and components can be easily rewritten or restyled.

## Pattern

```tsx
import { useState, useCallback } from "react";

export interface DisclosureState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
}

export function useDisclosure(initialState = false): DisclosureState {
  const [isOpen, setIsOpen] = useState(initialState);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  return { isOpen, open, close, toggle };
}

// UI component simply wires the headless hook
export function CollapsibleSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const { isOpen, toggle } = useDisclosure(false);

  return (
    <div className="collapsible">
      <button onClick={toggle} aria-expanded={isOpen} className="collapsible-header">
        {title}
      </button>
      {isOpen && <div className="collapsible-body">{children}</div>}
    </div>
  );
}
```
