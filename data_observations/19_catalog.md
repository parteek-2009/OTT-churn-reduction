# 19 — catalog

## What is this dataset?

The **reference catalog** of all titles available (or previously available) on Jetflix — movies,
series, limited series, and stand-up specials. All title names are fictional.

## What does one row represent?

One row = one title (movie, series, special, or limited series).

## Size

| Fact | Value |
|---|---|
| Rows | 3,345 |
| Columns | 18 |
| Memory (approx.) | 1.89 MB |

Expected: 3,345 rows (2,023 movies, 1,091 series, 121 limited series, 110 specials).

## Important columns

- **`title_id`** — unique ID. Primary key.
- **`title_name`** — fictional title name.
- **`title_type`** — `MOVIE`, `SERIES`, `LIMITED_SERIES`, or `SPECIAL`.
- **`primary_genre`** / **`secondary_genre`** — genre tags (secondary often NULL).
- **`maturity_rating`** — US TV or MPA rating.
- **`is_jetflix_original`** — 1 if a Jetflix original production.
- **`is_kids_content`** — 1 if categorised as kids content.
- **`has_branched_playback`** — 1 for interactive titles.
- **`promo_tier`** — marketing priority: `A` (big launch), `B`, `C`; NULL for older library titles.
- **`available_from`** / **`available_until`** — first and last day on Jetflix. `available_until`
  is NULL for titles still available.
- **`runtime_min`** — for movies and specials.
- **`num_seasons`** / **`num_episodes`** — for series.

## Date ranges

- `available_from`: N/A
- `available_until`: N/A

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `available_until` | 2,843 | 84.99% |
| `num_seasons` | 2,133 | 63.77% |
| `secondary_genre` | 2,133 | 63.77% |
| `num_episodes` | 2,133 | 63.77% |
| `promo_tier` | 1,244 | 37.19% |

> `secondary_genre` is often NULL (not all titles have a second genre).
> `runtime_min` is NULL for series (they have `num_seasons` / `num_episodes` instead).
> `num_seasons` / `num_episodes` are NULL for movies and specials.
> `available_until` is NULL for titles still on the platform.
> `maturity_rating` is NULL for a few titles.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Title type distribution

  - `MOVIE` — 2,023 (60.5%)
  - `SERIES` — 1,091 (32.6%)
  - `LIMITED_SERIES` — 121 (3.6%)
  - `SPECIAL` — 110 (3.3%)

## Primary genre distribution

  - `Comedy` — 426 (12.7%)
  - `Drama` — 422 (12.6%)
  - `Crime & Thriller` — 357 (10.7%)
  - `Action & Adventure` — 303 (9.1%)
  - `Documentary` — 261 (7.8%)

## Promo tier distribution

  - `C` — 1,949 (58.3%)
  - `(null / missing)` — 1,244 (37.2%)
  - `B` — 130 (3.9%)
  - `A` — 22 (0.7%)

## Potential relationships

- `title_id` → `viewing_activity`, `playback_quality`, `search_history`, `ratings`, `my_list`,
  `clickstream`.
- `title_id` → `episodes` (one title has many episodes).

## What can this dataset help us understand?

- Content characteristics associated with high viewing or retention.
- Whether Jetflix Originals or promo-tier-A titles drive subscriber engagement.
- License expiry (`available_until`) — titles leaving the platform may frustrate viewers.
