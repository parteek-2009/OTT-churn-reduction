# 08 — consent_events

## What is this dataset?

A log of every time a member's **communication consent** changed — including the initial values
set at signup. Full history.

## What does one row represent?

One row = one consent change for one consent type on one account.

## Size

| Fact | Value |
|---|---|
| Rows | 451,401 |
| Columns | 5 |
| Memory (approx.) | 88.93 MB |

Expected: 451,401 rows. Many rows per account because each of the 9 consent types is recorded at
signup, plus any later changes.

## Important columns

> There is **no single primary key column**. The composite key is `(account_id, consent_type, changed_ts)`.

- **`account_id`** — the account.
- **`consent_type`** — which consent changed (e.g., `email_marketing`, `sms_transactional`,
  `ccpa_do_not_sell_share`).
- **`new_value`** — 0 or 1 (opted out or opted in) after the change.
- **`changed_ts`** — when the change happened.
- **`source`** — `SIGNUP`, `ACCOUNT_SETTINGS`, `EMAIL_UNSUBSCRIBE_LINK`, or `SMS_STOP`.

## Date range

- `changed_ts`: 2023-10-01 to 2026-10-03

## Missing values

No missing values.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Consent type distribution

  - `email_marketing` — 51,234 (11.3%)
  - `sms_informational` — 50,167 (11.1%)
  - `email_surveys` — 50,000 (11.1%)
  - `email_kids_activity` — 50,000 (11.1%)
  - `sms_transactional` — 50,000 (11.1%)

## Source distribution

  - `SIGNUP` — 450,000 (99.7%)
  - `ACCOUNT_SETTINGS` — 813 (0.2%)
  - `EMAIL_UNSUBSCRIBE_LINK` — 421 (0.1%)
  - `SMS_STOP` — 167 (0.0%)

## Potential relationships

- `account_id` → `accounts` (consent flags in `accounts` are the snapshot at extraction;
  this table is the full history).

## Anything unusual?

- The `accounts` table has consent flags as **current** values. This table is the **history**.
  If you want to know a member's consent state at a specific date in the past, you must query
  this table up to that date.
- `whatsapp_consent` entries exist, but no WhatsApp messages are actually sent. The consent is
  collected for potential future use.

## What can this dataset help us understand?

- When members opted out of marketing emails or SMS — a potential churn signal.
- Whether consent patterns differ before and after a member cancels.
