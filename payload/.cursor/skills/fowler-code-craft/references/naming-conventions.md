# Intent-Revealing Naming Standards & Anti-Patterns

A comprehensive naming rubric grounded in Martin Fowler's naming heuristics, Kent Beck's *Implementation Patterns*, and Robert C. Martin's *Clean Code*.

---

## 🎯 The Core Test of a Name

A well-crafted name must answer three questions without requiring inspection of the implementation:
1. **Why does it exist?** (Domain purpose)
2. **What does it do?** (Responsibility or value produced)
3. **How is it used?** (Type, unit, or contract expectations)

> *“If a name requires a comment to explain it, the name is a failure.”* — Martin Fowler

---

## 🚫 The Banished Noise Words & Badges

Eliminate meaningless filler words that add character count without conveying information:

| Noise Word | Problem | Better Alternative |
|---|---|---|
| `Data` / `Info` (`UserData`, `OrderInfo`) | Redundant; every object contains data. | `User`, `UserProfile`, `OrderSummary`, `OrderSnapshot` |
| `Manager` / `Handler` / `Processor` | Vague catch-all that masks multiple responsibilities. | Split into specific roles: `OrderValidator`, `PaymentGateway`, `InvoicePublisher` |
| `Helper` / `Util` | Junk drawer for code with unclear ownership. | Domain class, pure function library (e.g., `DateFormatter`, `CurrencyConverter`) |
| `temp` / `tmp` / `item` / `val` / `obj` | Communicates nothing about intent or lifespan. | Name the concrete domain concept (`pendingOrder`, `expiredToken`, `userRecord`) |
| `flag` / `statusFlag` | Ambiguous boolean or state variable. | Specify condition: `isEmailVerified`, `hasActiveSubscription`, `canRetry` |
| Hungarian prefixes (`strName`, `iCount`, `arrList`) | Leaks implementation types; decays when types change. | `customerName`, `retryCount`, `activeUsers` |

---

## 🏷️ Syntactic Naming Rules by Construct

### 1. Variables & Constants
* **Domain Entities**: Use clear nouns or noun phrases: `activeSubscription`, `billingAddress`.
* **Units & Metrics**: Always incorporate units when values represent measurements:
  * ❌ `timeout = 5000` → ✅ `timeoutInMs = 5000`
  * ❌ `delay = 10` → ✅ `delaySeconds = 10`
  * ❌ `fileSize = 1024` → ✅ `fileSizeBytes = 1024`
* **Collections & Plurals**:
  * Use natural plurals: `customers`, `invoices`.
  * For distinct collections, qualify by purpose: `activeCustomersList`, `ordersByCustomerIdMap`.

### 2. Booleans & Predicates
Never name a boolean with a noun or ambiguous verb. Always phrase booleans as **truth statements** or **modal assertions**:

* **State checks**: Prefix with `is`, `has`, `was`, `contains`:
  * ✅ `isOpen`, `isArchived`, `hasDiscountApplied`, `containsForbiddenWords`
  * ❌ `open` (could be an action), `discount` (sounds like an object or number)
* **Capability / Permission checks**: Prefix with `can`, `should`, `allows`:
  * ✅ `canCheckout`, `canCancelOrder`, `shouldSendNotification`, `allowsRefund`
  * ❌ `checkoutAllowed`, `sendEmailFlag`
* **Negated Booleans (Avoid Double Negatives)**:
  * ❌ `isNotInvalid`, `disableFeature = false`
  * ✅ `isValid`, `isFeatureEnabled = true`

### 3. Functions & Methods
* **Commands (Side Effects / State Changes)**: Must begin with a strong, imperative verb:
  * `createCustomer()`, `cancelSubscription()`, `archiveInvoice()`, `publishDomainEvent()`
* **Queries (Pure Calculations / Retrieval)**: Use nouns, adjective phrases, or descriptive query verbs:
  * ✅ `calculateDiscountedTotal()`, `findCustomerById()`, `latestOrder()`
  * ❌ `process()`, `doWork()`, `handle()`
* **Boolean Predicate Methods**: Must start with `is`, `has`, `can`, or `should`:
  * `isOverdue()`, `hasAvailableStock()`, `canApplyCoupon()`

---

## 🏛️ Architectural Pattern Naming (PoEAA Suffixes)

When introducing enterprise patterns, use recognized pattern suffixes to immediately telegraph the architectural boundary:

| Pattern Role | Canonical Suffix | Example |
|---|---|---|
| **Value Object** | Self-describing domain concept (no suffix) | `Money`, `EmailAddress`, `PostalCode`, `DateRange` |
| **Repository** | `*Repository` | `UserRepository`, `OrderRepository` |
| **Gateway** | `*Gateway` (External system wrapper) | `StripePaymentGateway`, `SendGridEmailGateway` |
| **Data Transfer Object** | `*Dto` or `*Payload` | `CreateUserDto`, `OrderResponseDto` |
| **Domain Service** | `*Service` | `OrderFulfillmentService`, `PricingService` |
| **Specification / Policy**| `*Policy` or `*Specification` | `PasswordComplexityPolicy`, `DiscountEligibilitySpecification` |
| **Mapper** | `*Mapper` | `UserEntityToDtoMapper`, `DatabaseRowMapper` |

---

## 🔍 Naming Audit Checklist

When reviewing code or designing a refactoring:
- [ ] Are single-letter variables restricted exclusively to loop counters (`i`, `j`) in scopes < 5 lines?
- [ ] Can every method's intent be understood without looking inside its curly braces?
- [ ] Are parameter lists free of boolean flags (`doSomething(data, true, false)`)? (Use named parameters or separate methods instead: `enableFeature()` / `disableFeature()`).
- [ ] Are domain terms consistent across the entire codebase (e.g., sticking with `customer` instead of oscillating between `client`, `account`, and `user`)?
- [ ] Have all noise words (`Data`, `Info`, `Helper`, `Manager`) been eliminated or refactored into distinct responsibilities?
