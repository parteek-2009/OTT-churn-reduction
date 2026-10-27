# 11 — playback_quality

## What is this dataset?

Quality-of-Experience (QoE) telemetry for every **playback attempt**, including failed attempts
that never got video started. **Last 90 days only (2026-07-03 to 2026-09-30).**

## What does one row represent?

One row = one playback attempt (whether or not video actually played).

## Size

| Fact | Value |
|---|---|
| Rows | 791,633 |
| Columns | 19 |
| Memory (approx.) | 392.25 MB |

Expected: ~791,633 rows.

## Important columns

- **`playback_id`** — unique ID. Primary key.
- **`view_id`** — links to `viewing_activity`; NULL when the attempt failed before video started
  (no viewing row is written for those cases).
- **`account_id`** / **`device_id`** / **`title_id`** — who, on what device, watching what.
- **`startup_time_ms`** — time from play request to first video frame. `-1` means the attempt
  failed before starting (not an error — it is the sentinel for "not measured").
- **`rebuffer_count`** — number of stalls after video started.
- **`rebuffer_duration_ms`** — total stall time. `-1` on clients older than version 8.11.0 that
  did not report this metric.
- **`exit_before_video_start`** — 1 if the user left before any video played.
- **`error_code`** — player error code (NULL if no error).
- **`network_type`** — `wifi`, `ethernet`, `cellular`, or `offline_download`.
- **`peak_resolution`** — `480p`, `720p`, or `1080p`; NULL if nothing played.

## Date range

- `client_ts`: 2026-07-03 to 2026-09-30

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `error_code` | 786,567 | 99.36% |
| `cdn_pop` | 5,858 | 0.74% |
| `avg_bitrate_kbps` | 5,462 | 0.69% |
| `view_id` | 5,462 | 0.69% |
| `peak_resolution` | 5,462 | 0.69% |

> `view_id` is NULL for attempts that failed before video started — expected.
> `avg_bitrate_kbps` and `peak_resolution` are NULL when nothing played — expected.
> `isp_name` and `cdn_pop` are NULL for offline downloads — expected.

## Sentinel values (-1 = "not captured", not an error)

| Column | Count | % | Meaning |
|---|---|---|---|
| `startup_time_ms` | 3,301 | 0.4% | System did not capture this value |
| `rebuffer_duration_ms` | 359 | 0.0% | System did not capture this value |

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Network type distribution

  - `wifi` — 608,098 (76.8%)
  - `ethernet` — 141,620 (17.9%)
  - `cellular` — 36,021 (4.6%)
  - `offline_download` — 5,894 (0.7%)

## Peak resolution distribution

  - `1080p` — 432,098 (54.6%)
  - `720p` — 281,318 (35.5%)
  - `480p` — 72,780 (9.2%)
  - `(null / missing)` — 5,437 (0.7%)

## Top error codes

  - `(null / missing)` — 786,557 (99.4%)
  - `JF-1011` — 1,448 (0.2%)
  - `JF-3104` — 752 (0.1%)
  - `JF-7020` — 734 (0.1%)
  - `JF-5003` — 732 (0.1%)

## Potential relationships

- `view_id` → `viewing_activity`.
- `device_id` → `devices`.
- `title_id` → `catalog`.

## Anything unusual?

- `startup_time_ms = -1` is a sentinel, not a bad value — it means the attempt never started.
  These rows also have `exit_before_video_start = 1`.
- `rebuffer_duration_ms = -1` on old clients is also a sentinel — old clients did not report
  stall duration.
- Do not exclude `-1` rows as errors. Treat them as "not measured".

## What can this dataset help us understand?

- Whether poor streaming quality (long startup, frequent buffering) is associated with churn.
- Geographic or ISP-level quality differences.
- Failed playback attempts and their causes.
