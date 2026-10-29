"""
Event Timestamp Audit.

Requirement 6:
For every event table, list each timestamp field and flag rows where a field is
later than the row's main timestamp or later than T (opened_ts, clicked_ts,
removed_ts, server_received_ts vs client_ts). Report how common it is.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np


EVENT_TABLE_CONFIGS = [
    {
        "table": "communications_log",
        "main_ts": "sent_ts",
        "secondary_ts": ["delivered_ts", "opened_ts", "clicked_ts", "unsubscribed_ts"],
        "account_id_col": "account_id",
        "description": "Outbound messaging (email, SMS, push)"
    },
    {
        "table": "my_list",
        "main_ts": "added_ts",
        "secondary_ts": ["removed_ts"],
        "account_id_col": "account_id",
        "description": "Watchlist items"
    },
    {
        "table": "payment_methods",
        "main_ts": "added_ts",
        "secondary_ts": ["last_updated_ts", "removed_ts"],
        "account_id_col": "account_id",
        "description": "Payment methods on file"
    },
    {
        "table": "clickstream",
        "main_ts": "client_ts",
        "secondary_ts": ["server_received_ts"],
        "account_id_col": "account_id",
        "description": "UI event stream (90-day retention)"
    },
    {
        "table": "playback_events",
        "main_ts": "client_ts",
        "secondary_ts": ["server_received_ts"],
        "account_id_col": None,  # view_id based, large 3.9M
        "description": "Video playback events (90-day retention)"
    },
    {
        "table": "subscription_history",
        "main_ts": "opened_ts",
        "secondary_ts": ["cancel_requested_ts", "closed_ts"],
        "account_id_col": "account_id",
        "description": "Subscription period history"
    },
    {
        "table": "billing_history",
        "main_ts": "transaction_ts",
        "secondary_ts": ["next_billing_date"],
        "account_id_col": "account_id",
        "description": "Billing transaction attempts and auths"
    },
    {
        "table": "devices",
        "main_ts": "first_seen_ts",
        "secondary_ts": ["last_seen_ts", "deactivated_ts"],
        "account_id_col": "account_id",
        "description": "Registered devices"
    },
    {
        "table": "profiles",
        "main_ts": "created_ts",
        "secondary_ts": ["deleted_ts"],
        "account_id_col": "account_id",
        "description": "Profiles per account"
    },
    # Single timestamp event tables:
    {
        "table": "membership_events",
        "main_ts": "event_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Membership lifecycle event log"
    },
    {
        "table": "consent_events",
        "main_ts": "changed_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Consent status change log"
    },
    {
        "table": "viewing_activity",
        "main_ts": "start_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Title and episode playbacks"
    },
    {
        "table": "playback_quality",
        "main_ts": "client_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "QoE session telemetry (90-day retention)"
    },
    {
        "table": "search_history",
        "main_ts": "search_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Search queries and actions"
    },
    {
        "table": "ratings",
        "main_ts": "event_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Thumbs ratings log"
    },
    {
        "table": "login_events",
        "main_ts": "event_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Authentication and security events"
    },
    {
        "table": "support_contacts",
        "main_ts": "contact_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Customer service contacts"
    },
    {
        "table": "accounts",
        "main_ts": "account_created_ts",
        "secondary_ts": [],
        "account_id_col": "account_id",
        "description": "Account master snapshot"
    }
]


def audit_table_timestamps(
    data_dir: Path,
    config: Dict[str, Any],
    df_cycles: Optional[pd.DataFrame] = None,
    n_days: int = 10
) -> Dict[str, Any]:
    """
    Run timestamp audit for a single table.
    """
    tbl = config["table"]
    main_col = config["main_ts"]
    sec_cols = config["secondary_ts"]
    file_path = data_dir / f"{tbl}.csv.gz"

    if not file_path.exists():
        return {"table": tbl, "error": "File not found"}

    usecols = [main_col] + sec_cols
    if tbl == "subscription_history" and "subscription_id" not in usecols:
        usecols.append("subscription_id")
    if config["account_id_col"] and config["account_id_col"] not in usecols:
        usecols.append(config["account_id_col"])

    df = pd.read_csv(file_path, usecols=usecols)
    total_rows = len(df)
    main_dt = pd.to_datetime(df[main_col], utc=True)

    table_report: Dict[str, Any] = {
        "table": tbl,
        "description": config["description"],
        "total_rows": total_rows,
        "main_timestamp_col": main_col,
        "secondary_fields": []
    }

    # If no secondary timestamps, report single timestamp summary
    if not sec_cols:
        return table_report

    for sec_col in sec_cols:
        sec_dt = pd.to_datetime(df[sec_col], utc=True)
        pop_count = int(sec_dt.notnull().sum())
        null_count = total_rows - pop_count
        pop_pct = pop_count / total_rows * 100.0
        null_pct = null_count / total_rows * 100.0

        mask = sec_dt.notnull() & main_dt.notnull()
        diff_sec = (sec_dt[mask] - main_dt[mask]).dt.total_seconds()

        later_count = int((diff_sec > 0).sum())
        equal_count = int((diff_sec == 0).sum())
        earlier_count = int((diff_sec < 0).sum())

        later_pct_total = later_count / total_rows * 100.0
        later_pct_pop = (later_count / pop_count * 100.0) if pop_count > 0 else 0.0

        field_stat: Dict[str, Any] = {
            "field": sec_col,
            "populated_count": pop_count,
            "populated_pct": pop_pct,
            "null_count": null_count,
            "null_pct": null_pct,
            "later_than_main_count": later_count,
            "later_than_main_pct_total": later_pct_total,
            "later_than_main_pct_populated": later_pct_pop,
            "equal_to_main_count": equal_count,
            "equal_to_main_pct": equal_count / total_rows * 100.0,
            "earlier_than_main_count": earlier_count,
            "earlier_than_main_pct": earlier_count / total_rows * 100.0,
        }

        if later_count > 0:
            delay_days = diff_sec[diff_sec > 0] / 86400.0
            field_stat["delay_days_median"] = float(delay_days.median())
            field_stat["delay_days_mean"] = float(delay_days.mean())
            field_stat["delay_days_min"] = float(delay_days.min())
            field_stat["delay_days_max"] = float(delay_days.max())

        # Now evaluate "later than T" for rows where main_ts <= T
        if df_cycles is not None:
            # We sample cycles if necessary to keep audit fast and representative
            field_stat.update(
                evaluate_later_than_T(
                    df, tbl, main_col, sec_col, config["account_id_col"], df_cycles, n_days
                )
            )

        table_report["secondary_fields"].append(field_stat)

    return table_report


def evaluate_later_than_T(
    df_table: pd.DataFrame,
    table_name: str,
    main_col: str,
    sec_col: str,
    account_id_col: Optional[str],
    df_cycles: pd.DataFrame,
    n_days: int = 10
) -> Dict[str, Any]:
    """
    Evaluate how often a secondary timestamp is > T for rows where main_ts <= T.
    """
    res: Dict[str, Any] = {
        f"later_than_T_N{n_days}_count": None,
        f"later_than_T_N{n_days}_pct": None,
    }

    # Case 1: subscription_history table matches directly on subscription_id
    if table_name == "subscription_history":
        cycles_t = df_cycles[["subscription_id", "renewal_ts"]].copy()
        cycles_t["T"] = cycles_t["renewal_ts"] - pd.Timedelta(days=n_days)
        merged = cycles_t.merge(
            df_table[["subscription_id", main_col, sec_col]], on="subscription_id", how="inner"
        )
        main_dt = pd.to_datetime(merged[main_col], utc=True)
        sec_dt = pd.to_datetime(merged[sec_col], utc=True)
        t_dt = merged["T"]

        # Only rows where main_ts <= T
        pre_t = merged[main_dt <= t_dt]
        sec_dt_pre = sec_dt[main_dt <= t_dt]
        pop_pre_t = sec_dt_pre.notnull()

        later_than_t = (sec_dt_pre > pre_t["T"]) & pop_pre_t
        res[f"later_than_T_N{n_days}_count"] = int(later_than_t.sum())
        res[f"later_than_T_N{n_days}_pct_populated"] = float(
            later_than_t.sum() / pop_pre_t.sum() * 100.0
        ) if pop_pre_t.sum() > 0 else 0.0
        res[f"later_than_T_N{n_days}_pct_all_pre_T"] = float(
            later_than_t.sum() / len(pre_t) * 100.0
        ) if len(pre_t) > 0 else 0.0
        return res

    # Case 2: account-level activity tables (my_list, communications_log, payment_methods, clickstream)
    if account_id_col and account_id_col in df_table.columns:
        # Sample 10,000 cycles for rapid, highly representative statistical convergence
        np.random.seed(42)
        sample_size = min(10000, len(df_cycles))
        sample_cycles = df_cycles.sample(sample_size).copy()
        sample_cycles["T"] = sample_cycles["renewal_ts"] - pd.Timedelta(days=n_days)

        merged = sample_cycles[["account_id", "T"]].merge(
            df_table[[account_id_col, main_col, sec_col]],
            left_on="account_id",
            right_on=account_id_col,
            how="inner"
        )
        main_dt = pd.to_datetime(merged[main_col], utc=True)
        sec_dt = pd.to_datetime(merged[sec_col], utc=True)
        t_dt = merged["T"]

        valid_pre_t = main_dt <= t_dt
        pre_t_df = merged[valid_pre_t]
        sec_pre_t = sec_dt[valid_pre_t]
        pop_mask = sec_pre_t.notnull()

        later_than_t = (sec_pre_t > pre_t_df["T"]) & pop_mask
        res[f"sample_cycles_evaluated"] = sample_size
        res[f"rows_pre_T_sample"] = int(len(pre_t_df))
        res[f"later_than_T_N{n_days}_count_sample"] = int(later_than_t.sum())
        res[f"later_than_T_N{n_days}_pct_populated"] = float(
            later_than_t.sum() / pop_mask.sum() * 100.0
        ) if pop_mask.sum() > 0 else 0.0
        res[f"later_than_T_N{n_days}_pct_all_pre_T"] = float(
            later_than_t.sum() / len(pre_t_df) * 100.0
        ) if len(pre_t_df) > 0 else 0.0

    return res


def run_full_timestamp_audit(
    data_dir: Path, df_cycles: Optional[pd.DataFrame] = None, n_days: int = 10
) -> List[Dict[str, Any]]:
    """
    Run audit across all configured tables.
    """
    reports = []
    for cfg in EVENT_TABLE_CONFIGS:
        rep = audit_table_timestamps(data_dir, cfg, df_cycles=df_cycles, n_days=n_days)
        reports.append(rep)
    return reports
