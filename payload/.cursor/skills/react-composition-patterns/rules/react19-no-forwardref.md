# React 19 Ref as Prop (`react19-no-forwardref`)

In React 19, `ref` is a standard prop. You no longer need `React.forwardRef` to pass refs down to DOM elements or child components.

## React 18 (Deprecated)

```tsx
// Legacy React 18:
const Input = React.forwardRef<HTMLInputElement, InputProps>((props, ref) => {
  return <input ref={ref} {...props} />;
});
```

## React 19 (Idiomatic)

```tsx
// React 19: ref is a normal prop
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  ref?: React.Ref<HTMLInputElement>;
}

export function Input({ ref, className = "", ...props }: InputProps) {
  return <input ref={ref} className={`input ${className}`} {...props} />;
}
```
