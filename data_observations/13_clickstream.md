# 13 — clickstream

## What is this dataset?

App and website **user-interface events**: app launches, page views, button clicks, search submits.
**Last 90 days only (2026-07-03 to 2026-09-30).**

## What does one row represent?

One row = one UI event in one app session.

## Size

| Fact | Value |
|---|---|
| Rows | 2,158,373 |
| Columns | 10 |
| Memory (approx.) | 615.49 MB |

Expected: ~2.2 million rows.

## Important columns

- **`event_id`** — unique ID. Primary key.
- **`app_session_id`** — groups all events of one continuous app/browser session.
- **`account_id`** / **`profile_id`** / **`device_id`** — who and on what.
- **`event_type`** — `app_launch`, `page_view`, `click`, `search_submit`.
- **`page`** — which page or UI element (e.g., `home`, `title_detail`, `membership_cancel`).
- **`title_id`** — the title being viewed, if any.
- **`client_ts`** — device time (can be skewed by up to a few minutes).
- **`server_received_ts`** — ingestion time (~1% arrive late).

## Date ranges

- `client_ts`: 2026-07-03 to 2026-09-30
- `server_received_ts`: 2026-07-03 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `title_id` | 1,193,364 | 55.29% |
| `profile_id` | 28,275 | 1.31% |

> `profile_id` is NULL before a profile is chosen (e.g., the rejoin screen).
> `title_id` is NULL for events not related to a specific title.

## Duplicate rows

Fully duplicated rows: **6,553** (0.304%)
*(Expected: ~0.3% are client re-sends — similar to playback_events.)*

## Event type distribution

  - `click` — 1,004,179 (46.5%)
  - `app_launch` — 706,809 (32.7%)
  - `page_view` — 404,843 (18.8%)
  - `search_submit` — 42,542 (2.0%)

## Page / element distribution

  - `home` — 692,729 (32.1%)
  - `play` — 562,957 (26.1%)
  - `profile_select` — 417,428 (19.3%)
  - `title_detail` — 341,469 (15.8%)
  - `search` — 85,115 (3.9%)

## Potential relationships

- `title_id` → `catalog`.
- `device_id` → `devices`.
- `profile_id` → `profiles`.

## Anything unusual?

- Cancels made through an **app store** (Apple, Google, Roku) produce no Jetflix clickstream rows.
  If you are trying to count cancel-page visits, you will miss app-store cancels.
- ~0.3% duplicate rows from client re-sends need deduplication before analysis.
- `client_ts` can be skewed; `server_received_ts` is generally more reliable.

## What can this dataset help us understand?

- Navigation patterns before cancellation (e.g., visits to `membership_cancel` page).
- How often members browse vs. search vs. play directly.
- App launch frequency as an engagement signal.
