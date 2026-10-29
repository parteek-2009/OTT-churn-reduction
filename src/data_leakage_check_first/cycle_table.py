"""
Cycle table construction, validation, and as-of-T availability evaluation.

Key Requirements:
1. One row per (subscription_id, cycle) with scheduled renewal_ts computed from
   opened_ts + billing_anchor_day (clamped to month end), same rule for everyone.
   Check against billing_history charge times and, for churners, closed_ts.
   Do not define renewal_ts from closed_ts.
2. T = renewal_ts - N days. Keep only cycles whose renewal is inside the data window
   and whose outcome is known. Drop QA_TEST and EMPLOYEE accounts.
3. Compute from membership_events: cancelled_at_T, cancel_ts, and days_before_renewal.
4. Report for N = 5, 10, 14, 21: share of cycles already cancelled at T, and
   share of eventual voluntary churners already cancelled at T.
5. Report distribution of cancel timing for voluntary churners.
"""

import calendar
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import pandas as pd
import numpy as np

DATA_WINDOW_START = pd.to_datetime("2025-10-01T00:00:00Z")
DATA_WINDOW_END = pd.to_datetime("2026-09-30T23:59:59Z")
EXTRACTION_DATE = pd.to_datetime("2026-10-01T03:12:00Z")


def compute_scheduled_renewal(opened_dt: pd.Timestamp, anchor_day: int, cycle: int) -> pd.Timestamp:
    """
    Compute scheduled renewal_ts for cycle c (1, 2, ...).
    Cycle 1 renewal occurs 1 month after opened_dt, clamped to month end.
    Cycle c renewal occurs c months after opened_dt, clamped to month end.
    Time of day (hour, minute, second) is preserved from opened_dt.
    """
    m = opened_dt.month + cycle
    y = opened_dt.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    max_days = calendar.monthrange(y, m)[1]
    day = min(anchor_day, max_days)
    return opened_dt.replace(year=y, month=m, day=day)


def load_valid_accounts(data_dir: Path) -> Set[int]:
    """
    Return set of valid CONSUMER account IDs (dropping QA_TEST and EMPLOYEE).
    """
    acc = pd.read_csv(data_dir / "accounts.csv.gz", usecols=["account_id", "account_type"])
    valid_acc = set(acc[~acc["account_type"].isin(["QA_TEST", "EMPLOYEE"])]["account_id"])
    return valid_acc


