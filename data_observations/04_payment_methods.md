# 04 — payment_methods

## What is this dataset?

Every payment method ever **added** to an account, including ones that have since been removed.
This is a full history table. If a member removed and re-added the same card, each addition is a
new row.

## What does one row represent?

One row = one payment method addition event for one account.

## Size

| Fact | Value |
|---|---|
| Rows | 65,246 |
| Columns | 13 |
| Memory (approx.) | 27.46 MB |

Expected: 65,246 rows. More rows than accounts because some accounts had multiple payment methods
over time.

## Important columns

- **`payment_method_id`** — unique ID. Primary key.
- **`account_id`** — the account.
- **`method_type`** — `CARD`, `APP_STORE_BILLING`, or `PAYPAL`.
- **`provider`** — e.g., `card`, `APPLE_APP_STORE`, `GOOGLE_PLAY`, `ROKU_PAY`.
- **`card_brand`** / **`card_funding`** — for cards only (NULL for PayPal / app stores).
- **`card_exp_month`** / **`card_exp_year`** — current expiry on file (may have been refreshed in-place
  by the card network's account-updater service).
- **`added_ts`** — when the method was added.
- **`removed_ts`** — when removed; NULL if still on file.
- **`removal_source`** — why it was removed (member cancelled, store turned off auto-renew, etc.).

## Date ranges

- `added_ts`: 2023-10-01 to 2026-09-30
- `removed_ts`: 2023-10-10 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `last_updated_ts` | 63,308 | 97.03% |
| `removed_ts` | 34,098 | 52.26% |
| `removal_source` | 34,098 | 52.26% |
| `card_brand` | 31,227 | 47.86% |
| `card_exp_year` | 31,227 | 47.86% |

> `card_brand`, `card_funding`, `card_exp_month`, `card_exp_year`, `billing_zip3` are NULL for
> non-card methods (PayPal, app stores). This is expected.
> `removed_ts` and `removal_source` are NULL for methods still on file.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Method type distribution

  - `CARD` — 34,017 (52.1%)
  - `APP_STORE_BILLING` — 21,603 (33.1%)
  - `PAYPAL` — 9,626 (14.8%)

## Provider distribution

  - `card` — 34,017 (52.1%)
  - `APPLE_APP_STORE` — 11,646 (17.8%)
  - `PAYPAL` — 9,626 (14.8%)
  - `GOOGLE_PLAY` — 6,639 (10.2%)
  - `ROKU_PAY` — 2,129 (3.3%)

## Card brand distribution (cards only)

  - `(null / missing)` — 31,229 (47.9%)
  - `VISA` — 17,677 (27.1%)
  - `MASTERCARD` — 9,493 (14.5%)
  - `AMEX` — 4,118 (6.3%)
  - `DISCOVER` — 2,729 (4.2%)

## Removal reason distribution

  - `(null / missing)` — 34,098 (52.3%)
  - `USER_CANCELLED` — 18,084 (27.7%)
  - `STORE_AUTO_RENEW_OFF` — 9,889 (15.2%)
  - `USER_REPLACED` — 2,073 (3.2%)
  - `SYSTEM_DUNNING_EXHAUSTED` — 1,102 (1.7%)

## Potential relationships

- `payment_method_id` → `billing_history`, `subscription_history`, `membership_events`.

## Anything unusual?

- About 2% of card/PayPal signups had a declined first card that was removed and replaced within
  minutes. This is expected and results in two rows for those accounts.
- The card network account-updater may refresh `card_exp_month`/`card_exp_year` in-place (no new row).

## What can this dataset help us understand?

- How members pay and whether payment method type is associated with churn.
- Payment method removal as a churn signal (removing a card is how members cancel on Jetflix).
