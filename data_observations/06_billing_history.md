# 06 — billing_history

## What is this dataset?

Every billing **transaction** ever attempted — successful charges, declined charges, retries, and
$0.00 verification authorisations. Full history from account creation.

## What does one row represent?

One row = one transaction attempt (charge, retry, or verification).

## Size

| Fact | Value |
|---|---|
| Rows | 677,917 |
| Columns | 17 |
| Memory (approx.) | 429.28 MB |

Expected: 677,917 rows. Many more than subscriptions because each renewal has at least one row, plus
retries for failed renewals and verifications when cards are added.

## Important columns

- **`transaction_id`** — unique ID. Primary key.
- **`account_id`** / **`subscription_id`** / **`payment_method_id`** — foreign keys.
- **`invoice_id`** — groups all attempts for the same invoice (retries share the invoice of the
  failed renewal). NULL for verifications.
- **`transaction_type`** — `CHARGE`, `RETRY`, or `VERIFY`.
- **`pmt_status`** — `approved` or `declined`.
- **`failure_code`** — for declined transactions (NULL when approved).
- **`amount_usd`** — 15.99 for charges/retries; 0.00 for verifications.
- **`billing_period_start`** / **`billing_period_end`** — the month covered.

## Date ranges

- `transaction_ts`: 2023-10-01 to 2026-10-01
- `billing_period_start`: N/A

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `failure_code` | 662,393 | 97.71% |
| `next_billing_date` | 59,182 | 8.73% |
| `invoice_id` | 43,658 | 6.44% |
| `billing_period_end` | 43,658 | 6.44% |
| `billing_period_start` | 43,658 | 6.44% |

> `invoice_id` is NULL for verifications (`VERIFY` transactions) — expected.
> `failure_code` is NULL for approved transactions — expected.
> `next_billing_date` is NULL for declined and verify transactions — expected.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Transaction type distribution

  - `CHARGE` — 622,002 (91.8%)
  - `VERIFY` — 43,643 (6.4%)
  - `RETRY` — 12,272 (1.8%)

## Payment status distribution

  - `approved` — 662,391 (97.7%)
  - `declined` — 15,526 (2.3%)

## Top failure codes (declines only)

  - `(null / missing)` — 662,391 (97.7%)
  - `INSUFFICIENT_FUNDS` — 3,494 (0.5%)
  - `STORE_BILLING_RETRY` — 2,560 (0.4%)
  - `DO_NOT_HONOR` — 2,021 (0.3%)
  - `EXPIRED_CARD` — 1,550 (0.2%)

## Gateway distribution

  - `card_gw_1` — 358,772 (52.9%)
  - `APPLE_APP_STORE` — 114,866 (16.9%)
  - `PAYPAL` — 104,853 (15.5%)
  - `GOOGLE_PLAY` — 66,053 (9.7%)
  - `ROKU_PAY` — 21,510 (3.2%)

## Potential relationships

- `subscription_id` → `subscription_history`.
- `payment_method_id` → `payment_methods`.

## Anything unusual?

- All amounts are exactly $15.99 or $0.00 — no refunds or partial charges exist in this dataset.
- Renewals post within ~30 minutes of the billing anchor time.
- Grace period retries happen on days 1, 3, and 5 after a failed renewal.

## What can this dataset help us understand?

- Payment success/failure rates and patterns.
- How often members go through the grace period.
- Which decline reasons are most common.
