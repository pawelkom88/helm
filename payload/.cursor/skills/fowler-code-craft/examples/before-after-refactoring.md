# Real-World Before & After Refactoring Case Studies

Comprehensive case studies illustrating the step-by-step transformation of smelly code into clean, well-architected systems using Martin Fowler's Refactoring techniques and PoEAA patterns.

---

## Case Study 1: Backend Business Logic (TypeScript)

### 🚨 The "Before" Implementation
**Smells Detected**:
* *Mysterious Name*: `d`, `u`, `flag`, `calc()`, `res`
* *Primitive Obsession*: Cents and currencies handled as bare numbers/strings; date ranges as separate strings
* *Transaction Script*: Business rules, persistence queries, and email alerts all intermingled in one method
* *Noise Words*: `OrderHelper` class name
* *Repeated Switches*: Inline discount type branching

```typescript
// BEFORE: Smelly, monolithic transaction script
export class OrderHelper {
  async proc(d: any, u: string, flag: boolean) {
    // Smell: Mysterious name & unvalidated primitives
    if (d.amt <= 0 || !d.curr) {
      throw new Error("Invalid");
    }

    // Smell: Repeated switch & magic numbers
    let disc = 0;
    if (flag) {
      if (d.type === "VIP") disc = d.amt * 0.15;
      else if (d.type === "REGULAR") disc = d.amt * 0.05;
      else if (d.type === "STUDENT") disc = d.amt * 0.10;
    }
    const finalAmt = d.amt - disc;

    // Smell: Leaky direct DB persistence inside business computation
    const query = "INSERT INTO orders (user_id, total, currency, status) VALUES ($1, $2, $3, $4) RETURNING id";
    const dbRes = await database.query(query, [u, finalAmt, d.curr, "COMPLETED"]);
    const orderId = dbRes.rows[0].id;

    // Smell: Direct unencapsulated HTTP call
    await fetch("https://api.notifications.internal/email", {
      method: "POST",
      body: JSON.stringify({ recipient: u, subject: "Order Placed", body: `Order ${orderId}: ${finalAmt}` })
    });

    return { id: orderId, total: finalAmt };
  }
}
```

---

### ✨ The "After" Refactoring
**Patterns Applied**:
1. **PoEAA Value Object**: `Money` encapsulates amount, currency, arithmetic, and validation.
2. **Intent-Revealing Naming**: `OrderPlacementRequest`, `CustomerTier`, `OrderFulfillmentService`, `fulfillOrder`.
3. **Lookup Table / Strategy**: `TIER_DISCOUNT_RATES` map replaces nested type switches.
4. **PoEAA Repository & Gateway**: Decouples domain logic from SQL and external notification APIs.
5. **Zero Breaking Changes**: An adapter or preserved facade keeps existing callers functional.

```typescript
// AFTER: Domain Model + Value Object + Repository + Gateway

export type CustomerTier = "VIP" | "REGULAR" | "STUDENT" | "GUEST";

// 1. PoEAA Value Object
export class Money {
  constructor(readonly amountInCents: number, readonly currency: string) {
    if (amountInCents <= 0) {
      throw new InvalidAmountError(`Amount must be positive: ${amountInCents}`);
    }
    if (!currency || currency.length !== 3) {
      throw new InvalidCurrencyError(`Invalid ISO currency: ${currency}`);
    }
  }

  applyDiscount(discountPercentage: number): Money {
    const discountAmount = Math.round(this.amountInCents * discountPercentage);
    return new Money(this.amountInCents - discountAmount, this.currency);
  }
}

// 2. Refactoring: Replace Conditional with Lookup Table
const TIER_DISCOUNT_RATES: Record<CustomerTier, number> = {
  VIP: 0.15,
  STUDENT: 0.10,
  REGULAR: 0.05,
  GUEST: 0.00,
};

// 3. PoEAA Separated Interfaces (Boundary Gateways)
export interface OrderRepository {
  save(order: Order): Promise<void>;
}

export interface NotificationGateway {
  sendOrderConfirmation(order: Order): Promise<void>;
}

// 4. Intent-revealing Request Object
export interface OrderPlacementRequest {
  readonly customerId: string;
  readonly basePrice: Money;
  readonly customerTier: CustomerTier;
  readonly isPromotionalDiscountEligible: boolean;
}

// 5. PoEAA Service Layer
export class OrderFulfillmentService {
  constructor(
    private readonly orderRepository: OrderRepository,
    private readonly notificationGateway: NotificationGateway
  ) {}

  async fulfillOrder(request: OrderPlacementRequest): Promise<OrderReceipt> {
    const finalPrice = this.calculateDiscountedPrice(request);
    const order = Order.create({
      customerId: request.customerId,
      total: finalPrice,
    });

    await this.orderRepository.save(order);
    await this.notificationGateway.sendOrderConfirmation(order);

    return new OrderReceipt(order.id, order.total);
  }

  private calculateDiscountedPrice(request: OrderPlacementRequest): Money {
    if (!request.isPromotionalDiscountEligible) {
      return request.basePrice;
    }
    const discountRate = TIER_DISCOUNT_RATES[request.customerTier] ?? 0;
    return request.basePrice.applyDiscount(discountRate);
  }
}

// 6. Backward-Compatibility Adapter (Preserves legacy OrderHelper for existing callers)
export class OrderHelper {
  constructor(private readonly service: OrderFulfillmentService) {}

  async proc(d: any, u: string, flag: boolean) {
    const money = new Money(d.amt, d.curr);
    const receipt = await this.service.fulfillOrder({
      customerId: u,
      basePrice: money,
      customerTier: d.type as CustomerTier,
      isPromotionalDiscountEligible: flag,
    });
    return { id: receipt.orderId, total: receipt.total.amountInCents };
  }
}
```

