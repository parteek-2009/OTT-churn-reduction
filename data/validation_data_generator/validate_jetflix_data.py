#!/usr/bin/env python3
"""
validate_jetflix_data.py - checks the generated Jetflix tables and writes validation_report.md.

    python validate_jetflix_data.py --data data --report validation_report.md
    python validate_jetflix_data.py --data data --quick        # rates only, no report
"""
import argparse
import os
import time

import numpy as np
import pandas as pd

WIN_START = pd.Timestamp("2025-10-01T00:00:00Z")
WIN_END = pd.Timestamp("2026-10-01T00:00:00Z")
SHORT_START = WIN_END - pd.Timedelta(days=90)
MONTHS = pd.date_range("2025-10-01", "2026-09-01", freq="MS", tz="UTC")


def rd(data, t, **kw):
    return pd.read_csv(os.path.join(data, t + ".csv.gz"), low_memory=False, **kw)


def ts(s):
    return pd.to_datetime(s, utc=True, format="ISO8601")


def subscription_metrics(sh, acc):
    consumer = set(acc.loc[acc.account_type == "CONSUMER", "account_id"])
    sh = sh[sh.account_id.isin(consumer)].copy()
    sh["o"] = ts(sh.opened_ts)
    sh["c"] = ts(sh.closed_ts)
    rows = []
    for m0 in MONTHS:
        m1 = m0 + pd.offsets.MonthBegin(1)
        active0 = ((sh.o <= m0) & (sh.c.isna() | (sh.c > m0))).sum()
        active1 = ((sh.o <= m1) & (sh.c.isna() | (sh.c > m1))).sum()
        inm = lambda col: (sh[col] > m0) & (sh[col] <= m1)
        vol = (inm("c") & (sh.is_customer_initiated_cancel == 1)).sum()
        inv = (inm("c") & (sh.is_customer_initiated_cancel == 0)).sum()
        joins = ((sh.o > m0) & (sh.o <= m1)).sum()
        rejoins = ((sh.o > m0) & (sh.o <= m1) & (sh.signup_type == "REJOIN")).sum()
        rows.append(dict(month=m0.strftime("%Y-%m"), active_start=active0, joins=joins, of_which_rejoins=rejoins,
                         vol_churn=vol, invol_churn=inv, active_end=active1,
                         vol_churn_rate=vol / active0, invol_rate=inv / active0, join_rate=joins / active0,
                         growth=active1 / active0 - 1))
    return pd.DataFrame(rows), sh


def reactivation(sh):
    """Kaplan-Meier time from a voluntary close in the window to the next period on the same account."""
    s = sh.sort_values(["account_id", "o"]).copy()
    s["next_o"] = s.groupby("account_id").o.shift(-1)
    v = s[(s.is_customer_initiated_cancel == 1) & (s.c >= WIN_START) & (s.c < WIN_END)].copy()
    dur = np.where(v.next_o.notna(), (v.next_o - v.c).dt.total_seconds() / 86400, (WIN_END - v.c).dt.total_seconds() / 86400)
    ev = v.next_o.notna().values
    order = np.argsort(dur)
    dur, ev = dur[order], ev[order]
    n = len(dur)
    surv, at_risk, out = 1.0, n, {}
    marks = [30, 60, 90, 180, 270, 330]
    i = 0
    for m in marks:
        while i < n and dur[i] <= m:
            if ev[i]:
                surv *= 1 - 1 / at_risk
            at_risk -= 1
            i += 1
        out[m] = 1 - surv
    # cohort view: closes in Oct-Nov 2025 (>= 10 months follow-up)
    early = v[v.c < pd.Timestamp("2025-12-01", tz="UTC")]
    r90 = ((early.next_o - early.c).dt.days <= 90).mean()
    r300 = ((early.next_o - early.c).dt.days <= 300).mean()
    return out, len(v), r90, r300


