#!/usr/bin/env python3
"""
SEALED - part of the ground truth. Do not open before finishing your own analysis.

Difficulty check: builds a reasonable engineered feature set at the start of every billing cycle
(right after a successful renewal or a new/returning signup), labels whether that cycle ends in a
voluntary close, trains LightGBM on early cycles and scores later cycles (time-based split).

    python GROUND_TRUTH_SEALED_difficulty_check.py --data data
"""
import argparse
import os

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

T0 = pd.Timestamp("2025-10-01T00:00:00Z")
WIN_END = pd.Timestamp("2026-10-01T00:00:00Z")


def rd(D, t, **kw):
    return pd.read_csv(os.path.join(D, t + ".csv.gz"), low_memory=False, **kw)


def sec(s):
    return ((pd.to_datetime(s, utc=True, format="ISO8601") - T0).dt.total_seconds()).astype("int64")


class Win:
    """Fast trailing-window sums per account using sorted keys and cumulative sums."""

    def __init__(self, acc_idx, t, val=None):
        key = acc_idx.astype(np.int64) * 10 ** 9 + (t.astype(np.int64) + 10 ** 8)
        o = np.argsort(key, kind="stable")
        self.key = key[o]
        v = np.ones(len(key)) if val is None else np.asarray(val, dtype=float)[o]
        self.cum = np.concatenate([[0.0], np.cumsum(v)])
        self.tt = t.astype(np.int64)[o]

    def sum(self, acc_idx, t_end, days):
        hi = np.searchsorted(self.key, acc_idx * 10 ** 9 + (t_end + 10 ** 8), "left")
        lo = np.searchsorted(self.key, acc_idx * 10 ** 9 + (t_end - days * 86400 + 10 ** 8), "left")
        return self.cum[hi] - self.cum[lo]

    def last(self, acc_idx, t_end):
        hi = np.searchsorted(self.key, acc_idx * 10 ** 9 + (t_end + 10 ** 8), "left")
        lo_acc = np.searchsorted(self.key, acc_idx * 10 ** 9, "left")
        ok = hi > lo_acc
        out = np.full(len(t_end), np.nan)
        out[ok] = (t_end[ok] - self.tt[hi[ok] - 1]) / 86400.0
        return out