---

## Case Study 2: Frontend Component & Data Hook (TypeScript / React)

### 🚨 The "Before" Implementation
**Smells Detected**:
* *Long Function / Mega Component*: 150-line component doing API calls, date formatting, filter logic, and rendering
* *Data Clumps*: `startDate`, `endDate`, `searchKeyword`, `page`, `pageSize` passed separately
* *Primitive Obsession*: Inline date string parsing inside JSX render loops
* *Mysterious Name*: `h1`, `tempData`, `res`, `flag`

```tsx
// BEFORE: Mega component with mixed concerns
export function UserList(props: any) {
  const [data, setData] = useState([]);
  const [sDate, setSDate] = useState("");
  const [eDate, setEDate] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/users?start=${sDate}&end=${eDate}&search=${q}`)
      .then(res => res.json())
      .then(resData => {
        setData(resData);
        setLoading(false);
      });
  }, [sDate, eDate, q]);

  return (
    <div>
      {/* 80 lines of nested inputs, inline date parsing, and mapping */}
      {data.map((u: any) => (
        <div key={u.id}>
          <span>{u.name}</span>
          <span>{new Date(u.created_at).toLocaleDateString()}</span>
        </div>
      ))}
    </div>
  );
}
```

---

### ✨ The "After" Refactoring
**Patterns Applied**:
1. **Extract Custom Hook**: State orchestration and API interaction moved to `useUserSearch`.
2. **Introduce Parameter Object**: Search filters encapsulated in `UserFilterCriteria`.
3. **Extract Sub-Component**: Row rendering separated into a focused `UserListItem`.
4. **Intent-Revealing Naming**: Clear props interface, semantic state names.

```tsx
// AFTER: Separated concerns with custom hook & presentational sub-components

export interface UserFilterCriteria {
  readonly startDate?: string;
  readonly endDate?: string;
  readonly searchQuery?: string;
}

// 1. Extracted Hook: Data fetching and filter orchestration
export function useUserSearch(filters: UserFilterCriteria) {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<Error | null>(null);

  useEffect(() => {
    let isCancelled = false;
    async function loadUsers() {
      setIsLoading(true);
      setFetchError(null);
      try {
        const fetchedUsers = await fetchUsersByCriteria(filters);
        if (!isCancelled) setUsers(fetchedUsers);
      } catch (err) {
        if (!isCancelled) setFetchError(err as Error);
      } finally {
        if (!isCancelled) setIsLoading(false);
      }
    }
    loadUsers();
    return () => { isCancelled = true; };
  }, [filters.startDate, filters.endDate, filters.searchQuery]);

  return { users, isLoading, fetchError };
}

// 2. Focused Presentational Child Component
export function UserListItem({ user }: { readonly user: User }) {
  const formattedCreationDate = useMemo(() => formatLocalizedDate(user.createdAt), [user.createdAt]);

  return (
    <div className="user-list-item">
      <span className="user-name">{user.fullName}</span>
      <time dateTime={user.createdAt.toISOString()}>{formattedCreationDate}</time>
    </div>
  );
}
```