def validate_renewal_rule(data_dir: Path, valid_acc: Set[int]) -> Dict[str, Any]:
    """
    Validate scheduled renewal rule against billing_history charge times and closed_ts.
    """
    sub = pd.read_csv(data_dir / "subscription_history.csv.gz")
    sub = sub[sub["account_id"].isin(valid_acc)].copy()
    sub["opened_dt"] = pd.to_datetime(sub["opened_ts"])
    sub["closed_dt"] = pd.to_datetime(sub["closed_ts"])

    # 1. Check against MEMBER_CANCELLED closed_ts
    mem_canc = sub[sub["close_reason_code"] == "MEMBER_CANCELLED"].copy()
    diff_months_mc = (mem_canc["closed_dt"].dt.year - mem_canc["opened_dt"].dt.year) * 12 + (
        mem_canc["closed_dt"].dt.month - mem_canc["opened_dt"].dt.month
    )
    mc_matches = 0
    mc_mismatches = 0
    for row, c in zip(mem_canc.itertuples(index=False), diff_months_mc):
        pred = compute_scheduled_renewal(row.opened_dt, int(row.billing_anchor_day), int(c))
        if pred == row.closed_dt:
            mc_matches += 1
        else:
            mc_mismatches += 1

    # 2. Check against PAYMENT_DECLINED_GRACE_EXPIRED closed_ts
    # Grace expired closed_ts is renewal_ts + 7 days
    invol = sub[sub["close_reason_code"] == "PAYMENT_DECLINED_GRACE_EXPIRED"].copy()
    invol["sched_renewal"] = invol["closed_dt"] - pd.Timedelta(days=7)
    diff_months_invol = (invol["sched_renewal"].dt.year - invol["opened_dt"].dt.year) * 12 + (
        invol["sched_renewal"].dt.month - invol["opened_dt"].dt.month
    )
    invol_matches = 0
    invol_mismatches = 0
    for row, c in zip(invol.itertuples(index=False), diff_months_invol):
        pred = compute_scheduled_renewal(row.opened_dt, int(row.billing_anchor_day), int(c))
        if pred == row.sched_renewal:
            invol_matches += 1
        else:
            invol_mismatches += 1

    # 3. Check against billing_history distinct billing_period_end dates
    bh = pd.read_csv(data_dir / "billing_history.csv.gz", usecols=["subscription_id", "billing_period_start", "billing_period_end"])
    periods = bh[bh["billing_period_start"].notnull()][["subscription_id", "billing_period_start", "billing_period_end"]].drop_duplicates().copy()
    periods = periods.sort_values(["subscription_id", "billing_period_start"])
    periods["cycle"] = periods.groupby("subscription_id").cumcount() + 1
    periods = periods.merge(sub[["subscription_id", "opened_dt", "billing_anchor_day"]], on="subscription_id", how="inner")

    bh_matches = 0
    bh_mismatches = 0
    for row in periods.itertuples(index=False):
        pred_date = compute_scheduled_renewal(row.opened_dt, int(row.billing_anchor_day), int(row.cycle)).strftime("%Y-%m-%d")
        if pred_date == row.billing_period_end:
            bh_matches += 1
        else:
            bh_mismatches += 1

    # 4. Check charge timing delay relative to scheduled renewal
    charges = bh = pd.read_csv(
        data_dir / "billing_history.csv.gz",
        usecols=["subscription_id", "transaction_ts", "transaction_type", "pmt_status", "billing_period_start"]
    )
    appr_charges = charges[(charges["transaction_type"] == "CHARGE") & (charges["pmt_status"] == "approved")].copy()
    appr_charges["tx_dt"] = pd.to_datetime(appr_charges["transaction_ts"])
    appr_charges = appr_charges.sort_values(["subscription_id", "tx_dt"])
    appr_charges["charge_seq"] = appr_charges.groupby("subscription_id").cumcount()
    renewal_charges = appr_charges[appr_charges["charge_seq"] > 0].merge(
        sub[["subscription_id", "opened_dt", "billing_anchor_day"]], on="subscription_id", how="inner"
    )
    
    delays_minutes = []
    for row in renewal_charges.itertuples(index=False):
        pred_dt = compute_scheduled_renewal(row.opened_dt, int(row.billing_anchor_day), int(row.charge_seq))
        diff_min = (row.tx_dt - pred_dt).total_seconds() / 60.0
        delays_minutes.append(diff_min)

    delay_series = pd.Series(delays_minutes)

    return {
        "member_cancelled_total": len(mem_canc),
        "member_cancelled_exact_matches": mc_matches,
        "member_cancelled_mismatches": mc_mismatches,
        "payment_declined_total": len(invol),
        "payment_declined_exact_matches": invol_matches,
        "payment_declined_mismatches": invol_mismatches,
        "billing_period_end_total": len(periods),
        "billing_period_end_matches": bh_matches,
        "billing_period_end_mismatches": bh_mismatches,
        "charge_time_diff_minutes_median": float(delay_series.median()),
        "charge_time_diff_minutes_25p": float(delay_series.quantile(0.25)),
        "charge_time_diff_minutes_75p": float(delay_series.quantile(0.75)),
        "charge_time_diff_minutes_mean": float(delay_series.mean()),
    }