def build(D):
    acc = rd(D, "accounts")
    acc = acc[acc.account_type == "CONSUMER"]
    aidx = {a: i for i, a in enumerate(acc.account_id)}
    sh = rd(D, "subscription_history")
    sh = sh[sh.account_id.isin(aidx)].copy()
    sh["o"] = sec(sh.opened_ts)
    sh["c"] = sec(sh.closed_ts.fillna("2100-01-01T00:00:00Z"))
    bh = rd(D, "billing_history", usecols=["account_id", "subscription_id", "transaction_ts", "transaction_type", "pmt_status",
                                           "billing_period_start", "billing_period_end", "attempt_number"])
    bh = bh[bh.account_id.isin(aidx)]
    bh["t"] = sec(bh.transaction_ts)
    ok = bh[(bh.pmt_status == "approved") & bh.transaction_type.isin(["CHARGE", "RETRY"])]
    cyc = ok.merge(sh[["subscription_id", "o", "c", "is_customer_initiated_cancel", "period_seq", "signup_type"]], on="subscription_id")
    cyc["pend"] = sec(cyc.billing_period_end + "T00:00:00Z")
    cyc = cyc[(cyc.t >= 30 * 86400) & (cyc.pend < 362 * 86400)]
    # label: the period closes voluntarily at the end of this paid cycle
    cyc["y"] = ((cyc.is_customer_initiated_cancel == 1) & (cyc.c < cyc.pend + 2 * 86400) & (cyc.c > cyc.t)).astype(int)
    cyc["ai"] = cyc.account_id.map(aidx).astype(np.int64)
    cyc["tenure_cycles"] = ((cyc.t - cyc.o) / (30.44 * 86400)).round()
    cyc["prior_periods"] = cyc.period_seq - 1
    fails = bh[(bh.pmt_status == "declined")]
    fw = Win(fails.account_id.map(aidx).values, fails.t.values)
    A = cyc.ai.values
    T = cyc.t.values
    F = pd.DataFrame({"tenure_cycles": cyc.tenure_cycles.values, "prior_periods": cyc.prior_periods.values,
                      "month": pd.to_datetime(T * 1e9 + T0.value).month})
    F["fail_60d"] = fw.sum(A, T, 60)
    va = rd(D, "viewing_activity", usecols=["account_id", "profile_id", "start_ts", "duration", "title_id", "episode_id", "supplemental_video_type"])
    va = va[va.account_id.isin(aidx) & va.supplemental_video_type.isna()]
    d = va.duration.str.split(":", expand=True).astype(int)
    va["s"] = d[0] * 3600 + d[1] * 60 + d[2]
    va["t"] = sec(va.start_ts)
    vi = va.account_id.map(aidx).values
    wv = Win(vi, va.t.values, va.s.values / 60.0)
    wc = Win(vi, va.t.values)
    for k in (7, 14, 30, 60):
        F["min_%dd" % k] = wv.sum(A, T, k)
    F["views_30d"] = wc.sum(A, T, 30)
    F["trend_14_60"] = (F.min_14d / 14 + 1) / (F.min_60d / 60 + 1)
    F["days_since_view"] = wv.last(A, T)
    # finished a series in the last 14 days: viewed the final episode
    eps = rd(D, "episodes")
    last_ep = eps.sort_values(["title_id", "season_number", "episode_number"]).groupby("title_id").episode_id.last()
    va["is_final"] = va.episode_id.isin(set(last_ep.values)).astype(float)
    wf = Win(vi, va.t.values, va.is_final.values)
    F["finished_series_14d"] = wf.sum(A, T, 14)
    # distinct-ish breadth: new titles started (first view of a title by a profile) in 30d
    va = va.sort_values("t")
    first = ~va.duplicated(["profile_id", "title_id"])
    wn = Win(vi, va.t.values, first.values.astype(float))
    F["new_titles_30d"] = wn.sum(A, T, 30)
    ml = rd(D, "my_list")
    ml = ml[ml.account_id.isin(aidx)]
    wm = Win(ml.account_id.map(aidx).values, sec(ml.added_ts).values)
    F["mylist_adds_30d"] = wm.sum(A, T, 30)
    sr = rd(D, "search_history")
    sr = sr[sr.account_id.isin(aidx)]
    ws = Win(sr.account_id.map(aidx).values, sec(sr.search_ts).values, sr.displayed_title_id.isna().values.astype(float))
    F["searches_no_result_30d"] = ws.sum(A, T, 30)
    sc = rd(D, "support_contacts")
    sc = sc[sc.account_id.isin(aidx)]
    wsc = Win(sc.account_id.map(aidx).values, sec(sc.contact_ts).values)
    wsu = Win(sc.account_id.map(aidx).values, sec(sc.contact_ts).values, sc.resolution.isin(["UNRESOLVED", "CUSTOMER_ABANDONED", "ESCALATED"]).values.astype(float))
    F["support_30d"] = wsc.sum(A, T, 30)
    F["support_unres_30d"] = wsu.sum(A, T, 30)
    cm = rd(D, "communications_log", usecols=["account_id", "channel", "sent_ts", "opened_ts", "clicked_ts"])
    cm = cm[cm.account_id.isin(aidx) & (cm.channel == "EMAIL")]
    wo = Win(cm.account_id.map(aidx).values, sec(cm.sent_ts).values, cm.clicked_ts.notna().values.astype(float))
    F["email_clicks_60d"] = wo.sum(A, T, 60)
    dv = rd(D, "devices")
    dv = dv[dv.account_id.isin(aidx)]
    wd = Win(dv.account_id.map(aidx).values, sec(dv.first_seen_ts).values)
    F["devices_registered"] = wd.sum(A, T, 2000)
    pr = rd(D, "profiles")
    pr = pr[pr.account_id.isin(aidx)]
    wp = Win(pr.account_id.map(aidx).values, sec(pr.created_ts).values)
    F["profiles"] = wp.sum(A, T, 2000)
    pm = rd(D, "payment_methods")
    first_pm = sh.merge(pm[["payment_method_id", "method_type"]], left_on="initial_payment_method_id", right_on="payment_method_id")
    mt = first_pm.set_index("subscription_id").method_type
    F["pay_type"] = cyc.subscription_id.map(mt).astype("category").cat.codes.values
    a2 = acc.set_index("account_id")
    F["channel"] = cyc.account_id.map(a2.signup_channel).astype("category").cat.codes.values
    F["email_consent"] = cyc.account_id.map(a2.email_consent_marketing).values
    F["acct_age_days"] = (T - cyc.account_id.map(sec(a2.account_created_ts)).values) / 86400
    # viewing quality of engagement: short (abandoned) views and views per viewing day
    wab = Win(vi, va.t.values, (va.s < 300).values.astype(float))
    F["abandon_share_30d"] = wab.sum(A, T, 30) / (F.views_30d + 1)
    va["day"] = va.t // 86400
    vd = va.drop_duplicates(["account_id", "day"])
    wdd = Win(vd.account_id.map(aidx).values, vd.t.values)
    F["view_days_30d"] = wdd.sum(A, T, 30)
    F["views_per_view_day_30d"] = F.views_30d / (F.view_days_30d + 1)
    F["view_days_7d"] = wdd.sum(A, T, 7)
    # signup / rejoin shortly after a promo tier A release
    cat = rd(D, "catalog")
    rel = np.sort(sec(cat[cat.promo_tier == "A"].available_from + "T00:00:00Z").values)
    j = np.searchsorted(rel, cyc.o.values, "right") - 1
    F["days_open_after_tier_a"] = np.where(j >= 0, (cyc.o.values - rel[np.clip(j, 0, None)]) / 86400, 999)
    me = rd(D, "membership_events", usecols=["account_id", "event_ts", "event_type"])
    me = me[me.account_id.isin(aidx)]
    for ev, nm in [("CANCEL_REVERSED", "reversals_ever"), ("CANCEL_REQUESTED", "cancel_requests_ever")]:
        x = me[me.event_type == ev]
        w_ = Win(x.account_id.map(aidx).values, sec(x.event_ts).values)
        F[nm] = w_.sum(A, T, 3000)
    cm2 = cm
    wop = Win(cm2.account_id.map(aidx).values, sec(cm2.sent_ts).values, cm2.opened_ts.notna().values.astype(float))
    wse = Win(cm2.account_id.map(aidx).values, sec(cm2.sent_ts).values)
    F["email_open_rate_60d"] = wop.sum(A, T, 60) / (wse.sum(A, T, 60) + 1)
    lg = rd(D, "login_events", usecols=["account_id", "event_ts", "geo_state"])
    lg = lg[lg.account_id.isin(aidx)]
    wl = Win(lg.account_id.map(aidx).values, sec(lg.event_ts).values)
    F["logins_60d"] = wl.sum(A, T, 60)
    F["kids_profiles"] = cyc.account_id.map(pr[pr.is_kids == 1].groupby("account_id").size()).fillna(0).values
    return cyc, F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    a = ap.parse_args()
    import lightgbm as lgb
    cyc, F = build(a.data)
    t = cyc.t.values
    tr = t < day(2026, 5, 15)
    te = t >= day(2026, 6, 15)
    y = cyc.y.values
    print("cycles", len(F), "train", tr.sum(), "test", te.sum(), "base rate train %.3f test %.3f" % (y[tr].mean(), y[te].mean()))
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=100, subsample=0.8,
                           subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    m.fit(F[tr], y[tr])
    p = m.predict_proba(F[te])[:, 1]
    auc = roc_auc_score(y[te], p)
    print("LightGBM AUC (time split): %.3f" % auc)
    rule = (F.days_since_view.fillna(999) >= 14).values
    print("rule 'no viewing for 14+ days': flags %.1f%% of test cycles, precision %.3f, recall %.3f, AUC %.3f" % (
        100 * rule[te].mean(), y[te][rule[te]].mean(), rule[te][y[te] == 1].mean(), roc_auc_score(y[te], rule[te])))
    for c in F.columns:
        x = F[c].fillna(-1).values
        try:
            au = roc_auc_score(y[te], x[te])
        except ValueError:
            continue
        print("  single-feature AUC %-24s %.3f" % (c, max(au, 1 - au)))
    imp = sorted(zip(m.feature_importances_, F.columns), reverse=True)
    print("importance:", ", ".join("%s=%d" % (c, v) for v, c in imp[:12]))


