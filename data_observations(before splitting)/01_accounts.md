# 01 — accounts

## What is this dataset?

This table holds one record for every Jetflix **account** in the sample. Think of it as the main
customer file. It shows the state of each account **at the time of data extraction (2026-10-01)**.

## What does one row represent?

One row = one Jetflix account holder.

## Size

| Fact | Value |
|---|---|
| Rows | 50,000 |
| Columns | 26 |
| Memory (approx.) | 32.78 MB |

This matches the expected sample of exactly 50,000 accounts.

## Important columns

- **`account_id`** — unique integer ID for each account. Primary key.
- **`account_created_ts`** — when the account was created.
- **`account_type`** — almost all rows are `CONSUMER`; a tiny fraction (~0.1%) are `EMPLOYEE` or `QA_TEST`.
- **`signup_channel`** / **`signup_platform`** / **`signup_device_category`** — describe how and where the customer signed up.
- **`state`** — US state (2-letter code) from billing address or IP.
- **`preferred_language`** — `en-US` or `es-US`.
- **`birth_year`** / **`gender`** — optional, self-reported (~30% / ~19% filled respectively).
- Consent flags (columns starting with `email_consent_`, `sms_consent_`, `whatsapp_consent`, etc.) — all snapshot values as of extraction.

## Date range

- `account_created_ts`: 2023-10-01 to 2026-09-30
  *(Accounts go back to platform launch 2023-10-01; not all are from the analysis window.)*

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `gender` | 40,635 | 81.27% |
| `birth_year` | 34,565 | 69.13% |
| `zip3` | 1,880 | 3.76% |

> **`zip3`** is NULL for ~2% of accounts (app-store payers have no billing address).  
> **`birth_year`** and **`gender`** are optional self-reported fields — high missingness is expected.

## Sentinel values

No sentinel `-1` values.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)
*(Expected: 0 — each account has exactly one row.)*

## Signup channel top values

  - `organic_direct` — 13,864 (27.7%)
  - `paid_search` — 9,230 (18.5%)
  - `paid_social` — 7,735 (15.5%)
  - `smart_tv_app` — 4,784 (9.6%)
  - `ios_app_store` — 4,749 (9.5%)

## Signup platform top values

  - `web` — 17,120 (34.2%)
  - `ios` — 8,319 (16.6%)
  - `roku` — 6,844 (13.7%)
  - `android` — 4,314 (8.6%)
  - `fireos` — 4,096 (8.2%)

## Account type distribution

  - `CONSUMER` — 49,950 (99.9%)
  - `QA_TEST` — 30 (0.1%)
  - `EMPLOYEE` — 20 (0.0%)

## Potential relationships with other tables

- `account_id` links to almost every other table (profiles, devices, billing, viewing, etc.).
- Consent flags here are snapshots; to see consent history, use **`consent_events`**.

## Anything unusual?

- `birth_year` contains a few implausible values (e.g., very early years). These are self-reported and
  were entered by customers — treat them cautiously, not as errors.
- `account_type` is not purely `CONSUMER` — QA and employee accounts exist. These are flagged and behave
  like normal accounts for billing purposes.

## What can this dataset help us understand?

- Who signed up, when, and through which channel.
- Account-level demographics (partial) and communication preferences.
- Entry point for joining to all other tables.