def build_cycle_table(data_dir: Path, filter_known_in_window: bool = True) -> pd.DataFrame:
    """
    Build the cycle table with one row per (subscription_id, cycle).
    Only valid accounts (excluding QA_TEST and EMPLOYEE).
    Filters to window [2025-10-01, 2026-09-30] and known outcome if requested.
    """
    valid_acc = load_valid_accounts(data_dir)

    me = pd.read_csv(data_dir / "membership_events.csv.gz", usecols=["account_id", "subscription_id", "event_type"])
    me_valid = me[me["account_id"].isin(valid_acc)]
    grace_started = set(me_valid[me_valid["event_type"] == "GRACE_STARTED"]["subscription_id"].dropna().unique())
    grace_resolved_or_closed = set(
        me_valid[me_valid["event_type"].isin(["GRACE_RESOLVED", "SUBSCRIPTION_CLOSED"])]["subscription_id"].dropna().unique()
    )
    unresolved_grace_subs = grace_started - grace_resolved_or_closed

    sub = pd.read_csv(data_dir / "subscription_history.csv.gz")
    sub = sub[sub["account_id"].isin(valid_acc)].copy()
    sub["opened_dt"] = pd.to_datetime(sub["opened_ts"])
    sub["closed_dt"] = pd.to_datetime(sub["closed_ts"])

    cycles: List[Tuple] = []

    for row in sub.itertuples(index=False):
        s_id = row.subscription_id
        a_id = row.account_id
        op = row.opened_dt
        anchor = int(row.billing_anchor_day)
        cl = row.closed_dt
        reason = row.close_reason_code

        c = 1
        while True:
            r_ts = compute_scheduled_renewal(op, anchor, c)

            if pd.notnull(cl):
                if reason == "MEMBER_CANCELLED":
                    if r_ts > cl:
                        break
                elif reason == "PAYMENT_DECLINED_GRACE_EXPIRED":
                    if r_ts > (cl - pd.Timedelta(days=7)):
                        break
                else:
                    if r_ts > cl:
                        break
            else:
                if r_ts > EXTRACTION_DATE:
                    break

            outcome: Optional[str] = None
            if pd.notnull(cl):
                if reason == "MEMBER_CANCELLED" and r_ts == cl:
                    outcome = "VOLUNTARY_CHURN"
                elif reason == "PAYMENT_DECLINED_GRACE_EXPIRED" and r_ts == (cl - pd.Timedelta(days=7)):
                    outcome = "INVOLUNTARY_CHURN"
                elif r_ts < cl:
                    outcome = "RENEWED"
            else:
                if s_id in unresolved_grace_subs:
                    if r_ts >= pd.to_datetime("2026-09-24T00:00:00Z"):
                        outcome = "UNKNOWN"
                    else:
                        outcome = "RENEWED"
                else:
                    outcome = "RENEWED"

            is_in_window = (DATA_WINDOW_START <= r_ts <= DATA_WINDOW_END)

            if not filter_known_in_window or (is_in_window and outcome != "UNKNOWN"):
                cycles.append((
                    s_id, a_id, c, op, anchor, r_ts, cl, reason, outcome, is_in_window
                ))

            if outcome in ["VOLUNTARY_CHURN", "INVOLUNTARY_CHURN"]:
                break
            c += 1

    df_cycles = pd.DataFrame(
        cycles,
        columns=[
            "subscription_id", "account_id", "cycle", "opened_ts", "billing_anchor_day",
            "renewal_ts", "closed_ts", "close_reason_code", "outcome", "is_in_window"
        ]
    )
    return df_cycles


def load_cancel_events(data_dir: Path, valid_acc: Set[int]) -> Dict[int, List[Tuple[pd.Timestamp, str]]]:
    """
    Load CANCEL_REQUESTED and CANCEL_REVERSED events sorted by event_ts.
    """
    me = pd.read_csv(data_dir / "membership_events.csv.gz", usecols=["account_id", "subscription_id", "event_type", "event_ts"])
    me = me[me["account_id"].isin(valid_acc)]
    cancels = me[me["event_type"].isin(["CANCEL_REQUESTED", "CANCEL_REVERSED"])].copy()
    cancels["event_dt"] = pd.to_datetime(cancels["event_ts"])
    cancels = cancels.sort_values("event_dt")

    cancel_events_by_sub: Dict[int, List[Tuple[pd.Timestamp, str]]] = {}
    for row in cancels.itertuples(index=False):
        sid = int(row.subscription_id)
        if sid not in cancel_events_by_sub:
            cancel_events_by_sub[sid] = []
        cancel_events_by_sub[sid].append((row.event_dt, row.event_type))

    return cancel_events_by_sub


def evaluate_cancel_at_T(
    cancel_events: List[Tuple[pd.Timestamp, str]], T: pd.Timestamp
) -> Tuple[bool, Optional[pd.Timestamp]]:
    """
    Evaluate if subscription was cancelled at T:
    latest CANCEL_REQUESTED before T with no later CANCEL_REVERSED before T.
    """
    latest_req = None
    latest_rev = None
    for dt, etype in cancel_events:
        if dt >= T:
            break
        if etype == "CANCEL_REQUESTED":
            latest_req = dt
        elif etype == "CANCEL_REVERSED":
            latest_rev = dt

    if latest_req is not None:
        if latest_rev is None or latest_rev < latest_req:
            return True, latest_req
    return False, None


def annotate_cycle_table_with_T(
    df_cycles: pd.DataFrame,
    cancel_events_by_sub: Dict[int, List[Tuple[pd.Timestamp, str]]],
    n_days: int = 10
) -> pd.DataFrame:
    """
    Annotate cycle table with as-of-T metrics:
    - T = renewal_ts - N days
    - cancelled_at_T (bool)
    - cancel_ts (timestamp of latest cancel request before T)
    - days_before_renewal (renewal_ts - cancel_ts in days)
    """
    df = df_cycles.copy()
    t_series = df["renewal_ts"] - pd.Timedelta(days=n_days)
    df["T"] = t_series
    df["N_days"] = n_days

    cancelled_at_T: List[bool] = []
    cancel_ts_list: List[Optional[pd.Timestamp]] = []
    days_before_renewal_list: List[float] = []

    for sid, r_ts, t_val in zip(df["subscription_id"], df["renewal_ts"], t_series):
        evs = cancel_events_by_sub.get(int(sid), [])
        is_canc, c_ts = evaluate_cancel_at_T(evs, t_val)
        cancelled_at_T.append(is_canc)
        cancel_ts_list.append(c_ts)
        if is_canc and c_ts is not None:
            days_diff = (r_ts - c_ts).total_seconds() / 86400.0
            days_before_renewal_list.append(days_diff)
        else:
            days_before_renewal_list.append(np.nan)

    df["cancelled_at_T"] = cancelled_at_T
    df["cancel_ts"] = cancel_ts_list
    df["days_before_renewal"] = days_before_renewal_list
    return df


