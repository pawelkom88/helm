# Martin Fowler Code Smells Catalog

A comprehensive reference for diagnosing and eliminating the 24 canonical code smells defined in Martin Fowler's *Refactoring: Improving the Design of Existing Code (2nd Edition)*.

---

## Quick Reference Summary

| Code Smell | Core Symptom | Primary Remedy |
|---|---|---|
| **1. Mysterious Name** | Identifier fails to communicate intent (`d`, `temp`, `data`, `handle1`) | *Change Function Declaration*, *Rename Variable*, *Rename Field* |
| **2. Duplicated Code** | Similar logic or structure exists in multiple locations | *Extract Function*, *Pull Up Method*, *Substitute Algorithm* |
| **3. Long Function** | Function spans dozens of lines or performs multiple distinct jobs | *Extract Function*, *Replace Temp with Query*, *Decompose Conditional* |
| **4. Long Parameter List** | More than 3–4 parameters; difficult to understand and call | *Introduce Parameter Object*, *Preserve Whole Object* |
| **5. Global Data** | Unencapsulated mutable data accessible from anywhere | *Encapsulate Variable*, *Encapsulate Field* |
| **6. Mutable Data** | Unconstrained state mutation causing non-local side effects | *Encapsulate Variable*, *Split Variable*, *Separate Query from Modifier* |
| **7. Divergent Change** | One module is modified for multiple unrelated business reasons | *Split Phase*, *Extract Class*, *Extract Function* |
| **8. Shotgun Surgery** | A single requirement change forces minor edits across many files | *Move Function*, *Move Field*, *Combine Functions into Class* |
| **9. Feature Envy** | A function spends more time reading/writing another class's data | *Move Function*, *Extract Function then Move* |
| **10. Data Clumps** | Groups of 3+ data fields that always travel together | *Introduce Parameter Object*, *Extract Class*, *Create Value Object* |
| **11. Primitive Obsession** | Domain concepts represented as raw strings, numbers, or booleans | *Replace Primitive with Object*, *Introduce Value Object* |
| **12. Repeated Switches** | Duplicate `switch` / `if-else` blocks branching on the same type code | *Replace Conditional with Polymorphism*, *Lookup Table* |
| **13. Loops** | Imperative loop accumulation masking data pipeline intent | *Replace Loop with Pipeline* (`map`, `filter`, `reduce`) |
| **14. Lazy Element** | Function, class, or structure that adds indirection without value | *Inline Function*, *Inline Class*, *Collapse Hierarchy* |
| **15. Speculative Generality** | "Just in case" abstractions, unused hooks, or over-parameterization | *Collapse Hierarchy*, *Remove Parameter*, *Inline Function* |
| **16. Temporary Field** | Object fields that are populated and valid only during specific phases | *Extract Class*, *Introduce Special Case / Null Object* |
| **17. Message Chains** | Deep navigation chains like `a.getB().getC().getD().getValue()` | *Hide Delegate*, *Extract Function and Move* |
| **18. Middle Man** | Class where half the methods merely delegate to another class | *Remove Middle Man*, *Inline Function* |
| **19. Insider Trading** | Modules intimately inspecting each other's private fields/state | *Move Function*, *Hide Delegate*, *Replace Subclass with Delegate* |
| **20. Large Class (God Object)** | Class with too many instance variables, methods, and responsibilities | *Extract Class*, *Extract Superclass*, *Replace Type Code with Subclasses* |
| **21. Alternative Classes** | Classes with different method names doing the same work | *Change Function Declaration*, *Move Function*, *Extract Superclass* |
| **22. Data Class** | Anemic classes with only fields/getters/setters and zero domain logic | *Encapsulate Record*, *Move Function into Class* |
| **23. Refused Bequest** | Subclass reuses parent code but rejects its contract or interface | *Replace Subclass with Delegate*, *Extract Superclass* |
| **24. Comments (as Deodorant)**| Comments explaining confusing, convoluted code instead of fixing it | *Extract Function*, *Change Function Declaration*, *Introduce Assertion* |

---

## Detailed Smells & Detection Guidelines

### 1. Mysterious Name
* **Detection**: Read the identifier in isolation. If you cannot explain *what* it is, *why* it exists, or *what unit* it measures without inspecting the surrounding code, it is mysterious.
* **Bad**: `const d = 86400;`, `function proc(o: any) {}`
* **Remedy**: `const SECONDS_PER_DAY = 86400;`, `function calculateOrderDiscount(order: Order): Money {}`

### 2. Duplicated Code
* **Detection**: Identical or near-identical expressions, loops, or JSX structures in multiple files or methods.
* **Remedy**: *Extract Function* for identical logic; *Form Template Method* or pass functions as parameters for similar logic with small variations.

### 3. Long Function
* **Detection**: Any function longer than a single screenful (20–30 lines) or containing comments that act as paragraph headers (`// 1. Validate`, `// 2. Fetch`, `// 3. Calculate`).
* **Remedy**: Whenever you feel the need to write a comment explaining what a block of code does, extract that block into a well-named function.

### 4. Long Parameter List
* **Detection**: More than 3 positional parameters. Call sites are hard to read and prone to inverted argument bugs (e.g., `(width, height)` swapped).
* **Remedy**: Use *Introduce Parameter Object* to combine related arguments into a structured options object or domain type.

### 5. Primitive Obsession & Data Clumps
* **Detection**: Using raw numbers for monetary amounts, strings for email addresses/postal codes, or multiple date fields (`startDate`, `endDate`) passed side by side.
* **Remedy**:
  * Create **Value Objects** (`Money`, `EmailAddress`, `DateRange`).
  * Enforce invariants and validation inside the Value Object constructor.

### 6. Divergent Change vs. Shotgun Surgery
* **Divergent Change**: "I will have to change this class if the database schema changes, and ALSO if the financial tax calculation rules change." (Violates Single Responsibility Principle).
  * *Fix*: Split by axis of change using *Extract Class* or *Split Phase*.
* **Shotgun Surgery**: "Every time I add a new payment method, I have to touch 7 different files."
  * *Fix*: Consolidate related behavior using *Move Function*, *Move Field*, and *Replace Conditional with Polymorphism*.

### 7. Feature Envy
* **Detection**: Method `A` in Class `OrderProcessor` calls 6 getters on `Customer` (`customer.getAddress()`, `customer.getTier()`, `customer.getPoints()`).
* **Remedy**: The method belongs on `Customer`. Move it to the class that owns the data it manipulates.

### 8. Repeated Switches
* **Detection**: Multiple `switch (user.type)` or `if (type === 'A')` spread across controllers, calculations, and formatters.
* **Remedy**:
  * Replace with polymorphic classes (strategy pattern).
  * For functional codebases, replace with a dedicated lookup table/record map.

### 9. Message Chains & Middle Man
* **Message Chains**: Law of Demeter violation (`order.getCustomer().getAddress().getZipCode()`).
  * *Fix*: *Hide Delegate* (`order.getCustomerZipCode()`).
* **Middle Man**: Over-encapsulation where a wrapper class does nothing but forward calls.
  * *Fix*: *Remove Middle Man* and let callers talk to the underlying delegate directly.

### 10. Comments as Deodorant
* **Detection**: A block of code begins with a comment like `// check if user is eligible for senior citizen holiday discount`.
* **Remedy**: Extract the expression into a function or variable named `isSeniorHolidayDiscountEligible()`. The comment becomes redundant and should be deleted.
