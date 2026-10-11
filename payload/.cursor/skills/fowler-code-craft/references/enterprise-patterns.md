# Enterprise Architecture Patterns (PoEAA) in Refactoring

A practical guide to applying Martin Fowler's *Patterns of Enterprise Application Architecture* (PoEAA) to elevate code from disorganized procedural scripts into clean, decoupled, and maintainable systems.

---

## 🏗️ 1. Domain Logic Architecture

When business logic grows messy, choose the appropriate domain logic structure:

### Transaction Script → Domain Model
* **The Problem (Smell: Anemic Domain Model / God Method)**:
  * Business logic is written as a procedural script inside controllers or route handlers, directly querying SQL and manipulating bare database records.
* **The PoEAA Pattern**:
  * **Transaction Script**: Suitable only for simple CRUD operations with virtually no business rules.
  * **Domain Model**: An object-oriented network where entities encapsulate both business state and business behavior. Invariants are protected inside the domain objects.
* **Refactoring Move**:
  * Identify business calculations in the transaction script.
  * Move calculations into the domain entities (using *Move Function*).
  * Convert dumb data structures into encapsulated Domain Entities with private state and expressive methods.

### Service Layer
* **The Problem (Smell: Divergent Change & Mixed Concerns)**:
  * API controllers or CLI entry points duplicate transaction management, security checks, and workflow coordination.
* **The PoEAA Pattern**:
  * **Service Layer**: Defines an application's boundary with a layer of services that coordinates operations and manages transactions, keeping domain entities pure and unaware of transport layers.
* **Refactoring Move**:
  * Extract coarse-grained operations into dedicated services (`OrderFulfillmentService`, `AccountRegistrationService`).
  * Ensure services delegate domain calculations to Domain Models and persistence to Repositories.

---

## 💎 2. Structural & Value Patterns

### Value Object & Money
* **The Problem (Smell: Primitive Obsession & Data Clumps)**:
  * Monetary amounts stored as floats/numbers with separate currency strings; date ranges passed as separate start/end timestamps; email addresses passed as raw strings with scattered regex validations.
* **The PoEAA Pattern**:
  * **Value Object**: A small, immutable object whose equality is determined solely by its attributes/values rather than identity. Two `Money` objects representing `$50 USD` are equal.
  * **Money**: Represents currency and amount together, preventing accidental addition of different currencies and rounding errors.
* **Refactoring Move**:
  ```typescript
  // Value Object Pattern
  export class DateRange {
    constructor(readonly start: Date, readonly end: Date) {
      if (start.getTime() > end.getTime()) {
        throw new InvalidDateRangeException("Start date must precede end date");
      }
    }
    contains(date: Date): boolean {
      return date >= this.start && date <= this.end;
    }
  }
  ```

### Special Case / Null Object
* **The Problem (Smell: Repeated Switches / Null Checks)**:
  * Endless `if (user == null)` or `if (customer.getPlan() == null)` checks polluting business code.
* **The PoEAA Pattern**:
  * **Special Case**: Creates a subclass or specific object instance that provides neutral/default behavior instead of returning `null`.
* **Refactoring Move**:
  * Introduce `NullCustomer` or `GuestCustomer` that returns `discountRate = 0.0` and `canAccessPremium() = false`. Callers execute regular methods without checking for `null`.

---

## 🗄️ 3. Persistence & Boundary Decoupling

### Gateway
* **The Problem (Smell: Leaky Third-Party Abstractions)**:
  * Direct calls to third-party SDKs (Stripe, Twilio, AWS S3) scattered across business logic, making unit testing impossible and coupling code to vendor APIs.
* **The PoEAA Pattern**:
  * **Gateway**: An object that encapsulates access to an external system or resource.
* **Refactoring Move**:
  * Define a domain-facing interface: `PaymentGateway`.
  * Implement an adapter: `StripePaymentGateway`.
  * Inject the gateway into the domain service.

### Repository & Data Mapper
* **The Problem (Smell: Leaky Persistence / SQL in Domain Logic)**:
  * Domain logic littered with SQL queries, ORM queries, or HTTP persistence calls.
* **The PoEAA Pattern**:
  * **Data Mapper**: A layer of mappers that moves data between objects and a database while keeping them independent of each other and the mapper itself.
  * **Repository**: Mediates between the domain and data mapping layers using a collection-like interface for accessing domain objects.
* **Refactoring Move**:
  * Replace direct DB calls with `orderRepository.findById(id)` and `orderRepository.save(order)`.

---

## 📦 4. Distribution & Data Transfer

### Data Transfer Object (DTO)
* **The Problem (Smell: Leaking Domain Entities / Over-fetching)**:
  * Internal domain entities with sensitive fields (e.g., password hashes, internal status flags) are serialized directly over the network to frontend clients.
* **The PoEAA Pattern**:
  * **Data Transfer Object (DTO)**: An object that carries data between processes to assemble coarse-grained responses and insulate internal domain models from API contracts.
* **Refactoring Move**:
  * Create dedicated DTO classes/interfaces for API requests and responses.
  * Use a mapper or serializer to transform `DomainModel → DTO`.

### Separated Interface & Plugin
* **The Problem (Smell: Inverted Dependency / Tight Coupling)**:
  * High-level business modules directly importing low-level infrastructure modules.
* **The PoEAA Pattern**:
  * **Separated Interface**: Define the interface in the high-level package (Domain), and place the implementation in a separate infrastructure package.
  * **Plugin**: Dynamically resolve the implementation at startup or test configuration.
