# 07 — membership_events

## What is this dataset?

A log of every important **account change** — subscription starts, cancels, payment method changes,
grace periods, profile changes, and more. Full history.

## What does one row represent?

One row = one event that changed something about the account's membership state.

## Size

| Fact | Value |
|---|---|
| Rows | 271,991 |
| Columns | 8 |
| Memory (approx.) | 60.0 MB |

Expected: 271,991 rows. Multiple events per account over their lifetime.

## Important columns

- **`event_id`** — unique ID. Primary key.
- **`account_id`** — the account.
- **`subscription_id`** — the subscription period active at the time.
- **`event_ts`** — when the event happened.
- **`event_type`** — what happened (e.g., `SUBSCRIPTION_STARTED`, `CANCEL_REQUESTED`,
  `CANCEL_REVERSED`, `GRACE_STARTED`, `PAYMENT_METHOD_ADDED`).
- **`source`** — where the action came from (e.g., `WEB`, `IOS`, `SYSTEM`, `CS_AGENT`).
- **`device_id`** — mostly NULL; this service does not always capture it.
- **`payment_method_id`** — filled for payment-method and cancel events.

## Date range

- `event_ts`: 2023-10-01 to 2026-10-01

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `device_id` | 271,991 | 100.0% |
| `payment_method_id` | 134,880 | 49.59% |
| `subscription_id` | 19,910 | 7.32% |

> `device_id` is mostly NULL — the membership service does not always capture the device.
> `payment_method_id` is only filled for relevant event types.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Event type distribution

  - `PAYMENT_METHOD_ADDED` — 65,246 (24.0%)
  - `SUBSCRIPTION_STARTED` — 61,331 (22.5%)
  - `PROFILE_CREATED` — 40,456 (14.9%)
  - `PAYMENT_METHOD_REMOVED` — 31,149 (11.5%)
  - `CANCEL_REQUESTED` — 27,974 (10.3%)

## Event source distribution

  - `WEB` — 128,376 (47.2%)
  - `TV` — 42,710 (15.7%)
  - `SYSTEM` — 36,179 (13.3%)
  - `USER_CANCELLED` — 18,084 (6.6%)
  - `IOS` — 13,585 (5.0%)

## Potential relationships

- `account_id` → `accounts`.
- `subscription_id` → `subscription_history`.
- `payment_method_id` → `payment_methods`.

## Anything unusual?

- `CANCEL_REVERSED` events mean a member cancelled but then re-added a payment method before
  the renewal date, so the subscription continued. The `subscription_history` table does not show
  this — you need this event log to see it.
- `subscription_id` is NULL for events that happened before the first subscription period
  (rare pre-subscription events).

## What can this dataset help us understand?

- The full timeline of account changes for any given account.
- Cancel-and-reverse patterns (members who "save" themselves from churning).
- How often support agents made account changes.
