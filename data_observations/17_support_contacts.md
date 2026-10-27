# 17 — support_contacts

## What is this dataset?

Every **customer-service contact** — chat, phone, email, and social — during the analysis window.

## What does one row represent?

One row = one support interaction between an account and a Jetflix agent.

## Size

| Fact | Value |
|---|---|
| Rows | 16,247 |
| Columns | 10 |
| Memory (approx.) | 5.27 MB |

Expected: ~16,247 rows. A small fraction of members contact support.

## Important columns

- **`contact_id`** — unique ID. Primary key.
- **`account_id`** — the account.
- **`contact_ts`** — when the contact started.
- **`channel`** — `CHAT`, `PHONE`, `EMAIL`, `SOCIAL`.
- **`contact_reason`** — agent-selected reason (e.g., `BILLING_QUESTION`, `PAYMENT_FAILED`,
  `CANCEL_HELP`, `PLAYBACK_ISSUE`).
- **`resolution`** — `RESOLVED`, `RESOLVED_WORKAROUND`, `ESCALATED`, `UNRESOLVED`,
  `CUSTOMER_ABANDONED`.
- **`handle_time_sec`** — how long the contact took. `-1` for email contacts (not measured).
- **`csat_score`** — post-contact satisfaction score 1–5; NULL when not answered (~70% of contacts).
- **`agent_tier`** — `TIER1`, `TIER2`, or `BILLING`.

## Date range

- `contact_ts`: 2025-10-01 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `device_id` | 14,361 | 88.39% |
| `csat_score` | 11,675 | 71.86% |

> `csat_score` is NULL ~70% of the time (most members do not complete the survey).
> `device_id` is NULL when the issue was not tied to a specific device.

## Sentinel values

| Column | Count | % | Meaning |
|---|---|---|---|
| `handle_time_sec` | 2,374 | 14.6% | System did not capture this value |

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Contact reason distribution

  - `REFUND_REQUEST` — 2,732 (16.8%)
  - `BILLING_QUESTION` — 2,482 (15.3%)
  - `OTHER` — 1,933 (11.9%)
  - `PLAYBACK_ISSUE` — 1,887 (11.6%)
  - `DEVICE_ACTIVATION` — 1,772 (10.9%)

## Resolution distribution

  - `RESOLVED` — 6,220 (38.3%)
  - `UNRESOLVED` — 3,825 (23.5%)
  - `RESOLVED_WORKAROUND` — 2,489 (15.3%)
  - `CUSTOMER_ABANDONED` — 1,862 (11.5%)
  - `ESCALATED` — 1,851 (11.4%)

## Channel distribution

  - `CHAT` — 8,336 (51.3%)
  - `PHONE` — 4,865 (29.9%)
  - `EMAIL` — 2,374 (14.6%)
  - `SOCIAL` — 672 (4.1%)

## Potential relationships

- `account_id` → `accounts`.
- `device_id` → `devices`.

## Anything unusual?

- `REFUND_REQUEST` contacts are described as common after renewals, even though Jetflix has no
  refund policy. This reflects real member behaviour, not a data error.
- `handle_time_sec = -1` for email contacts is a sentinel (email handle time is not measured),
  not missing data.

## What can this dataset help us understand?

- Whether members who contact support are more or less likely to cancel.
- Which contact reasons are most associated with churn.
- Whether issue resolution quality (CSAT) affects retention.
