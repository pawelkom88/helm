# Prefer Children Over Render Props (`patterns-children-over-render-props`)

Prefer standard `children` composition over render prop functions (`renderItem={(item) => ...}`) unless the component truly produces internal data that callers must consume per element.

## Guidelines

- If the child component does not need arguments passed from the parent, pass React nodes via `children` or named slots (`leadingAccessory`, `trailingAccessory`).
- Reserve render props strictly for iterators/virtual lists where items are computed inside the container.
- For modal dialogs, cards, toolbars, and layouts, use slot props or children.

## Example

```tsx
// Prefer slot props over render functions for static layout
interface DialogProps {
  title: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

export function Dialog({ title, actions, children }: DialogProps) {
  return (
    <div className="dialog">
      <div className="dialog-title">{title}</div>
      <div className="dialog-content">{children}</div>
      {actions && <div className="dialog-actions">{actions}</div>}
    </div>
  );
}
```
