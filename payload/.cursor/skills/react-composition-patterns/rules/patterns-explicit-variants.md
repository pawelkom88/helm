# Explicit Variants Over Booleans (`patterns-explicit-variants`)

Avoid boolean props representing exclusive states (`primary`, `secondary`, `destructive`). Use an explicit string union `variant` prop.

## Anti-Pattern

```tsx
// Confusing: What happens if both primary and secondary are passed?
<Button primary secondary />
```

## Pattern

```tsx
type ButtonVariant = "primary" | "secondary" | "destructive" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`btn btn-${variant} btn-${size} ${className}`}
      {...props}
    />
  );
}
```
