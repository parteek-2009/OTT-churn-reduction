# 09 — viewing_activity

## What is this dataset?

One row for every **completed playback** session — a user watching a movie, an episode, a
preview, or a trailer. Covers the full analysis window (2025-10-01 to 2026-09-30). This is the
largest core table.

## What does one row represent?

One row = one playback event on one account, by one profile, on one device.

## Size

| Fact | Value |
|---|---|
| Rows | 3,326,139 |
| Columns | 14 |
| Memory (approx.) | 1336.21 MB |

Expected: ~3.3 million rows.

## Important columns

- **`view_id`** — unique ID for this playback. Primary key. Joins to `playback_events` and
  `playback_quality`.
- **`account_id`** / **`profile_id`** / **`device_id`** — who watched and on what device.
- **`start_ts`** — when playback started.
- **`duration`** — how long was actually watched (HH:MM:SS, pauses excluded).
- **`title_id`** / **`episode_id`** — what was watched. `episode_id` is NULL for movies and
  trailers/previews.
- **`supplemental_video_type`** — NULL for the main title; `HOOK` (auto-played preview on TV) or
  `TRAILER`.
- **`bookmark`** / **`latest_bookmark`** — playback position when the session ended.
- **`is_offline_download`** — 1 if watched from a downloaded file.
- **`subtitle_language`** — only captured by app 9.0.0+ (released 2026-02-10); NULL for older
  clients and sessions before that date.

## Date range

- `start_ts`: 2025-10-01 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `supplemental_video_type` | 3,040,756 | 91.42% |
| `attributes` | 2,341,602 | 70.4% |
| `subtitle_language` | 1,544,326 | 46.43% |
| `episode_id` | 885,418 | 26.62% |

> `episode_id` is NULL for movies, specials, and previews — expected.
> `supplemental_video_type` is NULL for the title itself — expected.
> `subtitle_language` is NULL before app version 9.0.0 (pre-2026-02-10) and for older clients.

## Duplicate rows

Fully duplicated rows: **1,274** (0.038%)
*(A small number of duplicate view rows are an expected raw-data characteristic.)*

## Supplemental video type distribution

  - `(null / missing)` — 3,040,870 (91.4%)
  - `HOOK` — 280,008 (8.4%)
  - `TRAILER` — 5,261 (0.2%)

## Latest bookmark distribution

  - `Not latest view` — 1,107,974 (33.3%)
  - `01:10:00` — 19,611 (0.6%)
  - `01:55:00` — 14,622 (0.4%)
  - `01:46:00` — 12,585 (0.4%)
  - `01:38:00` — 11,355 (0.3%)

## Subtitle language distribution

  - `(null / missing)` — 1,544,423 (46.4%)
  - `off` — 1,389,481 (41.8%)
  - `en` — 304,626 (9.2%)
  - `es` — 67,958 (2.0%)
  - `fr` — 9,832 (0.3%)

## Potential relationships

- `view_id` → `playback_events` (play trace events), `playback_quality` (QoE metrics).
- `title_id` → `catalog`.
- `episode_id` → `episodes`.
- `profile_id` → `profiles`.
- `device_id` → `devices`.

## Anything unusual?

- Some TV sessions report very long `duration` values (many hours) because the TV player never
  sent a stop event. These are not necessarily errors — they are a known quirk of some TV clients.
- About 7.6% of accounts (3,796) have zero viewing rows in the window — they never played anything.
- ~0.04% of viewing rows reference a `profile_id` that no longer exists in `profiles` (purged
  profiles). Keep these rows — they are real historical views.

## What can this dataset help us understand?

- How much each subscriber watches (engagement level).
- Which titles are most popular.
- Whether low engagement predicts cancellation.
