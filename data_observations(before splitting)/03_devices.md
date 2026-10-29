# 03 — devices

## What is this dataset?

Every device that has ever been **signed in** to an account. This is a snapshot: it shows each
device's registration state as of extraction.

## What does one row represent?

One row = one device registration on one account.

## Size

| Fact | Value |
|---|---|
| Rows | 153,144 |
| Columns | 15 |
| Memory (approx.) | 103.94 MB |

Expected: 153,144 rows. Average of ~3 devices per account.

## Important columns

- **`device_id`** — unique ID. Primary key.
- **`account_id`** — which account registered this device.
- **`device_category`** — type of device (TV, phone, tablet, etc.). **Not normalised** — same category
  can appear as `TV`, `Smart TV`, or `tv`. Will need cleaning later.
- **`platform`** — operating platform (e.g., `roku`, `ios`, `web`).
- **`app_version_first`** / **`app_version_last`** — app versions at first and last use. Formats vary.
- **`os_version`** — `-1` when the system did not report it (not missing data, not an error).
- **`first_seen_ts`** / **`last_seen_ts`** — registration time and most recent activity.
- **`deactivated_ts`** — when the device was removed; NULL if still registered.

## Date ranges

- `first_seen_ts`: 2023-10-01 to 2026-09-30
- `last_seen_ts`: 2023-10-01 to 2026-09-30
- `deactivated_ts`: 2025-09-30 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `deactivated_ts` | 144,553 | 94.39% |
| `manufacturer` | 24,671 | 16.11% |
| `model_code` | 24,671 | 16.11% |

> `manufacturer` and `model_code` are NULL for web browsers (there is no hardware model for a browser).
> `deactivated_ts` is NULL for devices still registered — expected.

## Sentinel values

No sentinel `-1` values.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Device category distribution (raw, un-normalised)

  - `TV` — 25,258 (16.5%)
  - `STREAMING_STICK` — 20,985 (13.7%)
  - `MOBILE` — 14,795 (9.7%)
  - `WEB` — 12,260 (8.0%)
  - `Streaming Stick` — 10,626 (6.9%)

## Platform distribution

  - `ios` — 25,709 (16.8%)
  - `roku` — 25,309 (16.5%)
  - `web` — 24,674 (16.1%)
  - `tizen` — 16,821 (11.0%)
  - `fireos` — 15,976 (10.4%)

## Anything unusual?

- `device_category` has multiple spellings for the same concept — this is a **known raw-data
  characteristic**, not a data error. It will need to be standardised before analysis.
- `app_version_first` and `app_version_last` have inconsistent formats (`9.1.0`, `v9.1.0`,
  `tv-9.1.0`, etc.) across platforms.
- Some older TV models are capped at app version 8.12.x and cannot update further.

## Potential relationships

- `device_id` → `viewing_activity`, `playback_quality`, `login_events`, `support_contacts`,
  `communications_log` (push channel), `clickstream`.

## What can this dataset help us understand?

- What types of devices subscribers use.
- Whether device type or platform affects viewing behaviour or churn.
- App version adoption across the device base.
