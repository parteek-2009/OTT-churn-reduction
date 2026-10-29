"""
Analysis of cancel-and-renew behavior among non-churning customers.

Investigates:
1. Do customers who don't churn ever cancel their membership and then renew?
2. How often does this happen at the cycle level and at the account/subscription level?
3. How long do they stay in the cancelled state before reversing?
4. Is cancelling membership a strong signal of churning? (Signal strength, precision, recall, lift, relative risk).
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

try:
    from src.data_leakage_check_first.cycle_table import (
        build_cycle_table,
        compute_scheduled_renewal,
        load_valid_accounts,
        DATA_WINDOW_START,
        DATA_WINDOW_END,
    )
except ModuleNotFoundError:
    from data_leakage_check_first.cycle_table import (
        build_cycle_table,
        compute_scheduled_renewal,
        load_valid_accounts,
        DATA_WINDOW_START,
        DATA_WINDOW_END,
    )


def analyze_non_churner_cancels(data_dir: Path, output_dir: Path) -> Dict[str, Any]:
    valid_acc = load_valid_accounts(data_dir)
    
    # 1. Build cycles inside data window with known outcome
    df_cycles = build_cycle_table(data_dir, filter_known_in_window=True)
    
    # Also compute cycle_start_ts for each cycle
    # For cycle 1: cycle_start = opened_ts
    # For cycle c > 1: cycle_start = scheduled renewal of cycle c-1
    cycle_starts = []
    for row in df_cycles.itertuples(index=False):
        c = row.cycle
        op = row.opened_ts
        anchor = row.billing_anchor_day
        if c == 1:
            cycle_starts.append(op)
        else:
            prev_renewal = compute_scheduled_renewal(op, anchor, c - 1)
            cycle_starts.append(prev_renewal)
    df_cycles["cycle_start_ts"] = cycle_starts

    # 2. Load all membership events for valid accounts
    me = pd.read_csv(data_dir / "membership_events.csv.gz")
    me = me[me["account_id"].isin(valid_acc)].copy()
    me["event_dt"] = pd.to_datetime(me["event_ts"], utc=True)
    cancels = me[me["event_type"].isin(["CANCEL_REQUESTED", "CANCEL_REVERSED"])].sort_values("event_dt")

    # Map events by subscription_id
    events_by_sub: Dict[int, List[Tuple[pd.Timestamp, str, str]]] = {}
    for row in cancels.itertuples(index=False):
        sid = int(row.subscription_id)
        if sid not in events_by_sub:
            events_by_sub[sid] = []
        events_by_sub[sid].append((row.event_dt, row.event_type, row.source))

    # 3. For each cycle, examine cancel events that occurred DURING the cycle [cycle_start_ts, renewal_ts)
    has_cancel_req_during_cycle = []
    has_cancel_rev_during_cycle = []
    num_cancels_during_cycle = []
    num_reversals_during_cycle = []
    cancel_duration_hours = []

    for row in df_cycles.itertuples(index=False):
        sid = int(row.subscription_id)
        c_start = row.cycle_start_ts
        c_end = row.renewal_ts
        evs = events_by_sub.get(sid, [])

        req_in_cycle = []
        rev_in_cycle = []

        for dt, etype, src in evs:
            if c_start <= dt <= c_end:
                if etype == "CANCEL_REQUESTED":
                    req_in_cycle.append(dt)
                elif etype == "CANCEL_REVERSED":
                    rev_in_cycle.append(dt)

        has_cancel_req_during_cycle.append(len(req_in_cycle) > 0)
        has_cancel_rev_during_cycle.append(len(rev_in_cycle) > 0)
        num_cancels_during_cycle.append(len(req_in_cycle))
        num_reversals_during_cycle.append(len(rev_in_cycle))

        # If user cancelled and reversed during this cycle, compute duration
        if len(req_in_cycle) > 0 and len(rev_in_cycle) > 0:
            first_req = req_in_cycle[0]
            # find first reversal after first_req
            revs_after = [r for r in rev_in_cycle if r > first_req]
            if revs_after:
                dur_h = (revs_after[0] - first_req).total_seconds() / 3600.0
                cancel_duration_hours.append(dur_h)
            else:
                cancel_duration_hours.append(np.nan)
        else:
            cancel_duration_hours.append(np.nan)

    df_cycles["has_cancel_requested"] = has_cancel_req_during_cycle
    df_cycles["has_cancel_reversed"] = has_cancel_rev_during_cycle
    df_cycles["cancel_duration_hours"] = cancel_duration_hours

    # 4. Analyze Renewed (Non-Churning) Cycles
    renewed = df_cycles[df_cycles["outcome"] == "RENEWED"]
    vol_churn = df_cycles[df_cycles["outcome"] == "VOLUNTARY_CHURN"]
    invol_churn = df_cycles[df_cycles["outcome"] == "INVOLUNTARY_CHURN"]

    renewed_total = len(renewed)
    renewed_with_cancel = renewed["has_cancel_requested"].sum()
    renewed_with_cancel_pct = renewed_with_cancel / renewed_total * 100.0

    renewed_with_reversal = renewed["has_cancel_reversed"].sum()
    renewed_with_reversal_pct = renewed_with_reversal / renewed_total * 100.0

    # How many distinct subscribers who renewed ever had a cancel-and-reverse cycle?
    renewed_subs_total = renewed["subscription_id"].nunique()
    renewed_subs_with_cancel = renewed[renewed["has_cancel_requested"]]["subscription_id"].nunique()

    # Reversal durations
    dur_series = renewed["cancel_duration_hours"].dropna()
    dur_stats = {
        "count": int(dur_series.count()),
        "median_hours": float(dur_series.median()),
        "mean_hours": float(dur_series.mean()),
        "min_hours": float(dur_series.min()),
        "max_hours": float(dur_series.max()),
        "p25_hours": float(dur_series.quantile(0.25)),
        "p75_hours": float(dur_series.quantile(0.75)),
        "median_days": float(dur_series.median() / 24.0),
        "mean_days": float(dur_series.mean() / 24.0),
    }

    # 5. Signal Strength: Does CANCEL_REQUESTED predict Churn?
    # Contingency Table:
    #                 Voluntary Churn | Renewed | Total
    # Cancelled:           A          |    B    | A + B
    # Not Cancelled:       C          |    D    | C + D
    a = int(vol_churn["has_cancel_requested"].sum())
    b = int(renewed["has_cancel_requested"].sum())
    c = int((~vol_churn["has_cancel_requested"]).sum())
    d = int((~renewed["has_cancel_requested"]).sum())

    total_with_cancel = a + b
    total_without_cancel = c + d
    total_cycles = len(df_cycles)

    # Churn probabilities
    p_churn_given_cancel = a / total_with_cancel if total_with_cancel > 0 else 0.0
    p_renew_given_cancel = b / total_with_cancel if total_with_cancel > 0 else 0.0

    baseline_churn_rate = len(vol_churn) / total_cycles
    p_churn_given_no_cancel = c / total_without_cancel if total_without_cancel > 0 else 0.0

    lift = p_churn_given_cancel / baseline_churn_rate if baseline_churn_rate > 0 else 0.0
    relative_risk = p_churn_given_cancel / p_churn_given_no_cancel if p_churn_given_no_cancel > 0 else np.nan
    odds_ratio = (a * d) / (b * c) if (b * c) > 0 else np.nan

    # Overall Subscription Lifetime Level Check:
    # Out of all subscriptions in valid accounts, how many ever cancelled?
    sub = pd.read_csv(data_dir / "subscription_history.csv.gz")
    sub = sub[sub["account_id"].isin(valid_acc)].copy()
    
    total_subs = len(sub)
    closed_vol_subs = len(sub[sub["close_reason_code"] == "MEMBER_CANCELLED"])
    closed_invol_subs = len(sub[sub["close_reason_code"] == "PAYMENT_DECLINED_GRACE_EXPIRED"])
    open_subs = len(sub[sub["closed_ts"].isnull()])

    # How many subscriptions ever had a CANCEL_REQUESTED event?
    subs_with_cancel_event = set(cancels[cancels["event_type"] == "CANCEL_REQUESTED"]["subscription_id"].unique())
    subs_with_reversal_event = set(cancels[cancels["event_type"] == "CANCEL_REVERSED"]["subscription_id"].unique())

    total_subs_with_cancel = len(subs_with_cancel_event)
    subs_cancelled_and_closed_vol = len(subs_with_cancel_event & set(sub[sub["close_reason_code"] == "MEMBER_CANCELLED"]["subscription_id"]))
    subs_cancelled_but_still_open = len(subs_with_cancel_event & set(sub[sub["closed_ts"].isnull()]["subscription_id"]))
    subs_with_reversal = len(subs_with_reversal_event)

    results = {
        "cycle_level": {
            "total_known_cycles": total_cycles,
            "renewed_cycles": renewed_total,
            "voluntary_churn_cycles": len(vol_churn),
            "involuntary_churn_cycles": len(invol_churn),
            "renewed_cycles_with_cancel_request": int(renewed_with_cancel),
            "renewed_cycles_with_cancel_request_pct": float(renewed_with_cancel_pct),
            "renewed_cycles_with_cancel_reversed": int(renewed_with_reversal),
            "renewed_cycles_with_cancel_reversed_pct": float(renewed_with_reversal_pct),
            "renewed_subscribers_count": int(renewed_subs_total),
            "renewed_subscribers_with_cancel_count": int(renewed_subs_with_cancel),
            "renewed_subscribers_with_cancel_pct": float(renewed_subs_with_cancel / renewed_subs_total * 100.0),
            "reversal_duration_stats": dur_stats,
        },
        "signal_strength": {
            "total_cycles_with_cancel_request": total_with_cancel,
            "cancel_request_leading_to_churn_count (A)": a,
            "cancel_request_leading_to_renewal_count (B)": b,
            "no_cancel_request_churn_count (C)": c,
            "no_cancel_request_renewal_count (D)": d,
            "p_churn_given_cancel (Precision/Conversion)": float(p_churn_given_cancel),
            "p_renew_given_cancel (Reversal Rate)": float(p_renew_given_cancel),
            "baseline_voluntary_churn_rate": float(baseline_churn_rate),
            "p_churn_given_no_cancel": float(p_churn_given_no_cancel),
            "lift_over_baseline": float(lift),
            "relative_risk": float(relative_risk),
            "odds_ratio": float(odds_ratio),
        },
        "subscription_lifetime_level": {
            "total_valid_subscriptions": total_subs,
            "subscriptions_with_cancel_event": total_subs_with_cancel,
            "subscriptions_with_cancel_event_pct": float(total_subs_with_cancel / total_subs * 100.0),
            "cancelled_subscriptions_that_closed_voluntarily": subs_cancelled_and_closed_vol,
            "cancelled_subscriptions_that_closed_voluntarily_pct": float(subs_cancelled_and_closed_vol / total_subs_with_cancel * 100.0),
            "cancelled_subscriptions_with_reversal": subs_with_reversal,
            "cancelled_subscriptions_with_reversal_pct": float(subs_with_reversal / total_subs_with_cancel * 100.0),
        }
    }

    # Save structured results
    with open(output_dir / "non_churner_cancel_check.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    data_dir = Path("data/raw")
    output_dir = Path("results")
    res = analyze_non_churner_cancels(data_dir, output_dir)
    print(json.dumps(res, indent=2))
