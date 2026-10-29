"""
Key Period Fields Null Rate Audit (Requirement 7).

Report null rates per column at T versus at extraction for the key period fields.
"""

from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np


PERIOD_FIELDS = [
    "subscription_id",
    "account_id",
    "period_seq",
    "signup_type",
    "opened_ts",
    "plan_code",
    "plan_name",
    "plan_price_usd",
    "billing_cycle",
    "max_concurrent_streams",
    "max_video_quality",
    "has_ads",
    "is_free_trial_at_signup",
    "billing_anchor_day",
    "initial_payment_method_id",
    "cancel_requested_ts",
    "cancel_channel",
    "closed_ts",
    "is_customer_initiated_cancel",
    "close_reason_code",
]


def audit_period_null_rates(
    data_dir: Path, df_annotated_cycles: pd.DataFrame, n_days: int = 10
) -> pd.DataFrame:
    """
    Compare null rates at extraction vs at T for key period fields.
    """
    sub = pd.read_csv(data_dir / "subscription_history.csv.gz")
    
    # Merge sub columns with annotated cycles, avoiding column collision
    cols_to_use = ["subscription_id"] + [c for c in PERIOD_FIELDS if c not in df_annotated_cycles.columns]
    cycle_merged = df_annotated_cycles.merge(
        sub[cols_to_use],
        on="subscription_id",
        how="left"
    )

    total_cycles = len(cycle_merged)
    results = []

    for col in PERIOD_FIELDS:
        # 1. Raw subscription_history null rate at extraction
        raw_nulls = int(sub[col].isnull().sum())
        raw_null_rate = raw_nulls / len(sub)

        # 2. Cycle-level null rate at extraction
        if col in cycle_merged.columns:
            ext_nulls = int(cycle_merged[col].isnull().sum())
        elif col in sub.columns:
            # Map through subscription_id
            ext_nulls = int(sub.set_index("subscription_id").loc[cycle_merged["subscription_id"], col].isnull().sum())
        else:
            ext_nulls = 0
        ext_null_rate = ext_nulls / total_cycles

        # 3. Cycle-level null rate as of T
        if col in ["closed_ts", "is_customer_initiated_cancel", "close_reason_code"]:
            # Access ends at renewal_ts or renewal_ts + 7 days; at T = renewal - N, it is NEVER closed
            t_nulls = total_cycles
            t_null_rate = 1.0
            status_note = "Strictly 100% NULL at T (access open until renewal)"
        elif col in ["cancel_requested_ts", "cancel_channel"]:
            # Non-null only if member initiated cancel before T
            t_nulls = int((~cycle_merged["cancelled_at_T"]).sum())
            t_null_rate = t_nulls / total_cycles
            status_note = f"Populated only if cancelled before T ({cycle_merged['cancelled_at_T'].mean()*100:.2f}%)"
        else:
            # Fixed signup-time / configuration attributes
            t_nulls = ext_nulls
            t_null_rate = ext_null_rate
            status_note = "Known at signup; identical at T and extraction"

        diff_pp = (t_null_rate - ext_null_rate) * 100.0

        results.append({
            "Column": col,
            "Raw_Null_Rate_Extraction": raw_null_rate,
            "Cycle_Nulls_Extraction": ext_nulls,
            "Cycle_Null_Rate_Extraction": ext_null_rate,
            "Cycle_Nulls_at_T": t_nulls,
            "Cycle_Null_Rate_at_T": t_null_rate,
            "Delta_Percentage_Points": diff_pp,
            "Status_at_T": status_note
        })

    return pd.DataFrame(results)
