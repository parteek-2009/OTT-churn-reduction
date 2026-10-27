# 20 — episodes

## What is this dataset?

The **reference table for all episodes** belonging to series and limited series titles.

## What does one row represent?

One row = one episode of one series.

## Size

| Fact | Value |
|---|---|
| Rows | 25,240 |
| Columns | 7 |
| Memory (approx.) | 3.84 MB |

Expected: 25,240 rows.

## Important columns

- **`episode_id`** — unique ID. Primary key.
- **`title_id`** — which series this episode belongs to. Foreign key → `catalog`.
- **`season_number`** / **`episode_number`** — position within the series.
- **`episode_title`** — name of the episode.
- **`runtime_sec`** — episode length in seconds.
- **`release_date`** — when the episode became available on Jetflix (weekly releases drop one
  episode per week).

## Date range

- `release_date`: 2023-10-01 to 2026-09-26

## Missing values

No missing values.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Season number distribution

N/A

## Potential relationships

- `title_id` → `catalog`.
- `episode_id` → `viewing_activity` (which episodes were watched and for how long).

## What can this dataset help us understand?

- Episode completion rates (by joining with `viewing_activity`).
- Whether binge-watching behaviour (rapid episode progression) predicts retention.
- Whether weekly-release shows drive sustained engagement vs. all-at-once releases.
