# Martin Fowler Refactoring Patterns Catalog

A reference catalog of core behavior-preserving micro-refactorings based on Martin Fowler's *Refactoring: Improving the Design of Existing Code (2nd Edition)*.

---

## ✂️ 1. Composing Functions

### Extract Function
* **Intent**: Turn a code fragment into a standalone function whose name explains its purpose.
* **When to Use**: When a block of code requires effort or comments to understand, or when the same code is repeated.
* **Idiom**:
  ```typescript
  // Before
  function printOwing(invoice: Invoice) {
    printBanner();
    let outstanding = 0;
    for (const o of invoice.orders) outstanding += o.amount;
    recordDueDate(invoice);
    printDetails(invoice, outstanding);
  }

  // After
  function printOwing(invoice: Invoice) {
    printBanner();
    const outstanding = calculateOutstanding(invoice);
    recordDueDate(invoice);
    printDetails(invoice, outstanding);
  }
  function calculateOutstanding(invoice: Invoice): number {
    return invoice.orders.reduce((sum, order) => sum + order.amount, 0);
  }
  ```

### Extract Variable / Inline Variable
* **Intent**: Put the result of a complex expression into a temporary variable with an intent-revealing name.
* **When to Use**: Complex boolean logic or nested property calculations.
* **Idiom**:
  ```typescript
  // Before
  if (platform.toUpperCase().includes('MAC') && browser.toUpperCase().includes('IE') && wasInitialized() && resize > 0)

  // After
  const isMac = platform.toUpperCase().includes('MAC');
  const isIE = browser.toUpperCase().includes('IE');
  const wasResized = resize > 0;
  if (isMac && isIE && wasInitialized() && wasResized)
  ```

### Change Function Declaration (Rename / Reshape Signature)
* **Intent**: Change a function's name, add/remove parameters, or change parameter order to better reflect its contract.
* **Safety Rule**: Use a transitional deprecated wrapper to avoid breaking existing callers if refactoring public APIs across multiple modules.

### Introduce Parameter Object
* **Intent**: Replace a group of parameters that naturally travel together with a single structured object.
* **When to Use**: When functions take 3+ related arguments (e.g., `(startDate, endDate, timezone)`).

### Split Phase
* **Intent**: Divide code that does two distinct things into separate consecutive stages (e.g., parsing/validation stage followed by execution/rendering stage).
* **When to Use**: When business computation is intertwined with data fetching, formatting, or presentation.

---

## 🛡️ 2. Encapsulation & Data Structure Refactorings

### Encapsulate Variable / Record
* **Intent**: Restrict direct access to data by wrapping it behind getter/setter functions or domain methods.
* **When to Use**: Global data or mutable shared state.

### Replace Primitive with Object (Value Object)
* **Intent**: Replace a simple string, number, or boolean with a dedicated domain class or branded type that validates its own rules.
* **When to Use**: Phone numbers, currency values, postal codes, email addresses.

### Replace Temp with Query
* **Intent**: Extract the calculation of an expression into a method, replacing temporary variables with direct function calls.
* **When to Use**: When a temporary variable is used multiple times across a long function.

### Hide Delegate & Remove Middle Man
* **Hide Delegate**: If a client calls `department = person.getDepartment(); manager = department.getManager();`, provide `person.getManager()` to reduce client coupling.
* **Remove Middle Man**: If a class does nothing but forward every method to a delegate, remove the wrapper and let callers interact directly.

---

## 🔀 3. Moving Features

### Move Function & Move Field
* **Intent**: Move a function or field to the class/module that uses it most frequently.
* **When to Use**: *Feature Envy* smell.

### Split Loop & Replace Loop with Pipeline
* **Intent**: Separate a loop doing multiple calculations into distinct loops, then replace imperative loops with collection pipelines (`map`, `filter`, `reduce`).
* **Idiom**:
  ```typescript
  // Before
  const activeUserEmails: string[] = [];
  for (const user of users) {
    if (user.isActive) activeUserEmails.push(user.email);
  }

  // After
  const activeUserEmails = users
    .filter(user => user.isActive)
    .map(user => user.email);
  ```

### Slide Statements
* **Intent**: Move related statements adjacent to each other to clarify data flow before extracting a function.

---

## ⚡ 4. Simplifying Conditionals

### Decompose Conditional
* **Intent**: Extract condition checks and branch bodies into clear, well-named functions.
* **Idiom**:
  ```typescript
  // Before
  if (!date.isBefore(plan.summerStart) && !date.isAfter(plan.summerEnd)) {
    charge = quantity * plan.summerRate;
  } else {
    charge = quantity * plan.regularRate + plan.regularServiceCharge;
  }

  // After
  if (isSummer(date, plan)) {
    charge = calculateSummerCharge(quantity, plan);
  } else {
    charge = calculateRegularCharge(quantity, plan);
  }
  ```

### Replace Nested Conditional with Guard Clauses
* **Intent**: Use early returns for special cases to avoid deep indentation and make the "happy path" prominent.
* **Idiom**:
  ```typescript
  // Before
  function getPayAmount() {
    let result;
    if (isDead) {
      result = deadAmount();
    } else {
      if (isSeparated) {
        result = separatedAmount();
      } else {
        if (isRetired) {
          result = retiredAmount();
        } else {
          result = normalPayAmount();
        }
      }
    }
    return result;
  }

  // After
  function getPayAmount() {
    if (isDead) return deadAmount();
    if (isSeparated) return separatedAmount();
    if (isRetired) return retiredAmount();
    return normalPayAmount();
  }
  ```

### Replace Conditional with Polymorphism / Lookup Table
* **Intent**: Replace duplicate type-switching logic with polymorphic classes or dictionary dispatch.
* **When to Use**: *Repeated Switches* smell.