def tenure_shape(sh):
    """Voluntary churn by renewal cycle of the current period: closes at the end of cycle j / periods that
    started cycle j inside the window and whose outcome is observed before the window ends."""
    s = sh.copy()
    month = pd.Timedelta(days=30.44)
    n_close = ((s.c - s.o) / month).round()
    out = []
    for j in range(1, 37):
        start = s.o + (j - 1) * month
        end = s.o + j * month
        exposed = (start >= WIN_START) & (end <= WIN_END) & (s.c.isna() | (s.c > start + pd.Timedelta(days=3)))
        churned = exposed & (s.is_customer_initiated_cancel == 1) & (n_close == j)
        out.append((j - 1, churned.sum() / max(exposed.sum(), 1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--report", default="validation_report.md")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    t_start = time.time()
    D = a.data
    acc = rd(D, "accounts")
    sh = rd(D, "subscription_history")
    mm, shc = subscription_metrics(sh, acc)
    km, n_vol, r90c, r300c = reactivation(shc)
    ten = tenure_shape(shc)
    summary = dict(vol=mm.vol_churn_rate.mean(), join=mm.join_rate.mean(), growth=mm.growth.mean(),
                   invol=mm.invol_rate.mean(), km90=km[90], km330=km[330])
    print(mm.to_string(index=False, float_format=lambda x: "%.4f" % x))
    print("AVG vol %.4f join %.4f growth %.4f invol %.4f | KM ret90 %.3f ret180 %.3f ret330 %.3f | early-cohort r90 %.3f r300 %.3f"
          % (summary["vol"], summary["join"], summary["growth"], summary["invol"], km[90], km[180], km[330], r90c, r300c))
    print("tenure:", " ".join("%d:%.3f" % (k, v) for k, v in ten[:14]), "| 12-24:", "%.3f" % np.mean([v for k, v in ten[12:24]]))
    inc = (ts(shc.o) <= WIN_START) & (shc.c.isna() | (shc.c > WIN_START))
    print("accounts", len(acc), "active on 2025-10-01:", shc[inc].account_id.nunique())
    if a.quick:
        return

    R = []  # report lines
    P = R.append
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    man = pd.read_csv(os.path.join(D, "_manifest.tsv"), sep="\t") if os.path.exists(os.path.join(D, "_manifest.tsv")) else None

    # ---------------- accounts
    check("accounts has exactly 50,000 rows", len(acc) == 50000, "%d rows" % len(acc))
    check("account_id unique", acc.account_id.is_unique)
    n_test = (acc.account_type != "CONSUMER").sum()
    check("test/internal accounts ~0.1%", 0.0005 <= n_test / len(acc) <= 0.002, "%d accounts (%.2f%%)" % (n_test, 100 * n_test / len(acc)))
    active_any = set(shc[(shc.o < WIN_END) & (shc.c.isna() | (shc.c > WIN_START))].account_id)
    cons = acc[acc.account_type == "CONSUMER"]
    check("every account held an active subscription in the window",
          set(acc.account_id) <= set(sh[(ts(sh.opened_ts) < WIN_END) & (ts(sh.closed_ts).isna() | (ts(sh.closed_ts) > WIN_START))].account_id),
          "%d of %d" % (len(set(acc.account_id) & set(sh[(ts(sh.opened_ts) < WIN_END) & (ts(sh.closed_ts).isna() | (ts(sh.closed_ts) > WIN_START))].account_id)), len(acc)))
    n_inc = shc[inc].account_id.nunique()

    # ---------------- subscription rules
    s = shc.sort_values(["account_id", "o"])
    prev_c = s.groupby("account_id").c.shift(1)
    overlap = ((prev_c.isna() & (s.groupby("account_id").cumcount() > 0)) | (prev_c > s.o)).sum()
    check("no overlapping subscription periods per account", overlap == 0, "%d overlaps" % overlap)
    check("at most one open period per account", (s[s.c.isna()].groupby("account_id").size() <= 1).all())
    bad_cancel = ((s.is_customer_initiated_cancel == 1) & s.cancel_requested_ts.isna()).sum()
    check("every voluntary close has a cancel request", bad_cancel == 0, "%d missing" % bad_cancel)
    cr = ts(s.cancel_requested_ts)
    check("cancel request falls inside its period", ((cr < s.o) | (s.c.notna() & (cr > s.c))).sum() == 0)
    check("price fields constant", (sh.plan_price_usd == 15.99).all() and (sh.is_free_trial_at_signup == 0).all())
    # voluntary closes on an anchor-day renewal boundary
    v = s[s.is_customer_initiated_cancel == 1]
    cd = v.c.dt.day
    od = v.o.dt.day
    last_dom = v.c.dt.days_in_month
    anch_ok = ((cd == od) | ((od > last_dom) & (cd == last_dom))).mean()
    check("voluntary closes happen at the anchor-day renewal time", anch_ok > 0.999, "%.4f on anchor day" % anch_ok)

    # ---------------- billing
    bh = rd(D, "billing_history")
    bh["t"] = ts(bh.transaction_ts)
    ch = bh[bh.transaction_type.isin(["CHARGE", "RETRY"])]
    check("every charge attempt is exactly $15.99 USD", ((ch.amount_usd == 15.99) & (ch.currency == "USD")).all())
    check("verification authorisations are $0.00", (bh[bh.transaction_type == "VERIFY"].amount_usd == 0).all())
    j = ch.merge(sh[["subscription_id", "opened_ts", "closed_ts", "billing_anchor_day"]], on="subscription_id", how="left")
    jo, jc = ts(j.opened_ts), ts(j.closed_ts)
    after_close = (jc.notna() & (j.t > jc + pd.Timedelta(days=0, seconds=60))).sum()
    before_open = (j.t < jo - pd.Timedelta(minutes=5)).sum()
    check("no charge after the period closed", after_close == 0, "%d" % after_close)
    check("no charge before the period opened", before_open == 0, "%d" % before_open)
    first = j[(j.transaction_type == "CHARGE") & (j.attempt_number == 1)]
    ren = first[ts(first.billing_period_start) > ts(first.opened_ts) + pd.Timedelta(days=1)]
    bps = pd.to_datetime(ren.billing_period_start)
    dim = bps.dt.days_in_month
    on_anchor = ((bps.dt.day == ren.billing_anchor_day) | ((ren.billing_anchor_day > dim) & (bps.dt.day == dim))).mean()
    check("renewal charges fall on the billing anchor day", on_anchor > 0.999, "%.4f" % on_anchor)
    win_ren = ren[(ren.t >= WIN_START) & (ren.t < WIN_END)]
    fail1 = (win_ren.pmt_status == "declined").mean()
    check("first-attempt renewal failure ~1-2%", 0.008 <= fail1 <= 0.022, "%.2f%%" % (100 * fail1))
    inv_rate = summary["invol"]
    paid = ch[ch.pmt_status == "approved"].groupby("subscription_id").size()
    # every period has an approved initial charge
    first_ok = j[j.pmt_status == "approved"].groupby("subscription_id").t.min()
    check("every subscription period has an approved charge", sh.subscription_id.isin(first_ok.index).all(),
          "%d without" % (~sh.subscription_id.isin(first_ok.index)).sum())
    pm = rd(D, "payment_methods")
    pm_first = pm.sort_values("added_ts").merge(sh[["initial_payment_method_id"]].rename(columns={"initial_payment_method_id": "payment_method_id"}), on="payment_method_id")
    mix = pm[pm.payment_method_id.isin(sh.initial_payment_method_id)].method_type.value_counts(normalize=True)

    # ---------------- referential integrity
    prof = rd(D, "profiles")
    dev = rd(D, "devices")
    cat = rd(D, "catalog")
    eps = rd(D, "episodes")
    ri = []
    A, Pf, Dv, Ti, Ep, Sb, Pm = (set(acc.account_id), set(prof.profile_id), set(dev.device_id), set(cat.title_id),
                                 set(eps.episode_id), set(sh.subscription_id), set(pm.payment_method_id))

    def fk(table, df, col, ref, refname, allow_null=True):
        x = df[col]
        if allow_null:
            x = x.dropna()
        miss = (~x.isin(ref)).sum()
        ri.append((table, col, refname, len(x), miss))

    for name, df in [("profiles", prof), ("devices", dev), ("payment_methods", pm), ("subscription_history", sh),
                     ("billing_history", bh)]:
        fk(name, df, "account_id", A, "accounts")
    fk("billing_history", bh, "subscription_id", Sb, "subscription_history")
    fk("billing_history", bh, "payment_method_id", Pm, "payment_methods")
    fk("subscription_history", sh, "initial_payment_method_id", Pm, "payment_methods")
    fk("episodes", eps, "title_id", Ti, "catalog")
    me = rd(D, "membership_events")
    fk("membership_events", me, "account_id", A, "accounts")
    fk("membership_events", me, "subscription_id", Sb, "subscription_history")
    fk("membership_events", me, "payment_method_id", Pm, "payment_methods")
    ce = rd(D, "consent_events")
    fk("consent_events", ce, "account_id", A, "accounts")

    t1 = time.time()
    va = rd(D, "viewing_activity", usecols=["view_id", "account_id", "profile_id", "device_id", "start_ts", "duration",
                                            "title_id", "episode_id", "supplemental_video_type", "subtitle_language"])
    va["t"] = ts(va.start_ts)
    dsec = va.duration.str.split(":", expand=True).astype(int)
    va["dur"] = dsec[0] * 3600 + dsec[1] * 60 + dsec[2]
    for col, ref, nm in [("account_id", A, "accounts"), ("profile_id", Pf, "profiles"), ("device_id", Dv, "devices"),
                         ("title_id", Ti, "catalog"), ("episode_id", Ep, "episodes")]:
        fk("viewing_activity", va, col, ref, nm)
    for tname, cols in [("search_history", ["account_id", "profile_id", "device_id"]), ("ratings", ["account_id", "profile_id", "title_id"]),
                        ("my_list", ["account_id", "profile_id", "title_id"]), ("login_events", ["account_id", "device_id"]),
                        ("support_contacts", ["account_id", "device_id"]), ("communications_log", ["account_id", "device_id"])]:
        df = rd(D, tname, usecols=cols)
        for c in cols:
            ref = {"account_id": A, "profile_id": Pf, "device_id": Dv, "title_id": Ti}[c]
            fk(tname, df, c, ref, c.replace("_id", "s") if c != "title_id" else "catalog")
    pq = rd(D, "playback_quality", usecols=["playback_id", "view_id", "account_id", "device_id", "client_ts", "exit_before_video_start", "startup_time_ms", "rebuffer_duration_ms"])
    fk("playback_quality", pq, "account_id", A, "accounts")
    fk("playback_quality", pq, "device_id", Dv, "devices")
    V = set(va.view_id)
    fk("playback_quality", pq, "view_id", V, "viewing_activity")
    pe = rd(D, "playback_events", usecols=["view_id", "event_seq", "event_type", "client_ts", "server_received_ts"])
    fk("playback_events", pe, "view_id", V, "viewing_activity")
    cs = rd(D, "clickstream", usecols=["event_id", "account_id", "profile_id", "device_id", "client_ts", "server_received_ts"])
    for c, ref in [("account_id", A), ("profile_id", Pf), ("device_id", Dv)]:
        fk("clickstream", cs, c, ref, c.replace("_id", "s"))

    # ---------------- viewing inside paid access
    per = sh[["account_id"]].assign(o=ts(sh.opened_ts), c=ts(sh.closed_ts))
    per["c"] = per.c.fillna(pd.Timestamp("2100-01-01", tz="UTC"))
    vv = va[va.supplemental_video_type.isna() | va.supplemental_video_type.notna()][["account_id", "t", "dur"]].sort_values("t")
    per = per.sort_values("o")
    m = pd.merge_asof(vv, per, left_on="t", right_on="o", by="account_id", direction="backward")
    outside = (m.o.isna() | (m.t >= m.c)).sum()
    ends_after = (m.c.notna() & (m.t + pd.to_timedelta(m.dur, unit="s") > m.c + pd.Timedelta(minutes=1))).sum()
    test_acc = set(acc.loc[acc.account_type != "CONSUMER", "account_id"])
    check("no viewing outside paid access", outside == 0, "%d rows outside" % outside)
    check("viewing durations stop at access end", ends_after == 0, "%d rows" % ends_after)
    check("viewing timestamps inside the data window", ((va.t >= WIN_START) & (va.t < WIN_END)).all())
    acc_c = acc.set_index("account_id").account_created_ts.pipe(ts)
    before = (va.t < va.account_id.map(acc_c)).sum()
    check("no viewing before account creation", before == 0, "%d" % before)
    # sessions before device first seen
    dfs = dev.set_index("device_id").first_seen_ts.pipe(ts)
    bdev = (va.t < va.device_id.map(dfs) - pd.Timedelta(minutes=1)).sum()
    check("no viewing on a device before it was first seen", bdev == 0, "%d" % bdev)
    pc = prof.set_index("profile_id").created_ts.pipe(ts)
    bprof = (va.t < va.profile_id.map(pc) - pd.Timedelta(minutes=1)).sum()
    check("no viewing on a profile before it was created", bprof == 0, "%d" % bprof)
    sub_col = va.subtitle_language.notna()
    print("viewing checks %.0fs" % (time.time() - t1), flush=True)

    # ---------------- short-retention tables
    pq_t = ts(pq.client_ts)
    pe_t = ts(pe.client_ts.str.slice(0, 19) + "Z")
    cs_t = ts(cs.client_ts)
    pe_s = ts(pe.server_received_ts.str.slice(0, 19) + "Z")
    ret = {}
    for nm, tt in [("playback_events", pe_t), ("playback_quality", pq_t), ("clickstream", cs_t)]:
        ret[nm] = (tt.min(), tt.max())
    check("90-day tables start on/after 2026-07-02 (allowing device clock skew)",
          all(v[0] >= SHORT_START - pd.Timedelta(hours=2) for v in ret.values()),
          "; ".join("%s %s .. %s" % (k, v[0], v[1]) for k, v in ret.items()))
    dup_pe = pe.duplicated().mean()
    dup_cs = cs.duplicated().mean()
    late_pe = ((pe_s - pe_t).dt.total_seconds() > 3600).mean()

    # ---------------- report
    P("# Jetflix dataset validation report\n")
    P("Generated by `validate_jetflix_data.py` on the files in `%s/`. Window: 2025-10-01 00:00 UTC to 2026-09-30 23:59 UTC. "
      "Rates use CONSUMER accounts only (QA/employee accounts excluded).\n" % D)
    P("## Summary of checks\n")
    P("| Check | Result | Detail |\n|---|---|---|")
    for nm, ok, det in checks:
        P("| %s | %s | %s |" % (nm, "PASS" if ok else "FAIL", det))
    P("")
    P("## Subscriber flow vs targets\n")
    P("Active base at the start of each month, joins (new and returning subscription periods), voluntary closes "
      "(access ended after a member cancel) and involuntary closes (grace period expired).\n")
    P("| Month | Active start | Joins | of which rejoins | Vol. churn | Invol. churn | Active end | Vol. churn rate | Join rate | Net growth |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in mm.iterrows():
        P("| %s | %d | %d | %d | %d | %d | %d | %.2f%% | %.2f%% | %.2f%% |" % (r.month, r.active_start, r.joins, r.of_which_rejoins, r.vol_churn,
                                                                     r.invol_churn, r.active_end, 100 * r.vol_churn_rate, 100 * r.join_rate, 100 * r.growth))
    P("")

    def tgt(name, val, target, lo, hi, fmtx="%.2f%%", mult=100):
        ok = lo <= val <= hi
        checks.append((name, ok, ""))
        return "| %s | %s | %s | %s | %s |" % (name, fmtx % (val * mult), target, (fmtx % (lo * mult)) + " - " + (fmtx % (hi * mult)), "PASS" if ok else "FAIL")

    P("| Metric | Value | Target | Accepted range (+/-10%) | Result |\n|---|---|---|---|---|")
    P(tgt("Voluntary churn, avg monthly", summary["vol"], "5%", 0.045, 0.055))
    P(tgt("Join rate, avg monthly", summary["join"], "7%", 0.063, 0.077))
    P(tgt("Net growth of active base, avg monthly", summary["growth"], "2%", 0.018, 0.022))
    P(tgt("Voluntary churners returning within 90 days (Kaplan-Meier)", km[90], "25%", 0.225, 0.275))
    P(tgt("Voluntary churners returning within 12 months (KM at 330 days, max follow-up)", km[330], "33%", 0.297, 0.363))
    P("")
    P("Involuntary churn averages %.2f%% of the active base per month. First-attempt renewal failures in the window: %.2f%% of renewals. "
      "Kaplan-Meier return curve for the %d voluntary closes in the window: 30d %.1f%%, 60d %.1f%%, 90d %.1f%%, 180d %.1f%%, 270d %.1f%%, 330d %.1f%%. "
      "Closes in Oct-Nov 2025 (10+ months of follow-up): %.1f%% returned within 90 days and %.1f%% within 300 days. "
      "%d accounts were active on 2025-10-01 (%.1f%% of the sample).\n"
      % (100 * inv_rate, 100 * fail1, n_vol, 100 * km[30], 100 * km[60], 100 * km[90], 100 * km[180], 100 * km[270], 100 * km[330],
         100 * r90c, 100 * r300c, n_inc, 100 * n_inc / len(acc)))
    P("Voluntary churn by month of tenure in the current period (closes per exposed subscriber-month):\n")
    P("| Tenure month | " + " | ".join(str(k + 1) for k, _ in ten[:12]) + " | 13-24 |")
    P("|---" * 14 + "|")
    P("| Churn rate | " + " | ".join("%.1f%%" % (100 * v) for _, v in ten[:12]) + " | %.1f%% |" % (100 * np.mean([v for k, v in ten[12:24]])))
    P("")
    P("Cycles 25-36: %.1f%%.\n" % (100 * np.mean([v for k, v in ten[24:36]])))
    P("")
    P("Payment method mix at subscription start: " + ", ".join("%s %.1f%%" % (k, 100 * v) for k, v in mix.items()) + ".\n")

    P("## Referential integrity\n")
    P("| Table | Column | References | Non-null rows | Missing parent |\n|---|---|---|---|---|")
    for t_, c_, r_, n_, m_ in ri:
        P("| %s | %s | %s | %d | %d |" % (t_, c_, r_, n_, m_))
    P("")
    P("Expected, documented orphans: `profile_id` values of hard-deleted (purged) profiles remain in viewing, search, ratings, my_list "
      "and clickstream; `playback_quality.view_id` is empty for attempts that failed before video start (no viewing row exists). "
      "Everything else resolves.\n")

    P("## Raw-data characteristics\n")
    P("- Exact duplicate rows: playback_events %.2f%%, clickstream %.2f%%." % (100 * dup_pe, 100 * dup_cs))
    P("- playback_events received by the server more than 1 hour after the client timestamp (offline downloads, flaky networks): %.2f%%." % (100 * late_pe))
    P("- `viewing_activity.subtitle_language` is populated on %.1f%% of rows; it exists only for app 9.0.0+ (released 2026-02-10) and the web player from that date." % (100 * sub_col.mean()))
    P("- `playback_quality.rebuffer_duration_ms = -1`: %.2f%% of rows (clients older than 8.11.0). `startup_time_ms = -1`: %.2f%% (failed before start)." %
      (100 * (pq.rebuffer_duration_ms == -1).mean(), 100 * (pq.startup_time_ms == -1).mean()))
    P("")
    P("## 90-day retention tables\n")
    P("| Table | First client timestamp | Last client timestamp |\n|---|---|---|")
    for k, v_ in ret.items():
        P("| %s | %s | %s |" % (k, v_[0], v_[1]))
    P("")
    P("## Row counts and file sizes\n")
    if man is not None:
        P("| Table | Rows | Uncompressed MB | gzip MB |\n|---|---|---|---|")
        for _, r in man.sort_values("table").iterrows():
            P("| %s | %d | %.1f | %.1f |" % (r.table, r.rows, r.uncompressed_bytes / 1e6, r.gzip_bytes / 1e6))
        P("| **Total** | %d | %.1f | %.1f |" % (man.rows.sum(), man.uncompressed_bytes.sum() / 1e6, man.gzip_bytes.sum() / 1e6))
    P("")
    # rewrite summary table with target checks included
    lines = R
    head = lines.index("| Check | Result | Detail |\n|---|---|---|")
    end = lines.index("", head)
    lines[head + 1:end] = ["| %s | %s | %s |" % (nm, "PASS" if ok else "FAIL", det) for nm, ok, det in checks]
    with open(a.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    n_fail = sum(1 for c in checks if not c[1])
    print("checks: %d, failed: %d (%.0fs)" % (len(checks), n_fail, time.time() - t_start))
    for c in checks:
        if not c[1]:
            print("  FAIL", c)


if __name__ == "__main__":
    main()
