# 15 — my_list

## What is this dataset?

Records of titles **added to** (and removed from) a member's watchlist ("My List"). Full analysis
window additions are recorded.

## What does one row represent?

One row = one My List add event (with removal info if the title was later removed).

## Size

| Fact | Value |
|---|---|
| Rows | 95,650 |
| Columns | 7 |
| Memory (approx.) | 17.96 MB |

Expected: ~95,650 rows.

## Important columns

- **`list_item_id`** — unique ID. Primary key.
- **`account_id`** / **`profile_id`** / **`title_id`** — who added what.
- **`added_ts`** — when the title was added.
- **`removed_ts`** — when the title was removed; NULL if still on the list.
- **`add_source`** — where the add happened: `title_detail` or `search`.

## Date ranges

- `added_ts`: 2025-10-01 to 2026-09-30
- `removed_ts`: 2025-10-03 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `removed_ts` | 85,301 | 89.18% |

> `removed_ts` is NULL for titles still on the list — expected.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Add source distribution

  - `title_detail` — 78,536 (82.1%)
  - `search` — 17,114 (17.9%)

## Potential relationships

- `title_id` → `catalog`.
- `profile_id` → `profiles`.

## What can this dataset help us understand?

- Which titles members intend to watch (intent signal).
- Whether members who actively maintain a watchlist churn less.
- Whether removing items from the list correlates with disengagement.
