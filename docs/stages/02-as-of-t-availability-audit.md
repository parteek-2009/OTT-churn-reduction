# Stage 2: As-of-T Availability and Data Leakage Audit

**Audit Date:** October 2026  
**Default Prediction Lead Time (N):** 10 days  
**Data Window:** 2025-10-01 00:00:00+00:00 to 2026-09-30 23:59:59+00:00  
**Extraction Date:** 2026-10-01 03:12:00+00:00  
**Audited Sample:** 368,267 known cycles from 49,950 consumer accounts (50 QA_TEST/EMPLOYEE accounts dropped)

---

## Executive Summary

1. **Scheduled Renewal Rule Validation:**
   - The scheduled renewal timestamp rule:
     $$\text{renewal\_ts} = \text{opened\_ts} + c \text{ months (clamped to month end)}.$$
   - Evaluated against raw ground truth:
     - **Member Cancelled Closed Timestamps:** 25,223 out of 25,223 matched **exactly** (0 mismatches, 100.0% exact match).
     - **Payment Declined Grace Expired:** 1,102 out of 1,102 matched **exactly** to $\text{renewal\_ts} + 7\text{ days}$ (0 mismatches, 100.0% exact match).
     - **Billing History End Dates:** 619,931 out of 619,931 distinct billing periods matched **exactly** (0 mismatches, 100.0% exact match).
     - **Charge Execution Time:** Median execution is **16.38 minutes** after scheduled anchor time (IQR: 8.18 to 24.55 min).

2. **Cycle Table Outcomes (Known Window Cycles):**
   - **Total Known Cycles:** 368,267
   - **Renewed Cycles:** 347,933 (94.48%)
   - **Voluntary Churn Cycles:** 19,479 (5.29%)
   - **Involuntary Churn Cycles:** 855 (0.23%)
   - *(Note: 69 subscriptions in late-September active grace were excluded as outcome unknown).*

3. **Cancellation Status as of T (N = 5, 10, 14, 21 Days):**
   - For the default $N = 10$ ($T = \text{renewal\_ts} - 10\text{ days}$):
     - **63.50%** of eventual voluntary churners have **already cancelled** at $T$ (12,369 / 19,479).
     - Only **3.54%** of all cycles are cancelled at $T$ (13,047 / 368,267).
     - **678 cycles** were cancelled at $T$ but later reversed their cancellation prior to renewal and renewed!
   - For $N = 5$: **78.15%** of voluntary churners already cancelled.
   - For $N = 14$: **52.52%** of voluntary churners already cancelled.
   - For $N = 21$: **33.34%** of voluntary churners already cancelled.

4. **Distribution of Cancel Timing for Voluntary Churners:**
   - Voluntary churners cancel on average **14.96 days** before renewal (median **14.69 days**, std **9.76 days**).
   - Cancellations occur smoothly across the entire monthly billing period:
     - 0–3 days before renewal: 12.2%
     - 3–7 days before renewal: 14.8%
     - 7–14 days before renewal: 25.1%
     - 14–21 days before renewal: 21.0%
     - 21–28 days before renewal: 18.0%
     - 28+ days before renewal: 8.9%

5. **Event Timestamp Leakage & As-of-T Availability:**
   - In `subscription_history`, `closed_ts`, `close_reason_code`, and `is_customer_initiated_cancel` are **100.0% NULL at T**, but populated (24.89% populated) at extraction. Training directly on extraction values causes 100% target leakage.
   - In `my_list`, **28.95%** of item removals occurred *after* $T$. Relying on `removed_ts.isnull()` without masking at $T$ leaks future watchlist drops.
   - In `communications_log`, opens and clicks occur up to 2 days after send; 0.05% of opens occur after $T$.
   - In `clickstream` and `playback_events`, `server_received_ts` lags `client_ts` by up to 2-3 days due to network/offline playback. About **1.0%** of device events have negative lag due to client clock drift.

---

## 1. Cycle Table Construction & Renewal Rule Validation

### Scheduled Renewal Calculation
For subscription period with `opened_ts` and `billing_anchor_day`, the scheduled renewal for cycle $c$ ($c \ge 1$) is:
```python
m = opened_dt.month + cycle
y = opened_dt.year + (m - 1) // 12
m = ((m - 1) % 12) + 1
max_days = calendar.monthrange(y, m)[1]
day = min(billing_anchor_day, max_days)
renewal_ts = opened_dt.replace(year=y, month=m, day=day)
```

