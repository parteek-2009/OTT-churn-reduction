# 10 — playback_events

## What is this dataset?

Fine-grained **play-trace events** within each viewing session — when the video started, paused,
seeked, and stopped. This is the most granular playback data. **Covers only the last 90 days
(2026-07-03 to 2026-09-30).**

## What does one row represent?

One row = one player event during one viewing session.

## Size

| Fact | Value |
|---|---|
| Rows | 3,922,212 |
| Columns | 7 |
| Memory (approx.) | 874.11 MB |

Expected: ~3.9 million rows. Multiple events per view.

## Important columns

> No single-column primary key. The composite key is `(view_id, event_seq)`.

- **`view_id`** — which viewing session this event belongs to. Foreign key → `viewing_activity`.
- **`event_seq`** — order of events within the view.
- **`event_type`** — `start`, `playing`, `paused`, `reposition` (seek, skip intro), or `stopped`.
- **`client_ts`** — device clock time. Some devices have clocks off by a few minutes.
- **`server_received_ts`** — when the event reached the server. Offline playback can arrive hours
  or days late.
- **`session_offset_ms`** — milliseconds since the view started (wall clock, includes pauses).
- **`media_offset_ms`** — position within the video (milliseconds).

## Date range

- `client_ts`: 2026-07-03 to 2026-10-01
- `server_received_ts`: 2026-07-03 to 2026-09-30

## Missing values

No missing values.

## Duplicate rows

Fully duplicated rows: **9,749** (0.249%)
*(Expected: ~0.25% are client re-sends — the client sometimes sends the same event twice.)*

## Event type distribution

  - `playing` — 1,567,211 (40.0%)
  - `start` — 787,980 (20.1%)
  - `stopped` — 787,940 (20.1%)
  - `paused` — 496,690 (12.7%)
  - `reposition` — 282,391 (7.2%)

## Potential relationships

- `view_id` → `viewing_activity`.

## Anything unusual?

- `client_ts` can be a few minutes off the true time on ~2% of devices with skewed clocks.
- `server_received_ts` can be hours or days later than `client_ts` for offline (downloaded)
  playback.
- Duplicate rows (~0.25%) are client re-sends, not recording errors. They need deduplication
  before analysis.
- This table only covers the last 90 days. There are no rows for older viewing sessions even
  if those sessions appear in `viewing_activity`.

## What can this dataset help us understand?

- Exact play/pause/seek patterns during a viewing session.
- Whether viewers complete content or stop early (position at `stopped` event).
- Skip-intro behaviour.
