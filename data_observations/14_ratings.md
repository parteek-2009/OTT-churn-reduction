# 14 — ratings

## What is this dataset?

Thumbs ratings given by members on titles. Full analysis window.

## What does one row represent?

One row = one rating by one profile on one title.

## Size

| Fact | Value |
|---|---|
| Rows | 58,124 |
| Columns | 8 |
| Memory (approx.) | 9.48 MB |

Expected: ~58,124 rows. Only a subset of members rate content.

## Important columns

- **`rating_id`** — unique ID. Primary key.
- **`account_id`** / **`profile_id`** / **`title_id`** — who rated what.
- **`rating_type`** — always `thumb` in this dataset.
- **`thumbs_value`** — 1 = thumbs down, 2 = thumbs up, 3 = two thumbs up ("love this").
- **`device_id`** — device used when the rating was given (may not be the same device used to watch).
- **`event_ts`** — when the rating was given.

## Date range

- `event_ts`: 2025-10-01 to 2026-09-30

## Missing values

No missing values.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Thumbs value distribution

  - `thumb` — 58,124 (100.0%)

## Potential relationships

- `title_id` → `catalog`.
- `profile_id` → `profiles`.
- `device_id` → `devices`.

## What can this dataset help us understand?

- Whether members who rate content more are more engaged and less likely to churn.
- Content satisfaction signals across the catalog.
- Whether negative ratings (thumbs down) appear before cancellation.
