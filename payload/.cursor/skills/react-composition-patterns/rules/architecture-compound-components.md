# Compound Components (`architecture-compound-components`)

Use compound components when multiple related components need to share implicit state and coordinate behavior without manual prop drilling.

## Pattern

```tsx
import React, { createContext, useContext, useState } from "react";

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("Tabs compound components must be used within <Tabs.Root>");
  }
  return context;
}

export function TabsRoot({
  defaultTab,
  children,
}: {
  defaultTab: string;
  children: React.ReactNode;
}) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className="tabs-container">{children}</div>
    </TabsContext.Provider>
  );
}

export function TabList({ children }: { children: React.ReactNode }) {
  return <div role="tablist" className="tabs-list">{children}</div>;
}

export function TabTrigger({ id, children }: { id: string; children: React.ReactNode }) {
  const { activeTab, setActiveTab } = useTabs();
  const isSelected = activeTab === id;
  return (
    <button
      role="tab"
      aria-selected={isSelected}
      className={`tab-trigger ${isSelected ? "active" : ""}`}
      onClick={() => setActiveTab(id)}
    >
      {children}
    </button>
  );
}

export function TabPanel({ id, children }: { id: string; children: React.ReactNode }) {
  const { activeTab } = useTabs();
  if (activeTab !== id) return null;
  return <div role="tabpanel" className="tab-panel">{children}</div>;
}

export const Tabs = {
  Root: TabsRoot,
  List: TabList,
  Trigger: TabTrigger,
  Panel: TabPanel,
};
```