def day(y, mo, d):
    return int((pd.Timestamp(year=y, month=mo, day=d, tz="UTC") - T0).total_seconds())


if __name__ == "__main__" and not os.environ.get("WARN_SHARE"):
    main()


def warning_share(D, verbose=True):
    """Share of voluntary cancels with no visible warning beforehand.

    A 'warning' is any of these observable signals, measured at the moment of the cancel request:
      drop    - watch time in the last 28 days below DROP x the user's own average of the 12 weeks before,
                for users whose baseline is at least 2 hours per 28 days;
      silent  - no viewing for 14+ days by someone who watched on 6+ days in the prior 12 weeks;
      dormant - under 30 minutes of viewing per 28 days over the prior 12 weeks (pays but barely uses it);
      event   - a support contact in the last 30 days, a declined payment in the last 60 days,
                or a series finale watched in the last 14 days.
    The same flags are computed for non-churners (renewal moments not followed by a cancel within 35 days)
    to show how selective each signal is.
    """
    acc = rd(D, "accounts")
    cons = set(acc[acc.account_type == "CONSUMER"].account_id)
    aidx = {a: i for i, a in enumerate(acc.account_id)}
    sh = rd(D, "subscription_history")
    vol = sh[(sh.is_customer_initiated_cancel == 1) & sh.account_id.isin(cons)].copy()
    vol["t"] = sec(vol.cancel_requested_ts)
    vol["o"] = sec(vol.opened_ts)
    vol = vol[(vol.t >= 120 * 86400) & (vol.t - vol.o > 60 * 86400)]
    bh = rd(D, "billing_history", usecols=["account_id", "subscription_id", "transaction_ts", "transaction_type", "pmt_status"])
    bh["t"] = sec(bh.transaction_ts)
    ren = bh[(bh.transaction_type == "CHARGE") & (bh.pmt_status == "approved") & (bh.t >= 120 * 86400) & (bh.t < 330 * 86400)
             & bh.account_id.isin(cons)]
    canc = sh.dropna(subset=["cancel_requested_ts"]).copy()
    canc["ct"] = sec(canc.cancel_requested_ts)
    me = rd(D, "membership_events", usecols=["account_id", "event_ts", "event_type"])
    req = me[me.event_type == "CANCEL_REQUESTED"]
    wr = Win(req.account_id.map(aidx).values, sec(req.event_ts).values)
    RA = ren.account_id.map(aidx).values.astype(np.int64)
    RT = ren.t.values
    stay = (wr.sum(RA, RT + 35 * 86400, 35) == 0)
    ren = ren[stay].sample(min(60000, stay.sum()), random_state=1)
    pts = pd.concat([pd.DataFrame({"a": vol.account_id.map(aidx).values, "t": vol.t.values, "churn": 1}),
                     pd.DataFrame({"a": ren.account_id.map(aidx).values, "t": ren.t.values, "churn": 0})])
    A = pts.a.values.astype(np.int64)
    T = pts.t.values
    va = rd(D, "viewing_activity", usecols=["account_id", "start_ts", "duration", "episode_id", "supplemental_video_type"])
    va = va[va.supplemental_video_type.isna()]
    d = va.duration.str.split(":", expand=True).astype(int)
    va["s"] = d[0] * 3600 + d[1] * 60 + d[2]
    vi = va.account_id.map(aidx).values
    vt = sec(va.start_ts).values
    wv = Win(vi, vt, va.s.values / 60.0)
    recent = wv.sum(A, T, 28)
    base = wv.sum(A, T - 28 * 86400, 84) / 3.0
    va["day"] = vt // 86400
    vd = va.assign(t=vt).drop_duplicates(["account_id", "day"])
    wvd = Win(vd.account_id.map(aidx).values, vd.t.values)
    prior_days = wvd.sum(A, T - 28 * 86400, 84)
    last = np.nan_to_num(wv.last(A, T), nan=999)
    sc = rd(D, "support_contacts")
    wsu = Win(sc.account_id.map(aidx).values, sec(sc.contact_ts).values)
    f = bh[bh.pmt_status == "declined"]
    wf = Win(f.account_id.map(aidx).values, f.t.values)
    eps = rd(D, "episodes")
    last_ep = set(eps.sort_values(["title_id", "season_number", "episode_number"]).groupby("title_id").episode_id.last())
    wfin = Win(vi, vt, va.episode_id.isin(last_ep).values.astype(float))
    event = (wsu.sum(A, T, 30) > 0) | (wf.sum(A, T, 60) > 0) | (wfin.sum(A, T, 14) > 0)
    dormant = base < 30
    silent = (last >= 14) & (prior_days >= 6)
    ch = pts.churn.values == 1
    res = {}
    for drop in (0.6, 0.5, 0.4, 0.3):
        dec = (base >= 120) & (recent < drop * base)
        warn = dec | silent | dormant | event
        res[drop] = (warn[~ch].mean(), (~warn[ch]).mean(), dec, warn)
    drop = 0.5  # headline: a 50% drop vs the user's own baseline
    fp, nowarn, dec, warn = res[drop]
    if verbose:
        print("voluntary cancels analysed: %d; non-churn reference points: %d" % (ch.sum(), (~ch).sum()))
        for k, v in sorted(res.items(), reverse=True):
            print("  drop<%.0f%% of baseline: non-churners flagged %.1f%%, churners with NO visible warning %.1f%%" % (100 * k, 100 * v[0], 100 * v[1]))
        print("  headline (drop < %.0f%%) -> NO VISIBLE WARNING among churners: %.1f%% (non-churners flagged %.1f%%)" % (100 * drop, 100 * nowarn, 100 * fp))
        for nm, x in [("drop", dec), ("silent", silent), ("dormant", dormant), ("event", event)]:
            print("    %-8s churners %.1f%%  non-churners %.1f%%" % (nm, 100 * x[ch].mean(), 100 * x[~ch].mean()))
        heavy = base >= np.percentile(base[~ch], 75)
        print("  heavy viewers (top quartile of non-churner usage) among churners: %.1f%%; heavy churners with no warning: %.1f%% of cancels"
              % (100 * heavy[ch].mean(), 100 * (heavy & ~warn)[ch].mean()))
    return nowarn, fp

if __name__ == "__main__" and os.environ.get("WARN_SHARE"):
    import sys
    warning_share(sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "data")
