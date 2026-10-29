# 16 — login_events

## What is this dataset?

A log of every **sign-in, sign-out, login failure, and password reset** on any account. Full
analysis window.

## What does one row represent?

One row = one login-related event on one account.

## Size

| Fact | Value |
|---|---|
| Rows | 198,805 |
| Columns | 9 |
| Memory (approx.) | 67.66 MB |

Expected: ~198,805 rows.

## Important columns

- **`login_event_id`** — unique ID. Primary key.
- **`account_id`** — the account.
- **`device_id`** — which device; NULL for password-reset events (no device needed).
- **`event_ts`** — when the event happened.
- **`event_type`** — `LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`, `PASSWORD_RESET_REQUEST`,
  `PASSWORD_RESET_COMPLETE`.
- **`auth_method`** — `PASSWORD`, `EMAIL_LINK`, `TV_CODE`, `BIOMETRIC_TOKEN`.
- **`ip_hash`** — hashed IP address (not usable for geolocation, privacy-safe).
- **`geo_state`** — US state resolved from IP at login time.
- **`failure_reason`** — for `LOGIN_FAILURE`: `BAD_PASSWORD`, `UNKNOWN_EMAIL`, `RATE_LIMITED`.

## Date range

- `event_ts`: 2025-09-30 to 2026-10-01

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `failure_reason` | 191,986 | 96.57% |
| `device_id` | 10,437 | 5.25% |
| `auth_method` | 8,111 | 4.08% |

> `device_id` is NULL for password-reset events.
> `failure_reason` is NULL for successful logins.

## Duplicate rows

Fully duplicated rows: **363** (0.183%)
*(A handful of rows are duplicated by the auth service — an expected raw-data characteristic.)*

## Event type distribution

  - `LOGIN_SUCCESS` — 173,439 (87.2%)
  - `LOGOUT` — 8,108 (4.1%)
  - `LOGIN_FAILURE` — 6,812 (3.4%)
  - `PASSWORD_RESET_REQUEST` — 5,793 (2.9%)
  - `PASSWORD_RESET_COMPLETE` — 4,653 (2.3%)

## Auth method distribution

  - `PASSWORD` — 115,753 (58.2%)
  - `EMAIL_LINK` — 38,718 (19.5%)
  - `TV_CODE` — 25,081 (12.6%)
  - `BIOMETRIC_TOKEN` — 11,145 (5.6%)
  - `(null / missing)` — 8,108 (4.1%)

## Potential relationships

- `account_id` → `accounts`.
- `device_id` → `devices`.

## What can this dataset help us understand?

- Login frequency as an engagement signal.
- Account security events (password resets, repeated failures).
- Whether login failures or resets correlate with cancellation.
