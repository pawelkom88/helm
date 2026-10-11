# Avoid Boolean Prop Proliferation (`architecture-avoid-boolean-props`)

Components with many boolean flags (`isCompact`, `showFooter`, `hasBorder`, `isModal`, `withIcon`) become brittle, unmaintainable, and difficult to customize.

## Anti-Pattern

```tsx
// Bad: Boolean flags dictate layout and rendering
function Card({
  title,
  content,
  showFooter,
  footerText,
  isCompact,
  hasBorder,
  withHeaderAction,
  onAction,
}: CardProps) {
  return (
    <div className={`card ${isCompact ? "compact" : ""} ${hasBorder ? "border" : ""}`}>
      <div className="card-header">
        <h3>{title}</h3>
        {withHeaderAction && <button onClick={onAction}>Action</button>}
      </div>
      <div className="card-body">{content}</div>
      {showFooter && <div className="card-footer">{footerText}</div>}
    </div>
  );
}
```

## Pattern: Composition via Slots / Compound Components

```tsx
// Good: Composable sub-components
function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>;
}

Card.Header = function CardHeader({ children }: { children: React.ReactNode }) {
  return <div className="card-header">{children}</div>;
};

Card.Body = function CardBody({ children }: { children: React.ReactNode }) {
  return <div className="card-body">{children}</div>;
};

Card.Footer = function CardFooter({ children }: { children: React.ReactNode }) {
  return <div className="card-footer">{children}</div>;
};

// Usage
<Card className="border">
  <Card.Header>
    <h3>Order Summary</h3>
    <button onClick={handleAction}>Action</button>
  </Card.Header>
  <Card.Body>Details...</Card.Body>
  <Card.Footer>Footer info</Card.Footer>
</Card>
```
