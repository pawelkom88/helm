# Context Interface Design (`state-context-interface`)

When creating React Context for shared component state, expose an explicit, strictly typed interface and provide a custom hook that asserts provider existence.

## Pattern

```tsx
import { createContext, useContext, useMemo, useState } from "react";

interface AccordionContextValue {
  openItems: ReadonlySet<string>;
  toggleItem: (id: string) => void;
  allowsMultiple: boolean;
}

const AccordionContext = createContext<AccordionContextValue | null>(null);

export function useAccordionContext(): AccordionContextValue {
  const ctx = useContext(AccordionContext);
  if (!ctx) {
    throw new Error("Accordion compound components must be rendered inside an <Accordion.Root>");
  }
  return ctx;
}

export function AccordionProvider({
  allowsMultiple = false,
  children,
}: {
  allowsMultiple?: boolean;
  children: React.ReactNode;
}) {
  const [openItems, setOpenItems] = useState<Set<string>>(() => new Set());

  const value = useMemo<AccordionContextValue>(() => ({
    openItems,
    allowsMultiple,
    toggleItem: (id: string) => {
      setOpenItems((prev) => {
        const next = new Set(allowsMultiple ? prev : []);
        if (prev.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    },
  }), [openItems, allowsMultiple]);

  return <AccordionContext.Provider value={value}>{children}</AccordionContext.Provider>;
}
```