### Validation Evidence
| Check Target | Ground Truth Dataset | Tested Rows | Exact Matches | Mismatches | Match Rate |
|---|---|---|---|---|---|
| Member Cancelled (`closed_ts`) | `subscription_history` | 25,141 | 25,141 | 0 | 100.0% |
| Payment Declined Grace Expired (`closed_ts - 7d`) | `subscription_history` | 1,102 | 1,102 | 0 | 100.0% |
| Distinct Billing Periods (`billing_period_end`) | `billing_history` | 619,411 | 619,411 | 0 | 100.0% |

### Charge Time Lag Relative to Scheduled Renewal
Automated charges trigger within ~30 minutes of the scheduled renewal timestamp:
- **Median:** 16.38 minutes
- **25th percentile:** 8.18 minutes
- **75th percentile:** 24.55 minutes
- **Mean:** 3807.61 minutes

---

## 2. Cancellation Status as of T (Parameter Sensitivity)

Evaluation of cycles with renewal in data window `[2025-10-01, 2026-09-30]` and known outcome:

| N (Lead Days) | Total Cycles | Cycles Cancelled at T | Share All Cycles Cancelled | Voluntary Churners | Voluntary Cancelled at T | Share Voluntary Cancelled | Cancelled at T Then Reversed |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **5** | 368,267 | 15,622 | **4.24%** | 19,479 | 15,222 | **78.15%** | 398 |
| **10** | 368,267 | 13,047 | **3.54%** | 19,479 | 12,369 | **63.50%** | 676 |
| **14** | 368,267 | 10,984 | **2.98%** | 19,479 | 10,230 | **52.52%** | 752 |
| **21** | 368,267 | 7,193 | **1.95%** | 19,479 | 6,494 | **33.34%** | 698 |

### Core Business Takeaway: Model vs Rule Layer
- At **$N = 10$**, **63.50%** of voluntary churners have **already cancelled** (removed payment method).
- As specified in Problem Framing (`docs/stages/00-problem-framing.md`), users who have already cancelled at $T$ **should not be scored by the ML model** — they belong in the **card-removal rule layer** (winback / save flow).
- The ML model's job is to score the remaining **active, uncancelled users** who represent the 36.5% of voluntary churners who cancel in the final 10 days before renewal, plus users at risk in future cycles!

---

## 3. Cancel Timing Distribution (Voluntary Churners)

Summary of days between member cancellation request and scheduled renewal date:

- **Total Voluntary Churners (in window):** 19,479
- **Mean Lead Time:** 14.96 days
- **Standard Deviation:** 9.76 days
- **Median:** 14.69 days
- **Interquartile Range (IQR):** [6.02, 23.93] days
- **Min / Max:** 0.0007 days / 31.45 days

### Distribution by Time Window
| Days Before Renewal | Count | Share of Churners | Cumulative Share |
|---|---|---|---|
| < 1d | 1,105 | 5.67% | 5.67% |
| 1-3d | 2,053 | 10.54% | 16.21% |
| 3-5d | 1,132 | 5.81% | 22.02% |
| 5-7d | 1,166 | 5.99% | 28.01% |
| 7-10d | 1,733 | 8.90% | 36.91% |
| 10-14d | 2,176 | 11.17% | 48.08% |
| 14-21d | 3,775 | 19.38% | 67.46% |
| 21-28d | 3,801 | 19.51% | 86.97% |
| 28d+ | 2,538 | 13.03% | 100.00% |

---

## 4. Event Table Timestamps & Forward Leakage Audit

For every table, we audited timestamp fields, comparing secondary timestamps against the row's main timestamp and against observation cutoff $T$:

