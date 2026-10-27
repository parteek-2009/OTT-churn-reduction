# data_observations/

Plain-language notes for each of the 20 Jetflix raw datasets.

## What is this folder?

Each Markdown file in this folder describes one raw dataset.
The notes are written so that anyone — even someone new to data science — can understand:

- What the dataset contains.
- What one row means.
- Key columns and IDs.
- Missing values and data-quality notes.
- How this table connects to others.

## Files

| File | Dataset | Rows (expected) |
|---|---|---|
| [01_accounts.md](01_accounts.md) | accounts | 50,000 |
| [02_profiles.md](02_profiles.md) | profiles | 101,584 |
| [03_devices.md](03_devices.md) | devices | 153,144 |
| [04_payment_methods.md](04_payment_methods.md) | payment_methods | 65,246 |
| [05_subscription_history.md](05_subscription_history.md) | subscription_history | 61,331 |
| [06_billing_history.md](06_billing_history.md) | billing_history | 677,917 |
| [07_membership_events.md](07_membership_events.md) | membership_events | 271,991 |
| [08_consent_events.md](08_consent_events.md) | consent_events | 451,401 |
| [09_viewing_activity.md](09_viewing_activity.md) | viewing_activity | 3,326,139 |
| [10_playback_events.md](10_playback_events.md) | playback_events | 3,922,212 |
| [11_playback_quality.md](11_playback_quality.md) | playback_quality | 791,633 |
| [12_search_history.md](12_search_history.md) | search_history | 171,925 |
| [13_clickstream.md](13_clickstream.md) | clickstream | 2,158,373 |
| [14_ratings.md](14_ratings.md) | ratings | 58,124 |
| [15_my_list.md](15_my_list.md) | my_list | 95,650 |
| [16_login_events.md](16_login_events.md) | login_events | 198,805 |
| [17_support_contacts.md](17_support_contacts.md) | support_contacts | 16,247 |
| [18_communications_log.md](18_communications_log.md) | communications_log | 893,619 |
| [19_catalog.md](19_catalog.md) | catalog | 3,345 |
| [20_episodes.md](20_episodes.md) | episodes | 25,240 |

## Related notebook

`notebooks/01_data_exploration.ipynb` is the companion notebook.
It loads every dataset and prints the actual numbers that are referenced in these notes.

## How to re-run

1. Open a terminal in the project root.
2. Activate the virtual environment: `.venv\\Scripts\\activate` (Windows).
3. Open Jupyter: `jupyter notebook notebooks/01_data_exploration.ipynb`
4. Run all cells (Kernel → Restart & Run All).

The profiling stats are also saved to `data_observations_raw_stats.json` (project root) by
running `python notebooks/generate_observations.py`.

## Important caveats

- These notes describe the **raw data**. Nothing has been cleaned or transformed.
- `-1` is a sentinel meaning "not captured" — it is **not** a missing value or error.
- Empty fields are true NULLs.
- Some facts are from the schema documentation (`data/SCHEMA.md`); others come from running
  the notebook. Facts marked as "expected" come from the schema; actual row counts may differ
  by ±1 due to rounding in documentation.
- These notes do **not** make decisions about what to clean, impute, or exclude.
  Those decisions belong in the next phase.