def compute_n_summary(
    df_cycles: pd.DataFrame,
    cancel_events_by_sub: Dict[int, List[Tuple[pd.Timestamp, str]]],
    n_values: List[int] = [5, 10, 14, 21]
) -> pd.DataFrame:
    """
    Report for each N: share of cycles already cancelled at T, and
    share of eventual voluntary churners already cancelled at T.
    """
    records = []
    vol_churners = df_cycles[df_cycles["outcome"] == "VOLUNTARY_CHURN"]
    total_cycles = len(df_cycles)
    total_vol = len(vol_churners)

    for n in n_values:
        ann = annotate_cycle_table_with_T(df_cycles, cancel_events_by_sub, n_days=n)
        vol_ann = ann[ann["outcome"] == "VOLUNTARY_CHURN"]
        renewed_ann = ann[ann["outcome"] == "RENEWED"]

        all_canc_count = int(ann["cancelled_at_T"].sum())
        all_canc_share = float(ann["cancelled_at_T"].mean())

        vol_canc_count = int(vol_ann["cancelled_at_T"].sum())
        vol_canc_share = float(vol_ann["cancelled_at_T"].mean())

        renewed_canc_count = int(renewed_ann["cancelled_at_T"].sum())
        renewed_canc_share = float(renewed_ann["cancelled_at_T"].mean())

        records.append({
            "N_days": n,
            "Total_Cycles": total_cycles,
            "Cycles_Cancelled_at_T": all_canc_count,
            "Share_Cycles_Cancelled_at_T": all_canc_share,
            "Total_Voluntary_Churners": total_vol,
            "Voluntary_Churners_Cancelled_at_T": vol_canc_count,
            "Share_Voluntary_Churners_Cancelled_at_T": vol_canc_share,
            "Renewed_Cycles_Cancelled_at_T_Then_Reversed": renewed_canc_count,
            "Share_Renewed_Cycles_Cancelled_at_T": renewed_canc_share
        })

    return pd.DataFrame(records)


def compute_cancel_timing_distribution(
    data_dir: Path, valid_acc: Set[int], in_window_only: bool = True
) -> Dict[str, Any]:
    """
    Report the distribution of cancel timing (days before renewal) for voluntary churners.
    """
    sub = pd.read_csv(data_dir / "subscription_history.csv.gz")
    sub = sub[sub["account_id"].isin(valid_acc)].copy()
    vol = sub[sub["close_reason_code"] == "MEMBER_CANCELLED"].copy()
    vol["closed_dt"] = pd.to_datetime(vol["closed_ts"])
    vol["cancel_dt"] = pd.to_datetime(vol["cancel_requested_ts"])

    if in_window_only:
        vol = vol[(vol["closed_dt"] >= DATA_WINDOW_START) & (vol["closed_dt"] <= DATA_WINDOW_END)].copy()

    vol["days_before_renewal"] = (vol["closed_dt"] - vol["cancel_dt"]).dt.total_seconds() / 86400.0
    series = vol["days_before_renewal"]

    # Bucketed distribution
    bins = [0, 1, 3, 5, 7, 10, 14, 21, 28, 35]
    labels = ["< 1d", "1-3d", "3-5d", "5-7d", "7-10d", "10-14d", "14-21d", "21-28d", "28d+"]
    binned = pd.cut(series, bins=bins, labels=labels, right=False)
    counts = binned.value_counts().sort_index()
    shares = (counts / len(series)).to_dict()

    return {
        "count": int(series.count()),
        "mean": float(series.mean()),
        "std": float(series.std()),
        "min": float(series.min()),
        "p05": float(series.quantile(0.05)),
        "p10": float(series.quantile(0.10)),
        "p25": float(series.quantile(0.25)),
        "median": float(series.median()),
        "p75": float(series.quantile(0.75)),
        "p90": float(series.quantile(0.90)),
        "p95": float(series.quantile(0.95)),
        "max": float(series.max()),
        "bucket_counts": {str(k): int(v) for k, v in counts.items()},
        "bucket_shares": {str(k): float(v) for k, v in shares.items()},
    }