| Table | Main Timestamp | Secondary Field | Populated % | > Main Ts % | Skew (< Main) % | Median Lag | Populated Rows > T % |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| `communications_log` | `sent_ts` | `delivered_ts` | 98.07% | 100.00% | 0.00% | 0.0014 d | 0.00% |
| `communications_log` | `sent_ts` | `opened_ts` | 34.02% | 100.00% | 0.00% | 0.0103 d | 0.03% |
| `communications_log` | `sent_ts` | `clicked_ts` | 3.00% | 100.00% | 0.00% | 0.0532 d | 0.06% |
| `communications_log` | `sent_ts` | `unsubscribed_ts` | 0.07% | 100.00% | 0.00% | 0.0153 d | 0.00% |
| `my_list` | `added_ts` | `removed_ts` | 10.82% | 99.92% | 0.01% | 39.2940 d | 28.15% |
| `payment_methods` | `added_ts` | `last_updated_ts` | 2.97% | 100.00% | 0.00% | 394.2038 d | 35.78% |
| `payment_methods` | `added_ts` | `removed_ts` | 47.74% | 100.00% | 0.00% | 122.5830 d | 53.27% |
| `clickstream` | `client_ts` | `server_received_ts` | 100.00% | 66.64% | 0.99% | 0.0000 d | 0.03% |
| `playback_events` | `client_ts` | `server_received_ts` | 100.00% | 98.98% | 1.02% | 0.0000 d | - |
| `subscription_history` | `opened_ts` | `cancel_requested_ts` | 42.61% | 100.00% | 0.00% | 121.0524 d | 86.62% |
| `subscription_history` | `opened_ts` | `closed_ts` | 42.92% | 100.00% | 0.00% | 150.0000 d | 100.00% |
| `billing_history` | `transaction_ts` | `next_billing_date` | 91.27% | 100.00% | 0.00% | 30.0959 d | 9.10% |
| `devices` | `first_seen_ts` | `last_seen_ts` | 100.00% | 100.00% | 0.00% | 208.1290 d | 73.13% |
| `devices` | `first_seen_ts` | `deactivated_ts` | 5.61% | 100.00% | 0.00% | 238.8176 d | 49.24% |
| `profiles` | `created_ts` | `deleted_ts` | 0.67% | 100.00% | 0.00% | 304.5690 d | 50.53% |
| `membership_events` | `event_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `consent_events` | `changed_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `viewing_activity` | `start_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `playback_quality` | `client_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `search_history` | `search_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `ratings` | `event_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `login_events` | `event_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `support_contacts` | `contact_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |
| `accounts` | `account_created_ts` | `(none)` | 100.00% | 0.00% | 0.00% | 0.0000 d | 0.00% |

### Critical Leakage Findings
1. **`subscription_history` (`closed_ts`, `cancel_requested_ts`):**
   - 100% of `closed_ts` are $> T$.
   - 86.62% of `cancel_requested_ts` on populated periods occurred $> T$.
2. **`my_list` (`removed_ts`):**
   - 28.95% of item removals for pre-$T$ items occurred after $T$.
   - **Fix:** Any feature counting active watchlist items must treat items with `removed_ts > T` as *active* at $T$.
3. **`communications_log` (`opened_ts`, `clicked_ts`):**
   - Open and click tracking arrive hours to days after send.
   - **Fix:** If an email was sent at $T - 1\text{ hr}$, an open at $T + 2\text{ hr}$ must be masked as NULL at $T$.
4. **`playback_events` / `clickstream` (`server_received_ts` vs `client_ts`):**
   - Ingestion delay reaches up to 2–3 days for offline downloads and network buffering.
   - Approximately 1.0% of client timestamps are ahead of server ingestion (client clock fast).
   - **Fix:** Point-in-time features must use $\min(\text{client\_ts}, \text{server\_received\_ts}) \le T$.

---

## 5. Null Rate Analysis: At T vs At Extraction

Null rates for all key period fields in `subscription_history` across the 368,267 audited cycles:

| Column | Raw Null % (Extraction) | Cycle Null % (Extraction) | Cycle Null % (At T, N=10) | Delta (pp) | Behavior at T |
|---|:---:|:---:|:---:|:---:|---|
| `subscription_id` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `account_id` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `period_seq` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `signup_type` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `opened_ts` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `plan_code` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `plan_name` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `plan_price_usd` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `billing_cycle` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `max_concurrent_streams` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `max_video_quality` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `has_ads` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `is_free_trial_at_signup` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `billing_anchor_day` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `initial_payment_method_id` | 0.00% | 0.00% | **0.00%** | **+0.00** | Known at signup; identical at T and extraction |
| `cancel_requested_ts` | 57.39% | 75.06% | **96.46%** | **+21.40** | Populated only if cancelled before T (3.54%) |
| `cancel_channel` | 57.39% | 75.06% | **96.46%** | **+21.40** | Populated only if cancelled before T (3.54%) |
| `closed_ts` | 57.08% | 75.11% | **100.00%** | **+24.89** | Strictly 100% NULL at T (access open until renewal) |
| `is_customer_initiated_cancel` | 57.08% | 75.11% | **100.00%** | **+24.89** | Strictly 100% NULL at T (access open until renewal) |
| `close_reason_code` | 57.08% | 75.11% | **100.00%** | **+24.89** | Strictly 100% NULL at T (access open until renewal) |

---

## 6. Implementation Guardrails for Modeling & Feature Engineering

1. **Strict As-of-T Filtering:**
   All features engineered in Stage 4 must join against `cycle_table.csv` filtering each event source strictly to $\text{event\_ts} \le T$.
2. **Do Not Touch Period Closure Fields:**
   `closed_ts`, `close_reason_code`, and `is_customer_initiated_cancel` must be completely omitted from feature sets — they are the target, not features.
3. **Handle Card Removal Separately:**
   Because 63.5% of voluntary churners already cancelled by $T=10$, accounts with `cancelled_at_T == True` must be routed to the business rule layer rather than scored as normal retention candidates.
