# 12 — search_history

## What is this dataset?

One row for every **search** a member made in the app or on the website. Full analysis window.

## What does one row represent?

One row = one search action by one profile.

## Size

| Fact | Value |
|---|---|
| Rows | 171,925 |
| Columns | 10 |
| Memory (approx.) | 47.71 MB |

Expected: ~171,925 rows.

## Important columns

- **`search_id`** — unique ID. Primary key.
- **`account_id`** / **`profile_id`** / **`device_id`** — who searched.
- **`search_ts`** — when the search happened.
- **`query_typed`** — the text as typed (can include typos, partial words, or searches for titles
  not on Jetflix).
- **`displayed_title_id`** — the title the user selected from results; NULL if nothing was selected
  or no results matched.
- **`action`** — what the user did with the result: `play`, `view_details`, `add_to_my_list`,
  or `none`.
- **`section`** — where in the search UI: `search_results`, `suggested`, `top_searches`, `voice`.
- **`is_kids`** — 1 if the search was on a kids profile.

## Date range

- `search_ts`: 2025-10-01 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `displayed_title_id` | 9,336 | 5.43% |

> `displayed_title_id` is NULL when no title was matched or selected — expected.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Action distribution

  - `play` — 75,327 (43.8%)
  - `view_details` — 45,638 (26.5%)
  - `none` — 33,713 (19.6%)
  - `add_to_my_list` — 17,247 (10.0%)

## Section distribution

  - `search_results` — 125,267 (72.9%)
  - `top_searches` — 20,557 (12.0%)
  - `suggested` — 18,668 (10.9%)
  - `voice` — 7,433 (4.3%)

## Potential relationships

- `displayed_title_id` → `catalog`.
- `profile_id` → `profiles`.
- `device_id` → `devices`.

## What can this dataset help us understand?

- What content members are looking for.
- Whether unsuccessful searches (no result, no action) signal unmet content needs.
- How often members search vs. browse organically.
