# 02 — profiles

## What is this dataset?

Jetflix allows one account to have several viewer **profiles** (like Netflix — e.g., "Mum", "Dad",
"Kids"). This table lists all profiles that still exist at extraction time. Deleted profiles are
removed from this table, but their viewing history rows remain in other tables.

## What does one row represent?

One row = one profile within one account.

## Size

| Fact | Value |
|---|---|
| Rows | 101,584 |
| Columns | 12 |
| Memory (approx.) | 30.41 MB |

Expected: 101,584 rows. Average of ~2 profiles per account.

## Important columns

- **`profile_id`** — unique ID for the profile. Primary key.
- **`account_id`** — which account this profile belongs to. Foreign key → `accounts`.
- **`is_kids`** — 1 if this is a kids profile.
- **`maturity_level`** — `ALL` for adult profiles; `TV-Y7` or `TV-PG` for kids profiles.
- **`is_account_owner`** — 1 for the main (primary) profile of the account.
- **`created_ts`** — when the profile was created.
- **`deleted_ts`** — when the profile was deleted; NULL if it still exists.

## Date ranges

- `created_ts`: 2023-10-01 to 2026-09-30
- `deleted_ts`: 2025-09-30 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `deleted_ts` | 100,903 | 99.33% |

> `deleted_ts` is NULL for profiles that have **not** been deleted — that is expected and fine.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Maturity level distribution

  - `ALL` — 87,159 (85.8%)
  - `TV-PG` — 8,696 (8.6%)
  - `TV-Y7` — 5,729 (5.6%)

## Language distribution

  - `en` — 95,479 (94.0%)
  - `es` — 6,105 (6.0%)

## Potential relationships

- `profile_id` → `viewing_activity`, `search_history`, `ratings`, `my_list`, `clickstream`.
- `account_id` → `accounts`.

## Anything unusual?

- Profiles purged under a privacy/deletion request are removed from this table, but their old
  viewing/search/ratings rows remain elsewhere (~0.04% of viewing rows have no matching profile here).
  This is a known "orphan" — not an error.

## What can this dataset help us understand?

- How many profiles each account has (household size proxy).
- Whether the account has a kids profile (family segment indicator).
- Profile creation and deletion patterns over time.
