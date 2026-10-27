# 05 — subscription_history

## What is this dataset?

One row per **subscription period**. A subscription period is a continuous stretch of being
subscribed. If a member cancels and rejoins later, they get a brand-new row with `signup_type = REJOIN`.

## What does one row represent?

One row = one subscription period for one account.

## Size

| Fact | Value |
|---|---|
| Rows | 61,331 |
| Columns | 20 |
| Memory (approx.) | 36.52 MB |

Expected: 61,331 rows. More rows than accounts because some members have multiple periods
(cancelled and rejoined).

## Important columns

- **`subscription_id`** — unique ID per period. Primary key.
- **`account_id`** — the account.
- **`period_seq`** — 1 for first subscription, 2 for second (after a rejoin), etc.
- **`signup_type`** — `NEW` or `REJOIN`.
- **`opened_ts`** — when the period started (first successful charge).
- **`billing_anchor_day`** — day of the month when renewals charge.
- **`cancel_requested_ts`** — when the member asked to cancel. NULL if they haven't.
- **`closed_ts`** — when access ended. NULL while the period is still open.
- **`is_customer_initiated_cancel`** — 1 = member chose to cancel; 0 = closed due to unpaid billing.
- **`close_reason_code`** — `MEMBER_CANCELLED` or `PAYMENT_DECLINED_GRACE_EXPIRED`.

## Date ranges

- `opened_ts`: 2023-10-01 to 2026-09-30
- `cancel_requested_ts`: 2023-10-10 to 2026-09-30
- `closed_ts`: 2023-11-01 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `cancel_requested_ts` | 35,198 | 57.39% |
| `cancel_channel` | 35,198 | 57.39% |
| `closed_ts` | 35,008 | 57.08% |
| `is_customer_initiated_cancel` | 35,008 | 57.08% |
| `close_reason_code` | 35,008 | 57.08% |

> `cancel_requested_ts`, `cancel_channel`, `closed_ts`, `is_customer_initiated_cancel`, and
> `close_reason_code` are NULL for periods that are **still open** — this is expected.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Signup type distribution

  - `NEW` — 50,000 (81.5%)
  - `REJOIN` — 11,331 (18.5%)

## Cancel channel distribution

  - `(null / missing)` — 35,200 (57.4%)
  - `WEB` — 10,921 (17.8%)
  - `APPLE_SUBSCRIPTIONS` — 4,968 (8.1%)
  - `GOOGLE_PLAY` — 2,887 (4.7%)
  - `TV_APP` — 2,502 (4.1%)

## Close reason distribution

  - `(null / missing)` — 35,006 (57.1%)
  - `MEMBER_CANCELLED` — 25,223 (41.1%)
  - `PAYMENT_DECLINED_GRACE_EXPIRED` — 1,102 (1.8%)

## Potential relationships

- `subscription_id` → `billing_history`, `membership_events`.
- `account_id` → `accounts`.

## Anything unusual?

- Since Jetflix has only one plan (`Standard $15.99/month`), `plan_code`, `plan_name`,
  `plan_price_usd`, `billing_cycle`, `max_concurrent_streams`, `max_video_quality`, and `has_ads`
  will be the same for every row. They carry no variation but are kept for completeness.
- A cancel that was **reversed** (member re-added a payment method before the renewal) does not
  create a new period — you need `membership_events` to see that event.

## What can this dataset help us understand?

- Which accounts have churned (closed period), when, and why.
- How many members have rejoined (rejoin rate).
- Whether voluntary cancels or payment failures drive more churn.
