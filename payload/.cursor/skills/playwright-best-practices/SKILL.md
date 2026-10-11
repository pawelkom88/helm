---
name: playwright-best-practices
description: Playwright browser and end-to-end testing best practices. Use when writing, debugging, or reviewing Playwright E2E tests, browser automation, locator strategies, network route mocking, or accessibility test assertions. Do not use for unit testing.
license: Apache-2.0
metadata:
  upstream: currents-dev/playwright-best-practices-skill
  commit: 283d5cbc5d11aac1abda058b16ad22c317d54dc0
  version: "1.0.0"
---

# Playwright Best Practices (Core Essentials)

Lean reference for writing robust, maintainable, flake-free Playwright end-to-end browser tests. Covers user-facing locators, web-first assertions, flakiness elimination, network mocking, and accessibility audits.

## When to Apply

Use this skill when:
- Authoring new Playwright end-to-end or integration browser tests
- Debugging intermittent test failures, timeouts, or race conditions
- Mocking external APIs and backend routes with `page.route()`
- Auditing and writing accessibility assertions with `@axe-core/playwright`
- Reviewing E2E test suites for anti-patterns (e.g. hardcoded sleeps, fragile CSS/XPath selectors)

---

## 1. Locators: User-Facing Roles First

Always prefer user-visible locators that mirror how real users and assistive technologies interact with the page.

### Locator Priority Order
1. `page.getByRole('button', { name: /submit/i })` — accessible name and semantic role (best)
2. `page.getByLabel('Email Address')` — form controls with associated `<label>`
3. `page.getByPlaceholder('Search...')` — input placeholder text
4. `page.getByText('Welcome back')` — non-interactive text content
5. `page.getByTestId('checkout-card')` — explicit test IDs when semantic roles are ambiguous

### Anti-Patterns
```ts
// ❌ Fragile CSS / DOM hierarchy selectors
page.locator('div.container > form > div:nth-child(2) > button');

// ❌ Fragile XPath
page.locator('//button[text()="Submit"]');

// ✅ Robust user-facing locator
page.getByRole('button', { name: 'Submit' });
```

---

## 2. Web-First Assertions & Auto-Waiting

Playwright features built-in auto-waiting before performing actions (click, fill, check). Pair actions with **web-first assertions** that poll until the expected state is reached.

### Rules
- **Never use hardcoded sleeps**: `page.waitForTimeout(5000)` is forbidden. It causes slow test suites and fails unpredictably under CI load.
- **Always use `expect(locator)` with async matchers**:
  ```ts
  // ❌ Non-retrying sync assertion (fails if DOM hasn't updated yet)
  expect(await locator.isVisible()).toBe(true);

  // ✅ Auto-retrying web-first assertion
  await expect(locator).toBeVisible();
  ```
- Common matchers:
  - `await expect(locator).toBeVisible()`
  - `await expect(locator).toBeEnabled()`
  - `await expect(locator).toHaveText(/saved/i)`
  - `await expect(locator).toHaveValue('user@example.com')`
  - `await expect(page).toHaveURL(/\/dashboard/)`

---

## 3. Eliminating Flakiness

1. **Avoid `waitForLoadState('networkidle')`**: Modern single-page applications stream events and ping websockets continuously; `networkidle` frequently times out. Instead, wait for a specific element or response:
   ```ts
   // Wait for the specific data response or UI element
   await expect(page.getByRole('table')).toBeVisible();
   ```
2. **Isolate Test State**: Every test must run in its own `BrowserContext` with fresh storage and session cookies. Never rely on state left behind by previous tests.
3. **Actionability Checks**: Playwright checks that elements are attached, visible, stable, receive events, and are enabled before clicking. Do not duplicate these checks with manual `waitForSelector` calls.

---

## 4. Network Route Mocking (`page.route`)

Mock external third-party services (payment gateways, analytics, webhooks) or slow backend endpoints to keep tests deterministic and fast.

### Mocking a Single Route
```ts
test('handles payment failure gracefully', async ({ page }) => {
  await page.route('**/api/v1/payments', async (route) => {
    await route.fulfill({
      status: 402,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Card declined' }),
    });
  });

  await page.goto('/checkout');
  await page.getByRole('button', { name: 'Pay Now' }).click();
  await expect(page.getByText('Card declined')).toBeVisible();
});
```

### Unhandled Route Fallthrough
Use `route.continue()` to modify headers or monitor requests while allowing them to hit the real server when needed.

---

## 5. Accessibility Testing (a11y)

Integrate automated accessibility checks into key user flows using `@axe-core/playwright`.

```ts
import AxeBuilder from '@axe-core/playwright';

test('login page has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/login');

  const accessibilityScanResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  expect(accessibilityScanResults.violations).toEqual([]);
});
```
