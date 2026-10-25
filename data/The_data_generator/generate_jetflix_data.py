#!/usr/bin/env python3
"""
generate_jetflix_data.py - reproducible generator for the raw Jetflix (US) operational dataset.

Jetflix is a fictional, Netflix-like US streaming service (one ad-free Standard plan, $15.99/month).
This script simulates 50,000 accounts that held an active subscription at some point between
2025-10-01 and 2026-09-30 (UTC) and writes one gzipped CSV per operational table to --out.

Everything is driven by a fixed seed. Each account gets its own RNG stream derived from
(seed, account index), so a run split into batches or worker processes produces the same
rows as a single-process run.

Usage
    python generate_jetflix_data.py                       # full run, all cores, ./data
    python generate_jetflix_data.py --workers 4 --out data
    python generate_jetflix_data.py --sample-every 10     # every 10th account (quick check)

Requires numpy (setup only); the simulation itself uses the standard library.

NOTE: this file contains the hidden behaviour model. For a blind analysis, treat it like
GROUND_TRUTH_SEALED.md and do not read past the table definitions.
"""
import argparse
import bisect
import calendar
import gzip
import hashlib
import math
import os
import random
import shutil
import sys
import time
from datetime import date, datetime, timedelta, timezone
from multiprocessing import Pool

import numpy as np

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------
CFG = {
    "seed": 20261001,
    "n_accounts": 50_000,
    "n_incumbent": 27_900,          # active on 2025-10-01
    "n_lapsed_returner": 2_200,     # former subscribers (lapsed before window) who rejoin in window
    "n_test": 50,                   # internal / QA / employee accounts (~0.1%)
    "price": 15.99,
    "short_retention_days": 90,     # playback_events, playback_quality, clickstream
    # churn engine
    "h0": 0.000300,                 # base daily cancel hazard
    "exo": 0.00011,                 # base daily exogenous cancel hazard (x usage level^0.6)
    "ret90": 0.225,                 # base P(return within 90 days | voluntary churn)
    "ret_late": 0.075,              # base P(return in days 91-365 | voluntary churn)
    "rev_base": 0.0052,             # daily P(reverse a pending cancel)
    # payments
    "fail_card": 0.0125, "fail_store": 0.0090, "fail_paypal": 0.0115,
    # engagement
    "sit_scale": 0.61,
    "a_mu": 0.7, "a_dev": 1.4,     # engagement ~ exp(a_mu*mu + a_dev*dev)
    "b_mu": 1.2, "b_dev": 2.15,    # cancel hazard ~ exp(-b_mu*mu - b_dev*dev)
    "decline_onset": 1 / 230.0, "decline_recover": 1 / 85.0, "rho": 0.975,
    "b_use": 0.9,                  # cancel hazard ~ (own usage level / type median)^-b_use (not for passive payers)
}

UTC = timezone.utc
T0 = datetime(2025, 10, 1, tzinfo=UTC)
T0D = T0.date()
WIN_DAYS = 365
WIN_END = WIN_DAYS * 86400                       # exclusive, seconds relative to T0
SHORT_START = (WIN_DAYS - CFG["short_retention_days"]) * 86400
LAUNCH_DAY = (date(2023, 10, 1) - T0D).days      # -731
D_MIN = LAUNCH_DAY - 40
D_MAX = WIN_DAYS + 420
EXTRACTED_AT = "2026-10-01T03:12:44Z"

# --------------------------------------------------------------------------------------
# Calendar helpers (all times are integer seconds relative to T0 = 2025-10-01T00:00Z)
# --------------------------------------------------------------------------------------
_DATES = [T0D + timedelta(days=d) for d in range(D_MIN, D_MAX)]
DAYSTR = [x.isoformat() for x in _DATES]
DOW = [x.weekday() for x in _DATES]
MON = [x.month for x in _DATES]
DOM = [x.day for x in _DATES]
YR = [x.year for x in _DATES]


def di(d):
    return d - D_MIN


def fmt(ts):
    ts = int(ts)
    d, r = divmod(ts, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return "%sT%02d:%02d:%02dZ" % (DAYSTR[d - D_MIN], h, m, s)


def fmt_ms(ms):
    ms = int(ms)
    s, rem = divmod(ms, 1000)
    return fmt(s)[:-1] + ".%03dZ" % rem


def fmt_date(ts):
    return DAYSTR[int(ts // 86400) - D_MIN]


def hms(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return "%02d:%02d:%02d" % (h, m, s)


def day_of(d_date):
    return (d_date - T0D).days


def add_months(open_s, k, anchor):
    """Renewal timestamp: k months after open_s, on the anchor day (clamped), same time of day."""
    d = open_s // 86400
    tod = open_s - d * 86400
    y, m = YR[d - D_MIN], MON[d - D_MIN]
    m2 = m - 1 + k
    y2 = y + m2 // 12
    m2 = m2 % 12 + 1
    dd = min(anchor, calendar.monthrange(y2, m2)[1])
    return (date(y2, m2, dd) - T0D).days * 86400 + tod


# US daylight saving periods (day index ranges, local DST active)
_DST = [(date(2023, 3, 12), date(2023, 11, 5)), (date(2024, 3, 10), date(2024, 11, 3)),
        (date(2025, 3, 9), date(2025, 11, 2)), (date(2026, 3, 8), date(2026, 11, 1)),
        (date(2027, 3, 14), date(2027, 11, 7))]
DST = [False] * (D_MAX - D_MIN)
for a, b in _DST:
    for d in range(day_of(a), day_of(b)):
        if D_MIN <= d < D_MAX:
            DST[di(d)] = True

TZ_STD = {"America/New_York": -5, "America/Chicago": -6, "America/Denver": -7, "America/Phoenix": -7,
          "America/Los_Angeles": -8, "America/Anchorage": -9, "Pacific/Honolulu": -10}
TZ_NODST = {"America/Phoenix", "Pacific/Honolulu"}


def utc_off(tz, d):
    o = TZ_STD[tz]
    if tz not in TZ_NODST and DST[di(d)]:
        o += 1
    return o


HOLIDAYS = {
    date(2025, 10, 31): "halloween", date(2025, 11, 27): "thanksgiving", date(2025, 11, 28): "black_friday",
    date(2025, 12, 24): "xmas_eve", date(2025, 12, 25): "christmas", date(2025, 12, 31): "nye",
    date(2026, 1, 1): "new_year", date(2026, 1, 19): "mlk", date(2026, 2, 8): "super_bowl",
    date(2026, 2, 16): "presidents", date(2026, 5, 25): "memorial", date(2026, 7, 4): "july4",
    date(2026, 9, 7): "labor",
}
HOL = {day_of(k): v for k, v in HOLIDAYS.items()}
HOL_VIEW = {"thanksgiving": 1.25, "black_friday": 1.2, "xmas_eve": 1.05, "christmas": 1.3, "nye": 0.8,
            "new_year": 1.35, "super_bowl": 0.72, "july4": 0.8, "memorial": 1.08, "labor": 1.08,
            "mlk": 1.08, "presidents": 1.08, "halloween": 0.9}
DOW_VIEW = [0.95, 0.93, 0.95, 0.98, 1.08, 1.18, 1.15]
MON_VIEW = {1: 1.15, 2: 1.08, 3: 1.0, 4: 0.95, 5: 0.92, 6: 0.88, 7: 0.88, 8: 0.92, 9: 0.97, 10: 1.0, 11: 1.03,
            12: 1.10}
MON_CHURN = {1: 1.28, 2: 1.05, 3: 1.0, 4: 0.97, 5: 1.02, 6: 1.0, 7: 0.95, 8: 1.08, 9: 1.03, 10: 1.0, 11: 0.92,
             12: 0.86}

HOURS = {
    "adult_wd": [2, 1, .5, .3, .2, .3, .6, 1, 1, 1, 1.1, 1.3, 1.8, 1.5, 1.4, 1.6, 2, 2.6, 3.6, 5, 6.5, 6.8, 5, 3.2],
    "adult_we": [3, 2, 1, .5, .3, .3, .5, 1, 1.6, 2.2, 2.6, 2.8, 3, 3, 3, 3.1, 3.3, 3.6, 4.2, 5.2, 6, 6, 4.8, 3.6],
    "kids_wd": [0, 0, 0, 0, 0, .1, .8, 2.2, 1.2, .5, .6, .7, .8, .7, .8, 2.2, 3.2, 3.4, 3.2, 2.6, 1.4, .4, .1, 0],
    "kids_we": [0, 0, 0, 0, 0, .2, 1.5, 3.5, 4, 3.6, 3, 2.6, 2.2, 2, 2.2, 2.4, 2.6, 2.8, 2.8, 2.2, 1.2, .4, .1, 0],
    "mobile": [3, 2, 1, .4, .3, .5, 1.2, 2.6, 2.4, 1.4, 1.2, 1.6, 3, 2, 1.4, 1.6, 2.2, 2.8, 2.6, 2.8, 3.4, 4.2, 4.6, 4],
    "action": [1, .5, .3, .2, .2, .3, .8, 1.5, 2, 2.2, 2.3, 2.4, 2.6, 2.4, 2.3, 2.4, 2.5, 2.8, 3.2, 3.8, 4.2, 4, 3.2, 2],
}
HOURS_CUM = {}
for _k, _w in HOURS.items():
    _c, _s = [], 0.0
    for _x in _w:
        _s += _x
        _c.append(_s)
    HOURS_CUM[_k] = (_c, _s)


def pick_hour(R, key, shift=0):
    c, s = HOURS_CUM[key]
    h = bisect.bisect_right(c, R.random() * s)
    return (min(h, 23) + shift) % 24


def poisson(R, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(R.gauss(lam, math.sqrt(lam)) + 0.5))
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= R.random()
        if p <= L:
            return k
        k += 1


def wchoice(R, items, cum):
    return items[bisect.bisect_right(cum, R.random() * cum[-1])]


def cumsum(ws):
    out, s = [], 0.0
    for w in ws:
        s += w
        out.append(s)
    return out


def hhash(*parts):
    return hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=6).hexdigest()


# --------------------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------------------
# state, population (millions, approx 2024), default tz, zip3 ranges, rural-broadband flag
STATES = [
    ("CA", 39.4, "America/Los_Angeles", [(900, 961)], 0), ("TX", 31.3, "America/Chicago", [(750, 799), (885, 885)], 0),
    ("FL", 23.4, "America/New_York", [(320, 349)], 0), ("NY", 19.9, "America/New_York", [(100, 149)], 0),
    ("PA", 13.1, "America/New_York", [(150, 196)], 0), ("IL", 12.7, "America/Chicago", [(600, 629)], 0),
    ("OH", 11.9, "America/New_York", [(430, 458)], 0), ("GA", 11.2, "America/New_York", [(300, 319), (398, 399)], 0),
    ("NC", 11.0, "America/New_York", [(270, 289)], 0), ("MI", 10.1, "America/New_York", [(480, 499)], 0),
    ("NJ", 9.5, "America/New_York", [(70, 89)], 0), ("VA", 8.8, "America/New_York", [(220, 246)], 0),
    ("WA", 8.0, "America/Los_Angeles", [(980, 994)], 0), ("AZ", 7.6, "America/Phoenix", [(850, 865)], 0),
    ("TN", 7.2, "America/Chicago", [(370, 385)], 0), ("MA", 7.1, "America/New_York", [(10, 27)], 0),
    ("IN", 6.9, "America/New_York", [(460, 479)], 0), ("MO", 6.3, "America/Chicago", [(630, 658)], 0),
    ("MD", 6.3, "America/New_York", [(206, 219)], 0), ("WI", 6.0, "America/Chicago", [(530, 549)], 0),
    ("CO", 6.0, "America/Denver", [(800, 816)], 0), ("MN", 5.8, "America/Chicago", [(550, 567)], 0),
    ("SC", 5.5, "America/New_York", [(290, 299)], 0), ("AL", 5.2, "America/Chicago", [(350, 369)], 1),
    ("LA", 4.6, "America/Chicago", [(700, 714)], 0), ("KY", 4.6, "America/New_York", [(400, 427)], 1),
    ("OR", 4.3, "America/Los_Angeles", [(970, 979)], 0), ("OK", 4.1, "America/Chicago", [(730, 749)], 1),
    ("CT", 3.7, "America/New_York", [(60, 69)], 0), ("UT", 3.5, "America/Denver", [(840, 847)], 0),
    ("IA", 3.2, "America/Chicago", [(500, 528)], 1), ("NV", 3.3, "America/Los_Angeles", [(889, 898)], 0),
    ("AR", 3.1, "America/Chicago", [(716, 729)], 1), ("KS", 3.0, "America/Chicago", [(660, 679)], 1),
    ("MS", 2.9, "America/Chicago", [(386, 397)], 1), ("NM", 2.1, "America/Denver", [(870, 884)], 1),
    ("NE", 2.0, "America/Chicago", [(680, 693)], 1), ("ID", 2.0, "America/Denver", [(832, 838)], 1),
    ("WV", 1.8, "America/New_York", [(247, 268)], 1), ("HI", 1.4, "Pacific/Honolulu", [(967, 968)], 0),
    ("NH", 1.4, "America/New_York", [(30, 38)], 0), ("ME", 1.4, "America/New_York", [(39, 49)], 1),
    ("MT", 1.1, "America/Denver", [(590, 599)], 1), ("RI", 1.1, "America/New_York", [(28, 29)], 0),
    ("DE", 1.0, "America/New_York", [(197, 199)], 0), ("SD", 0.9, "America/Chicago", [(570, 577)], 1),
    ("ND", 0.8, "America/Chicago", [(580, 588)], 1), ("AK", 0.7, "America/Anchorage", [(995, 999)], 1),
    ("DC", 0.7, "America/New_York", [(200, 205)], 0), ("VT", 0.65, "America/New_York", [(50, 59)], 1),
    ("WY", 0.59, "America/Denver", [(820, 831)], 1),
]
# ZIP3 time-zone exceptions (split states)
TZ_ZIP3 = {798: "America/Denver", 799: "America/Denver", 324: "America/Chicago", 325: "America/Chicago",
           373: "America/New_York", 374: "America/New_York", 376: "America/New_York", 377: "America/New_York",
           378: "America/New_York", 379: "America/New_York", 463: "America/Chicago", 464: "America/Chicago",
           498: "America/Chicago", 499: "America/Chicago", 838: "America/Los_Angeles",
           979: "America/Denver", 690: "America/Denver", 693: "America/Denver", 677: "America/Denver"}
ISPS = ["Comcast Xfinity", "Charter Spectrum", "AT&T", "Verizon Fios", "Cox", "T-Mobile Home Internet",
        "Frontier", "Optimum", "CenturyLink", "Windstream", "Mediacom", "Starlink"]
ISP_W = [24, 22, 12, 7, 5, 6, 4, 4, 5, 2, 2, 1.5]
MOBILE_CARRIERS = ["Verizon Wireless", "T-Mobile USA", "AT&T Mobility"]
CDN_POPS = {"America/New_York": ["iad", "ewr", "atl", "mia", "bos"], "America/Chicago": ["ord", "dfw", "msp", "iah"],
            "America/Denver": ["den", "slc"], "America/Phoenix": ["phx"], "America/Los_Angeles": ["lax", "sjc", "sea"],
            "America/Anchorage": ["sea"], "Pacific/Honolulu": ["lax", "hnl"]}

# --------------------------------------------------------------------------------------
# Devices and app versions
# --------------------------------------------------------------------------------------
# category, platform, manufacturer, raw device string variants, model_code, share, quality (1 = good,
# higher = worse), max kbps, push-capable, max app version index (None = no cap), os versions
DEVICE_MODELS = [
    ("TV", "tizen", "Samsung", ["Samsung 2022 Crystal UHD TV Smart TV", "SAMSUNG 2022 Crystal UHD TV"], "UN55CU7000", 6.0, 1.0, 5800, 0, None, ["Tizen 6.5", "Tizen 7.0"]),
    ("TV", "tizen", "Samsung", ["Samsung 2019 UHD TV (Kant-S) Smart TV", "Samsung 2019 UHD TV Kant-S"], "UN55RU7100", 4.0, 1.15, 5200, 0, None, ["Tizen 5.0"]),
    ("TV", "tizen", "Samsung", ["Samsung 2017 UHD TV (Kant-M) Smart TV", "samsung 2017 uhd tv"], "UN50MU6300", 2.2, 1.6, 4300, 0, 3, ["Tizen 3.0"]),
    ("TV", "webos", "LG", ["LG 2023 OLED evo webOS 23 TV", "LG webOS 23 OLED"], "OLED55C3PUA", 3.0, 0.9, 5800, 0, None, ["webOS 23"]),
    ("TV", "webos", "LG", ["LG 2020 webOS 5.0 TV", "LG 2020 webOS TV"], "55UN7300PUF", 3.0, 1.1, 5200, 0, None, ["webOS 5.0"]),
    ("TV", "webos", "LG", ["LG 2018 webOS 4.0 TV", "LG webOS 4.0 TV (2018)"], "55UK6300PUE", 1.8, 1.45, 4300, 0, 4, ["webOS 4.0"]),
    ("TV", "vizio", "VIZIO", ["VIZIO 2021 SmartCast TV", "Vizio SmartCast 2021"], "V555-J01", 3.2, 1.2, 5200, 0, None, ["SmartCast 4.0"]),
    ("TV", "vidaa", "Hisense", ["Hisense VIDAA U5 TV", "HISENSE VIDAA"], "55A6H", 1.5, 1.3, 5200, 0, None, ["VIDAA U5"]),
    ("STREAMING_STICK", "roku", "Roku", ["Roku Express 3930X Streaming Stick", "Roku 3930X", "ROKU EXPRESS (3930X)"], "3930X", 6.0, 1.2, 4300, 0, None, ["Roku OS 12.5", "Roku OS 13.0"]),
    ("STREAMING_STICK", "roku", "Roku", ["Roku Streaming Stick 4K 3820X", "Roku 3820X"], "3820X", 4.5, 1.0, 5800, 0, None, ["Roku OS 13.0", "Roku OS 14.0"]),
    ("STREAMING_STICK", "roku", "Roku", ["Roku Ultra 4800X", "Roku Ultra (4800X)"], "4800X", 2.5, 0.9, 5800, 0, None, ["Roku OS 14.0"]),
    ("TV", "roku", "TCL", ["Roku TV (TCL 55S455)", "TCL Roku TV 55S455"], "55S455", 4.0, 1.15, 5200, 0, None, ["Roku OS 13.0"]),
    ("STREAMING_STICK", "roku", "Roku", ["Roku Streaming Stick 3800X", "roku 3800x"], "3800X", 1.4, 1.55, 3500, 0, 4, ["Roku OS 11.5"]),
    ("STREAMING_STICK", "fireos", "Amazon", ["Amazon Fire TV Stick 4K (AFTMM)", "Fire TV Stick 4K AFTMM"], "AFTMM", 5.0, 1.0, 5800, 0, None, ["Fire OS 6.7", "Fire OS 7.6"]),
    ("STREAMING_STICK", "fireos", "Amazon", ["Amazon Fire TV Stick Lite (AFTSSS)", "Fire TV Stick Lite"], "AFTSSS", 3.5, 1.2, 4300, 0, None, ["Fire OS 7.6"]),
    ("STREAMING_STICK", "fireos", "Amazon", ["Amazon Fire TV Stick (2nd Gen) AFTT", "AFTT"], "AFTT", 1.3, 1.6, 3500, 0, 4, ["Fire OS 5.2"]),
    ("STREAMING_STICK", "fireos", "Amazon", ["Amazon Fire TV Cube (AFTGAZL)"], "AFTGAZL", 1.0, 0.85, 5800, 0, None, ["Fire OS 7.6"]),
    ("STREAMING_STICK", "androidtv", "Google", ["Chromecast with Google TV (4K)", "Google Chromecast GTV 4K"], "GZRNL", 3.0, 0.95, 5800, 0, None, ["Android TV 12"]),
    ("TV", "androidtv", "TCL", ["TCL Google TV 2023", "TCL 2023 Google TV"], "55S551G", 1.5, 1.1, 5200, 0, None, ["Android TV 11"]),
    ("STREAMING_STICK", "tvos", "Apple", ["Apple TV 4K (3rd Gen)", "AppleTV14,1"], "AppleTV14,1", 2.5, 0.8, 5800, 0, None, ["tvOS 18.1", "tvOS 26.0"]),
    ("STREAMING_STICK", "tvos", "Apple", ["Apple TV HD", "AppleTV5,3"], "AppleTV5,3", 0.8, 1.25, 4300, 0, None, ["tvOS 18.1"]),
    ("MOBILE", "ios", "Apple", ["Apple iPhone 15 Pro", "iPhone16,1"], "iPhone16,1", 3.5, 0.9, 3000, 1, None, ["iOS 18.6", "iOS 26.0"]),
    ("MOBILE", "ios", "Apple", ["Apple iPhone 13", "iPhone14,5"], "iPhone14,5", 4.0, 1.0, 3000, 1, None, ["iOS 18.6", "iOS 26.0"]),
    ("MOBILE", "ios", "Apple", ["Apple iPhone 11", "iPhone12,1"], "iPhone12,1", 2.6, 1.1, 2500, 1, None, ["iOS 18.6"]),
    ("MOBILE", "ios", "Apple", ["Apple iPhone SE (2nd Gen)", "iPhone12,8"], "iPhone12,8", 1.2, 1.2, 2500, 1, None, ["iOS 17.7", "iOS 18.6"]),
    ("MOBILE", "android", "Samsung", ["Samsung Galaxy S23 (SM-S911U)", "SM-S911U"], "SM-S911U", 2.4, 0.95, 3000, 1, None, ["Android 14", "Android 15"]),
    ("MOBILE", "android", "Samsung", ["Samsung Galaxy A14 5G (SM-A146U)", "SM-A146U"], "SM-A146U", 2.0, 1.4, 2000, 1, None, ["Android 13", "Android 14"]),
    ("MOBILE", "android", "Google", ["Google Pixel 7a", "Pixel 7a"], "GWKK3", 1.2, 0.95, 3000, 1, None, ["Android 15", "Android 16"]),
    ("MOBILE", "android", "Motorola", ["Motorola moto g play (2023)", "moto g play - 2023"], "XT2271-5", 1.2, 1.5, 1800, 1, None, ["Android 12", "Android 13"]),
    ("TABLET", "ios", "Apple", ["Apple iPad (9th Gen)", "iPad12,1"], "iPad12,1", 2.8, 1.0, 3000, 1, None, ["iPadOS 18.6"]),
    ("TABLET", "ios", "Apple", ["Apple iPad Air (5th Gen)", "iPad13,16"], "iPad13,16", 1.0, 0.9, 3000, 1, None, ["iPadOS 18.6", "iPadOS 26.0"]),
    ("TABLET", "android", "Samsung", ["Samsung Galaxy Tab A8", "SM-X200"], "SM-X200", 1.2, 1.3, 2500, 1, None, ["Android 13", "Android 14"]),
    ("TABLET", "fireos", "Amazon", ["Amazon Fire HD 10 Kids", "KFTRWI"], "KFTRWI", 0.8, 1.35, 2000, 0, None, ["Fire OS 7.3"]),
    ("WEB", "web", None, ["Chrome PC (Halo)", "Chrome Windows"], None, 3.5, 1.0, 5200, 0, None, ["Windows 10", "Windows 11"]),
    ("WEB", "web", None, ["Edge PC (Halo)", "Edge Windows"], None, 1.2, 1.0, 5200, 0, None, ["Windows 11"]),
    ("WEB", "web", None, ["Safari MAC (Halo)", "Safari macOS"], None, 1.5, 0.95, 5200, 0, None, ["macOS 14", "macOS 15"]),
    ("WEB", "web", None, ["Chrome MAC (Halo)"], None, 1.0, 0.95, 5200, 0, None, ["macOS 15"]),
    ("WEB", "web", None, ["Firefox PC (Halo)"], None, 0.5, 1.05, 4300, 0, None, ["Windows 10"]),
    ("GAME_CONSOLE", "playstation", "Sony", ["Sony PlayStation 5", "PS5"], "CFI-1215A", 1.8, 0.9, 5800, 0, None, ["PS5 24.06"]),
    ("GAME_CONSOLE", "playstation", "Sony", ["Sony PlayStation 4", "PS4"], "CUH-2215B", 0.8, 1.2, 4300, 0, None, ["PS4 12.00"]),
    ("GAME_CONSOLE", "xbox", "Microsoft", ["Microsoft Xbox Series X|S", "Xbox Series X"], "1882", 1.2, 0.9, 5800, 0, None, ["Xbox OS 10.0.26100"]),
]
DM_CAT = {"TV": [], "STREAMING_STICK": [], "MOBILE": [], "TABLET": [], "WEB": [], "GAME_CONSOLE": []}
for _i, _m in enumerate(DEVICE_MODELS):
    DM_CAT[_m[0]].append(_i)
CAT_RAW = {  # messy category labels emitted by different ingestion paths
    "TV": ["TV", "TV", "TV", "Smart TV", "tv"], "STREAMING_STICK": ["STREAMING_STICK", "STREAMING_STICK", "Streaming Stick", "stb"],
    "MOBILE": ["MOBILE", "MOBILE", "Mobile", "phone"], "TABLET": ["TABLET", "TABLET", "Tablet"],
    "WEB": ["WEB", "WEB", "Browser", "web"], "GAME_CONSOLE": ["GAME_CONSOLE", "GAME_CONSOLE", "Game Console"]}
BIG_SCREEN = {"TV", "STREAMING_STICK", "GAME_CONSOLE"}
# app release train: (version, release day relative to T0). 9.0.0 started logging subtitle language.
APP_RELEASES = [("8.9.0", -150), ("8.10.0", -62), ("8.11.0", 27), ("8.12.0", 69), ("8.12.3", 96),
                ("9.0.0", 132), ("9.1.0", 174), ("9.1.2", 189), ("9.2.0", 223), ("9.3.0", 279),
                ("9.3.1", 301), ("9.4.0", 322)]
APP_V9 = 5
PLAT_LAG = {"ios": 5, "android": 8, "roku": 12, "fireos": 15, "androidtv": 14, "tvos": 7, "tizen": 35,
            "webos": 40, "vizio": 45, "vidaa": 50, "web": 0, "playstation": 18, "xbox": 14}


def version_string(R, plat, vidx):
    v = APP_RELEASES[vidx][0]
    if plat == "web":
        return "halo-%d.%04d.%03d.011" % (6 if vidx < APP_V9 else 7, 31 + vidx * 7, 100 + vidx * 13)
    x = R.random()
    if x < 0.04:
        return v + " (build %d)" % (21000 + vidx * 317)
    if x < 0.06:
        return "v" + v
    if plat in ("tizen", "webos", "vizio", "vidaa") and x < 0.20:
        return "tv-" + v
    return v


# --------------------------------------------------------------------------------------
# Content catalog
# --------------------------------------------------------------------------------------
GENRES = ["Drama", "Comedy", "Crime & Thriller", "Action & Adventure", "Sci-Fi & Fantasy", "Horror", "Romance",
          "Documentary", "Reality", "Stand-Up Comedy", "Anime", "International", "Kids & Family", "Animation"]
ADULT_G = GENRES[:12]
KIDS_G = ["Kids & Family", "Animation"]
ADJ = ["Silent", "Hidden", "Broken", "Golden", "Last", "Lost", "Crimson", "Quiet", "Wild", "Northern", "Little",
       "Bright", "Dark", "Hollow", "Iron", "Velvet", "Electric", "Burning", "Frozen", "Secret", "Distant", "Restless",
       "Savage", "Gentle", "Fallen", "Midnight", "Paper", "Glass", "Copper", "Salt", "Blue", "Black", "Silver",
       "Stone", "Long", "Small", "Strange", "Perfect", "Final", "First", "Southern", "Western", "Lucky", "Sweet",
       "Bitter", "Royal", "Rogue", "Open", "High", "Deep", "Lonely", "Empty", "Shattered", "Endless", "Scarlet",
       "Pale", "Brave", "Crooked", "Sunken", "Twisted", "Hungry", "Faithful", "Borrowed", "Second", "Neon", "Amber"]
NOUN = ["Harbor", "Ledger", "Kingdom", "River", "Road", "Garden", "House", "City", "Winter", "Summer", "Signal",
        "Echo", "Witness", "Orchard", "Frontier", "Station", "Circle", "Covenant", "Tide", "Empire", "Code", "Season",
        "Promise", "Lantern", "Society", "Meridian", "Horizon", "Valley", "Island", "Engine", "Mirror", "Crown",
        "Thief", "Doctor", "Detective", "Hunter", "Heart", "Shadow", "Storm", "Fire", "Wolf", "Raven", "Saints",
        "Sinners", "Strangers", "Neighbors", "Brothers", "Sisters", "Family", "Hotel", "Diner", "Ranch", "Bay",
        "Point", "Line", "Game", "Trial", "Verdict", "Affair", "Deal", "Job", "Heist", "Escape", "Drift", "Flight",
        "Coast", "Canyon", "Tower", "Bridge", "Machine", "Letters", "Daughters", "Sons", "Widow", "Pilot", "Sheriff",
        "Margin", "Archive", "Current", "Static", "Haven", "Pines", "Quarry", "Junction", "Parish", "County"]
KID_A = ["Penguin", "Otter", "Dragon", "Robot", "Bunny", "Dino", "Puppy", "Kitten", "Panda", "Owl", "Bee", "Llama",
         "Monster", "Rocket", "Fairy", "Truck", "Whale", "Turtle", "Unicorn", "Gecko"]
FIRST = ["Maya", "Leo", "Nora", "Theo", "Ivy", "Milo", "Ruby", "Finn", "Zara", "Ezra", "Luna", "Owen", "Hazel", "Jude"]
SURN = ["Okafor", "Brandt", "Castellano", "Whitlock", "Nakamura", "Delacroix", "Petrovic", "Oyelaran", "Lindqvist",
        "Marchetti", "Haddad", "Kowalczyk", "Abernathy", "Quintero", "Vasquez-Hale", "Thornbury"]
STUDIOS = ["Jetflix Studios", "Jetflix Animation", "Harborlight Pictures", "Northgate Television", "Copperline Media",
           "Bluefin Entertainment", "Sable Road Films", "Meridian Pictures", "Lumen Docs", "Kiteworks Kids",
           "Seventh Pier", "Granite Hill TV"]

TENTPOLES = [  # name, type, genre, release date, seasons existing before, weekly release
    ("Ironwood", "SERIES", "Drama", date(2025, 10, 17), 2, False),
    ("The Hollowing", "MOVIE", "Horror", date(2025, 10, 24), 0, False),
    ("Kingdom of Ash", "LIMITED_SERIES", "Sci-Fi & Fantasy", date(2025, 11, 21), 0, False),
    ("Starfall Protocol", "MOVIE", "Action & Adventure", date(2025, 12, 12), 0, False),
    ("Blue Meridian", "SERIES", "Crime & Thriller", date(2026, 1, 16), 1, True),
    ("The Quiet Partner", "SERIES", "Crime & Thriller", date(2026, 2, 20), 0, False),
    ("Ironwood: Origins", "SERIES", "Drama", date(2026, 3, 27), 0, False),
    ("Paper Saints", "SERIES", "Drama", date(2026, 4, 24), 0, False),
    ("Highwire", "SERIES", "Comedy", date(2026, 5, 22), 3, False),
    ("Pip and the Moon Garden", "MOVIE", "Animation", date(2026, 6, 19), 0, False),
    ("Salt Road", "SERIES", "Action & Adventure", date(2026, 7, 10), 1, True),
    ("Northbound", "MOVIE", "Action & Adventure", date(2026, 8, 14), 0, False),
    ("The Lantern Society", "SERIES", "Sci-Fi & Fantasy", date(2026, 9, 11), 0, False),
]
TP_STRENGTH = [1.0, 0.55, 0.8, 0.6, 0.85, 0.7, 0.75, 0.5, 0.7, 0.45, 0.8, 0.6, 0.85]
NOT_ON_SERVICE_QUERIES = ["yellowstone", "the office", "marvel", "star wars", "bluey", "succession", "nfl",
                          "the bear", "friends", "grey's anatomy", "college football", "harry potter", "suits",
                          "cocomelon", "the last of us", "taylor swift", "squid game", "ufc", "wwe", "true crime"]
GENRE_QUERIES = ["horror", "comedy movies", "christmas", "christmas movies", "kids", "documentary", "anime",
                 "thriller", "romance", "action", "new releases", "stand up", "halloween", "family movies",
                 "crime docs", "sci fi"]


class Catalog:
    """Fictional catalog: titles + episodes, tentpoles, sampling indexes."""

    def __init__(self, seed):
        rc = random.Random(seed * 31 + 7)
        names = set()
        T = []

        def mkname(kind, genre):
            for _ in range(200):
                x = rc.random()
                if genre in KIDS_G:
                    n = rc.choice(["%s and %s" % (rc.choice(KID_A), rc.choice(KID_A)),
                                   "The %s %ss" % (rc.choice(ADJ), rc.choice(KID_A)),
                                   "%s's %s Club" % (rc.choice(FIRST), rc.choice(KID_A)),
                                   "Little %s %s" % (rc.choice(KID_A), rc.choice(NOUN))])
                elif genre == "Documentary":
                    n = rc.choice(["Inside the %s" % rc.choice(NOUN), "%s: The True Story" % rc.choice(NOUN),
                                   "The %s Files" % rc.choice(NOUN), "American %s" % rc.choice(NOUN)])
                elif genre == "Stand-Up Comedy":
                    n = "%s %s: %s %s" % (rc.choice(FIRST), rc.choice(SURN), rc.choice(ADJ), rc.choice(NOUN))
                elif genre == "Reality":
                    n = rc.choice(["%s Wars" % rc.choice(NOUN), "Love on the %s" % rc.choice(NOUN),
                                   "%s %s Challenge" % (rc.choice(ADJ), rc.choice(NOUN)),
                                   "Selling the %s" % rc.choice(NOUN)])
                elif x < 0.35:
                    n = "The %s %s" % (rc.choice(ADJ), rc.choice(NOUN))
                elif x < 0.55:
                    n = "%s of the %s" % (rc.choice(NOUN), rc.choice(NOUN))
                elif x < 0.75:
                    n = "%s %s" % (rc.choice(ADJ), rc.choice(NOUN))
                elif x < 0.88:
                    n = "The %s" % rc.choice(NOUN)
                else:
                    n = "%s %s" % (rc.choice(FIRST), rc.choice(NOUN))
                if n in names and kind == "MOVIE" and rc.random() < 0.5:
                    n = n + " " + rc.choice(["2", "II", "Returns"])
                if n not in names:
                    names.add(n)
                    return n
            n = "Untitled %d" % len(names)
            names.add(n)
            return n

        gw_movie = [10, 11, 9, 9, 6, 7, 6, 7, 0.5, 4, 1.5, 4, 6, 4]
        gw_series = [13, 10, 11, 6, 7, 3, 3, 6, 7, 0, 3, 4, 5, 4]
        plan = [("MOVIE", 1980, gw_movie), ("SERIES", 1050, gw_series), ("LIMITED_SERIES", 120, gw_series),
                ("SPECIAL", 110, None)]
        for kind, n, gw in plan:
            gc = cumsum(gw) if gw else None
            for _ in range(n):
                g = "Stand-Up Comedy" if kind == "SPECIAL" else wchoice(rc, GENRES, gc)
                T.append(self._mk_title(rc, kind, g, mkname(kind, g)))
        # extra originals premiering in the window (non-tentpole)
        for _ in range(72):
            kind = "SERIES" if rc.random() < 0.6 else "MOVIE"
            g = wchoice(rc, GENRES, cumsum(gw_series if kind == "SERIES" else gw_movie))
            t = self._mk_title(rc, kind, g, mkname(kind, g), force_window_original=True)
            T.append(t)
        rc.shuffle(T)
        self.tentpole_idx = []
        for k, (nm, kind, g, rel, prior_seasons, weekly) in enumerate(TENTPOLES):
            names.add(nm)
            t = self._mk_title(rc, kind, g, nm, tentpole=(rel, prior_seasons, weekly))
            t["pop"] = 6.0 * TP_STRENGTH[k]
            pos = rc.randrange(len(T))
            T.insert(pos, t)
        # ids: catalog ids look like large sparse integers
        ids = sorted(rc.sample(range(70_000_000, 81_999_999), len(T)))
        rc.shuffle(ids)
        for i, t in enumerate(T):
            t["id"] = ids[i]
        self.T = T
        self.tentpole_idx = [i for i, t in enumerate(T) if t.get("tp") is not None]
        self.tentpole_idx.sort(key=lambda i: T[i]["tp"][0])
        # episodes
        self.ep_id, self.ep_season, self.ep_num, self.ep_rt, self.ep_rel, self.ep_title = [], [], [], [], [], []
        for t in T:
            t["ep0"] = len(self.ep_id)
            for (s, e, rt, rel) in t.get("eps", []):
                self.ep_id.append(0)
                self.ep_season.append(s)
                self.ep_num.append(e)
                self.ep_rt.append(rt)
                self.ep_rel.append(rel)
                self.ep_title.append("%s %s" % (rc.choice(["The", "A", "Chapter %d:" % e]), rc.choice(NOUN)))
            t["nep"] = len(self.ep_id) - t["ep0"]
            t.pop("eps", None)
        eids = rc.sample(range(80_000_000, 99_999_999), len(self.ep_id))
        self.ep_id = eids
        # sampling indexes per genre (kids separately), cumulative popularity
        self.by_genre = {}
        for g in GENRES:
            idx = [i for i, t in enumerate(T) if (t["g1"] == g or t["g2"] == g) and t.get("tp") is None]
            self.by_genre[g] = (idx, cumsum([T[i]["pop"] for i in idx]))
        kid_idx = [i for i, t in enumerate(T) if t["kids"]]
        self.kids_all = (kid_idx, cumsum([T[i]["pop"] for i in kid_idx]))
        order = sorted(range(len(T)), key=lambda i: T[i]["avail_from"])
        self.new_order = order
        self.new_days = [T[i]["avail_from"] for i in order]
        self.new_cum = cumsum([T[i]["pop"] ** 0.7 for i in order])
        self.title_index_by_id = {t["id"]: i for i, t in enumerate(T)}

    def _mk_title(self, rc, kind, g, name, force_window_original=False, tentpole=None):
        kids = g in KIDS_G and rc.random() < 0.9
        series = kind in ("SERIES", "LIMITED_SERIES")
        orig = tentpole is not None or force_window_original or rc.random() < 0.14
        if tentpole is not None:
            rel_day = day_of(tentpole[0])
            ry = tentpole[0].year
        elif force_window_original:
            rel_day = rc.randrange(-20, WIN_DAYS - 5)
            ry = (T0D + timedelta(days=rel_day)).year
        else:
            ry = int(min(2026, max(1972, 2025 - rc.expovariate(1 / 9.0)))) if not orig else rc.choice([2023, 2024, 2025])
            rel_day = None
        # when it arrived on Jetflix
        if tentpole is not None or force_window_original:
            avail_from = rel_day
        elif orig:
            avail_from = rc.randrange(LAUNCH_DAY, -20)
        else:
            x = rc.random()
            avail_from = LAUNCH_DAY if x < 0.45 else rc.randrange(LAUNCH_DAY, WIN_DAYS - 3)
            avail_from = max(avail_from, (date(ry, 1, 1) - T0D).days + 120)
            if avail_from >= WIN_DAYS:
                avail_from = rc.randrange(LAUNCH_DAY, WIN_DAYS - 3)
        if not orig and tentpole is None and rc.random() < 0.17:
            m = rc.randrange(0, 26)
            y, mo = 2024 + (m + 2) // 12, (m + 2) % 12 + 1
            until = max(day_of(date(y, mo, 1)), avail_from + 120)
        else:
            until = None
        if kids:
            rating = rc.choice(["TV-Y", "TV-Y7", "TV-G"]) if series else rc.choice(["G", "PG", "G", "TV-Y7"])
        elif g == "Horror":
            rating = rc.choice(["TV-MA", "R", "R"]) if not series else "TV-MA"
        elif series:
            rating = rc.choice(["TV-14", "TV-MA", "TV-PG", "TV-14", "TV-MA"])
        else:
            rating = rc.choice(["PG-13", "R", "PG", "PG-13", "R", "NR"])
        if rc.random() < 0.004:
            rating = None
        lang = "en"
        if g == "Anime":
            lang = "ja"
        elif g == "International":
            lang = rc.choice(["es", "ko", "fr", "de", "es", "hi", "it", "pt", "ko"])
        elif rc.random() < 0.03:
            lang = "es"
        g2 = rc.choice(GENRES) if rc.random() < 0.45 else None
        if g2 == g:
            g2 = None
        if kids and g2 not in (None,) + tuple(KIDS_G):
            g2 = None
        pop = rc.lognormvariate(0, 1.25) * (1.8 if orig else 1.0) * (0.6 if kids else 1.0)
        t = {"name": name, "type": kind, "g1": g, "g2": g2, "rating": rating, "lang": lang, "year": ry,
             "orig": int(orig), "kids": int(kids), "studio": rc.choice(STUDIOS[:2] if orig else STUDIOS[2:]),
             "branched": int(rc.random() < 0.006), "avail_from": avail_from, "until": until, "pop": pop,
             "tier": None, "series": series}
        if kind == "MOVIE":
            t["rt"] = int(max(70, min(185, rc.gauss(102, 17) if not kids else rc.gauss(88, 10)))) * 60
        elif kind == "SPECIAL":
            t["rt"] = int(rc.uniform(52, 75)) * 60
        else:
            t["rt"] = None
        if series:
            if g in ("Comedy",):
                ert = (21, 31)
            elif kids:
                ert = (11, 24)
            elif g in ("Anime",):
                ert = (23, 25)
            elif g in ("Reality", "Documentary"):
                ert = (38, 50)
            else:
                ert = (40, 62)
            if kind == "LIMITED_SERIES":
                ns = 1
            elif tentpole is not None:
                ns = tentpole[1] + 1
            elif force_window_original:
                ns = 1
            else:
                ns = 1 + min(7, int(rc.expovariate(1 / 1.3)))
            eps = []
            if tentpole is not None:
                last_rel = day_of(tentpole[0])
            elif force_window_original:
                last_rel = rel_day
            else:
                last_rel = avail_from if not orig else max(avail_from, rc.randrange(-400, WIN_DAYS - 10))
            for s in range(1, ns + 1):
                if tentpole is not None or orig:
                    s_rel = last_rel - (ns - s) * rc.randrange(300, 480)
                    s_rel = max(s_rel, LAUNCH_DAY) if orig else s_rel
                else:
                    s_rel = avail_from
                ne = rc.choice([6, 8, 8, 10, 10, 12, 13, 22]) if kind != "LIMITED_SERIES" else rc.choice([4, 5, 6, 8])
                if kids:
                    ne = rc.choice([13, 20, 26])
                weekly = tentpole is not None and tentpole[2] and s == ns
                base_rt = rc.uniform(*ert)
                for e in range(1, ne + 1):
                    rt = int(max(8, rc.gauss(base_rt, 2.5)) * 60)
                    rel = s_rel + (7 * (e - 1) if weekly else 0)
                    eps.append((s, e, rt, rel))
            t["eps"] = eps
            if orig:
                t["avail_from"] = min(t["avail_from"], eps[0][3])
        if tentpole is not None:
            t["tp"] = (day_of(tentpole[0]), tentpole[1], tentpole[2])
            t["tier"] = "A"
            t["avail_from"] = min(t["avail_from"], t.get("eps", [(0, 0, 0, t["avail_from"])])[0][3])
        else:
            x = rc.random()
            t["tier"] = ("A" if x < 0.004 else "B" if x < 0.12 else "C") if orig or t["avail_from"] > -120 else \
                (None if x < 0.6 else "C")
        return t

    def available(self, i, d):
        t = self.T[i]
        return t["avail_from"] <= d and (t["until"] is None or d < t["until"])

    def write(self, out_dir):
        cols = ["title_id", "title_name", "title_type", "primary_genre", "secondary_genre", "maturity_rating",
                "original_language", "release_year", "runtime_min", "num_seasons", "num_episodes",
                "is_jetflix_original", "is_kids_content", "has_branched_playback", "studio", "promo_tier",
                "available_from", "available_until"]
        rows = []
        for t in self.T:
            nseas = len({self.ep_season[j] for j in range(t["ep0"], t["ep0"] + t["nep"])}) if t["nep"] else None
            rows.append([t["id"], t["name"], t["type"], t["g1"], t["g2"], t["rating"], t["lang"], t["year"],
                         t["rt"] // 60 if t["rt"] else None, nseas, t["nep"] or None, t["orig"], t["kids"],
                         t["branched"], t["studio"], t["tier"], DAYSTR[di(t["avail_from"])],
                         DAYSTR[di(t["until"])] if t["until"] is not None else None])
        n1 = write_table(out_dir, "catalog", cols, rows)
        cols = ["episode_id", "title_id", "season_number", "episode_number", "episode_title", "runtime_sec",
                "release_date"]
        rows = []
        for t in self.T:
            for j in range(t["ep0"], t["ep0"] + t["nep"]):
                rows.append([self.ep_id[j], t["id"], self.ep_season[j], self.ep_num[j], self.ep_title[j],
                             self.ep_rt[j], DAYSTR[di(max(self.ep_rel[j], D_MIN + 1))]])
        n2 = write_table(out_dir, "episodes", cols, rows)
        return n1, n2


def csv_val(v):
    if v is None:
        return ""
    s = str(v)
    if "," in s or '"' in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def write_table(out_dir, name, cols, rows):
    path = os.path.join(out_dir, name + ".csv.gz")
    raw = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6) as f:
        line = ",".join(cols) + "\n"
        f.write(line)
        raw += len(line.encode())
        for r in rows:
            line = ",".join(csv_val(v) for v in r) + "\n"
            raw += len(line.encode())
            f.write(line)
    return len(rows), raw


# --------------------------------------------------------------------------------------
# Hidden behavioural types (never written to output)
# --------------------------------------------------------------------------------------
TYPES = ["family", "adult", "binger", "casual", "chaser", "serial", "passive", "movie"]
TP = {  # sittings/day (median), satisfaction mean, hazard mult, exo mult, binge, return mults
    "family": dict(R=0.30, mu=0.20, hz=0.68, exo=0.8, binge=0.42, r90=0.75, rl=1.0, pser=0.55),
    "adult": dict(R=0.21, mu=0.08, hz=0.92, exo=1.0, binge=0.40, r90=0.9, rl=1.0, pser=0.55),
    "binger": dict(R=0.30, mu=0.00, hz=0.95, exo=0.9, binge=0.66, r90=1.0, rl=1.0, pser=0.85),
    "casual": dict(R=0.105, mu=-0.10, hz=1.12, exo=1.1, binge=0.28, r90=0.7, rl=0.9, pser=0.5),
    "chaser": dict(R=0.25, mu=-0.10, hz=1.05, exo=1.0, binge=0.55, r90=1.35, rl=1.5, pser=0.7),
    "serial": dict(R=0.20, mu=-0.25, hz=1.75, exo=1.2, binge=0.45, r90=2.0, rl=1.6, pser=0.6),
    "passive": dict(R=0.022, mu=0.00, hz=0.42, exo=0.6, binge=0.25, r90=0.4, rl=0.6, pser=0.5),
    "movie": dict(R=0.17, mu=0.05, hz=0.92, exo=1.0, binge=0.25, r90=0.85, rl=1.0, pser=0.25),
}
W_NEW = [0.15, 0.24, 0.13, 0.17, 0.06, 0.08, 0.07, 0.10]
W_INC = [0.23, 0.26, 0.13, 0.12, 0.03, 0.05, 0.11, 0.07]
W_LAPSED = [0.08, 0.17, 0.12, 0.13, 0.22, 0.20, 0.02, 0.06]
TENURE = [2.0, 1.55, 1.3, 1.15, 1.05, 1.0, 0.94, 0.88, 0.84, 0.8, 0.77, 0.75]
CHANNELS = ["organic_direct", "paid_search", "paid_social", "referral_link", "ios_app_store", "google_play",
            "smart_tv_app", "affiliate", "tv_ad_campaign"]
CH_W = [29, 18, 15, 7, 10, 5, 10, 3, 3]
CH_HZ = {"organic_direct": 0.88, "paid_search": 1.0, "paid_social": 1.28, "referral_link": 0.82,
         "ios_app_store": 1.08, "google_play": 1.1, "smart_tv_app": 0.95, "affiliate": 1.32, "tv_ad_campaign": 1.0}
PAY_HZ = {"CARD": 1.0, "APP_STORE": 1.13, "PAYPAL": 1.05}
EMAIL_DOM = ["gmail.com", "yahoo.com", "icloud.com", "hotmail.com", "outlook.com", "aol.com", "comcast.net",
             "att.net", "me.com", "msn.com", "live.com", "sbcglobal.net", "verizon.net", "protonmail.com",
             "ymail.com", "cox.net", "charter.net", "mac.com", "bellsouth.net", "yahoo.co"]
EMAIL_W = [48, 11, 9, 7, 6, 3, 2, 1.5, 1.2, 1, 1, 1, 0.7, 0.6, 0.5, 0.5, 0.4, 0.3, 0.3, 0.05]
APPLE_MAIL = {"icloud.com", "me.com", "mac.com"}
PROFILE_NAMES = ["Mom", "Dad", "Kids", "Alex", "Sam", "Jordan", "Taylor", "Chris", "Pat", "Jamie", "Morgan",
                 "Casey", "Riley", "Avery", "Nana", "Guest", "Living Room", "Family", "Me", "Babe", "Jess", "Mike",
                 "Sarah", "Dave", "Liz", "Tony", "Maria", "Jose", "Ana", "Kim", "Lee", "Ty", "Bri", "Max", "Ella"]
KIDS_NAMES = ["Kids", "Kiddos", "Emma", "Liam", "Noah", "Olivia", "Ava", "Mason", "Lucas", "Mia", "Zoe", "Jr",
              "Little Ones", "Kids 2", "Ellie"]


class Plan:
    """Account-level plan arrays (built identically in every process from the seed)."""

    def __init__(self, cfg):
        rng = np.random.default_rng(cfg["seed"])
        N = cfg["n_accounts"]
        n_inc, n_lap = cfg["n_incumbent"], cfg["n_lapsed_returner"]
        n_new = N - n_inc - n_lap
        cohort = np.array([0] * n_inc + [1] * n_new + [2] * n_lap)
        rng.shuffle(cohort)
        self.N = N
        self.cohort = cohort
        # state / zip3
        pops = np.array([s[1] for s in STATES])
        st = rng.choice(len(STATES), N, p=pops / pops.sum())
        self.state = st
        zip3_w = {}
        for k, s in enumerate(STATES):
            zs = [z for a, b in s[3] for z in range(a, b + 1)]
            w = rng.dirichlet(np.ones(len(zs)) * 0.6)
            zip3_w[k] = (zs, w)
        self.zip3 = np.array([zip3_w[k][0][rng.choice(len(zip3_w[k][0]), p=zip3_w[k][1])] for k in st])
        bb = {}
        for k, s in enumerate(STATES):
            for z in zip3_w[k][0]:
                bb[z] = float(np.exp(rng.normal(0, 0.16))) * (1.22 if s[4] else 1.0) * (1.25 if rng.random() < 0.06 else 1.0)
        self.bb = bb
        # signup timing
        created = np.zeros(N, dtype=np.int64)
        # incumbents: density ~ acquisition(t) * survival(age)
        ages = np.arange(1, -LAUNCH_DAY + 1)
        acq = 1.0 + 1.6 * (1 - ages / -LAUNCH_DAY)
        acq[ages > -LAUNCH_DAY - 30] *= 2.6
        surv = np.exp(-0.034 * ages / 30.4) * (0.62 + 0.38 * np.exp(-ages / 60.0))
        w = acq * surv
        w /= w.sum()
        inc_idx = np.where(cohort == 0)[0]
        a = rng.choice(ages, len(inc_idx), p=w)
        created[inc_idx] = -a * 86400 + rng.integers(0, 86400, len(inc_idx))
        # new: daily acquisition curve with tentpole spikes
        days = np.arange(WIN_DAYS)
        base = 1.02 ** (days / 30.4)
        mmult = {10: 1.0, 11: 1.05, 12: 1.12, 1: 1.18, 2: 0.95, 3: 0.95, 4: 0.9, 5: 0.92, 6: 0.95, 7: 1.0, 8: 0.95,
                 9: 1.0}
        base = base * np.array([mmult[MON[di(d)]] * (1.14 if DOW[di(d)] >= 4 else 1.0) for d in days])
        for d, k in HOL.items():
            if 0 <= d < WIN_DAYS and k in ("black_friday", "christmas", "new_year"):
                base[d] *= {"black_friday": 1.55, "christmas": 1.8, "new_year": 1.4}[k]
        spike = np.zeros(WIN_DAYS)
        for k, tp in enumerate(TENTPOLES):
            r = day_of(tp[3])
            for j in range(-3, 21):
                if 0 <= r + j < WIN_DAYS:
                    spike[r + j] += TP_STRENGTH[k] * 1.25 * (np.exp(-j / 3.2) if j >= 0 else 0.25 * np.exp(j / 1.5))
        tot = base + spike
        new_idx = np.where(cohort == 1)[0]
        nd = rng.choice(days, len(new_idx), p=tot / tot.sum())
        self.new_spike_share = spike / tot
        created[new_idx] = nd * 86400 + rng.integers(0, 86400, len(new_idx))
        # lapsed returners: created well before; rejoin in window
        lap_idx = np.where(cohort == 2)[0]
        a = rng.choice(ages[60:], len(lap_idx), p=w[60:] / w[60:].sum())
        created[lap_idx] = -a * 86400 + rng.integers(0, 86400, len(lap_idx))
        rj_w = base + spike * 1.8
        self.rejoin_day = np.full(N, -1)
        self.rejoin_day[lap_idx] = rng.choice(days, len(lap_idx), p=rj_w / rj_w.sum())
        self.created = created
        # hidden type
        typ = np.zeros(N, dtype=np.int64)
        typ[inc_idx] = rng.choice(8, len(inc_idx), p=W_INC)
        typ[lap_idx] = rng.choice(8, len(lap_idx), p=W_LAPSED)
        pn = np.array(W_NEW) / sum(W_NEW)
        t_new = rng.choice(8, len(new_idx), p=pn)
        sh = self.new_spike_share[nd]
        is_ch = rng.random(len(new_idx)) < (0.04 + 0.8 * sh)
        t_new[is_ch] = TYPES.index("chaser")
        typ[new_idx] = t_new
        self.typ = typ
        # chased tentpole (for chasers): most recent tentpole release before signup/rejoin
        tp_days = [day_of(t[3]) for t in TENTPOLES]
        chase = np.full(N, -1)
        for i in np.where(typ == TYPES.index("chaser"))[0]:
            ref_d = int(created[i] // 86400) if cohort[i] == 1 else int(self.rejoin_day[i]) if cohort[i] == 2 else 0
            cands = [k for k, r in enumerate(tp_days) if r - 4 <= ref_d <= r + 25]
            if cands:
                chase[i] = cands[-1]
        self.chase = chase
        # test accounts
        test = np.zeros(N, dtype=np.int64)
        tsel = rng.choice(N, cfg["n_test"], replace=False)
        test[tsel[:20]] = 2  # employee
        test[tsel[20:]] = 1  # QA test
        self.test = test
        # channel
        ch = rng.choice(len(CHANNELS), N, p=np.array(CH_W) / sum(CH_W))
        ci = TYPES.index("chaser")
        for i in np.where(typ == ci)[0]:
            if rng.random() < 0.45:
                ch[i] = rng.choice([1, 2, 7, 8])
        self.channel = ch
        # account-level latent parameters
        self.mu = rng.normal(0, 0.5, N) + np.array([TP[TYPES[t]]["mu"] for t in typ])
        self.Rbase = np.exp(rng.normal(0, 0.85, N)) * np.array([TP[TYPES[t]]["R"] for t in typ])
        self.kappa = np.exp(rng.normal(0, 0.25, N))
        self.kappa[typ == TYPES.index("passive")] *= 0.55
        self.seed = cfg["seed"]
        # account ids increase with creation time, with gaps (other platform accounts not sampled)
        order = np.argsort(created, kind="stable")
        gaps = rng.geometric(0.42, N)
        ids = 4_100_000 + np.cumsum(gaps)
        self.account_id = np.zeros(N, dtype=np.int64)
        self.account_id[order] = ids


# --------------------------------------------------------------------------------------
# Output tables
# --------------------------------------------------------------------------------------
TABLES = {
    "accounts": ["account_id", "account_created_ts", "account_type", "signup_channel", "signup_platform",
                 "signup_device_category", "state", "zip3", "account_timezone", "preferred_language",
                 "email_domain", "email_verified", "phone_on_file", "birth_year", "gender",
                 "email_consent_marketing", "email_consent_surveys", "email_consent_kids_activity",
                 "sms_consent_transactional", "sms_consent_informational", "whatsapp_consent",
                 "marketing_matched_identifiers_consent", "ccpa_do_not_sell_share", "test_participation",
                 "parental_pin_enabled", "two_step_verification_enabled"],
    "profiles": ["profile_id", "account_id", "profile_name", "is_kids", "maturity_level", "profile_language",
                 "avatar_id", "autoplay_next_episode", "autoplay_previews", "is_account_owner", "created_ts",
                 "deleted_ts"],
    "devices": ["device_id", "account_id", "device_category", "device_type_raw", "platform", "manufacturer",
                "model_code", "os_version", "app_version_first", "app_version_last", "esn_hash", "push_enabled",
                "first_seen_ts", "last_seen_ts", "deactivated_ts"],
    "payment_methods": ["payment_method_id", "account_id", "method_type", "provider", "card_brand", "card_funding",
                        "card_exp_month", "card_exp_year", "billing_zip3", "added_ts", "last_updated_ts",
                        "removed_ts", "removal_source"],
    "subscription_history": ["subscription_id", "account_id", "period_seq", "signup_type", "opened_ts",
                             "plan_code", "plan_name", "plan_price_usd", "billing_cycle", "max_concurrent_streams",
                             "max_video_quality", "has_ads", "is_free_trial_at_signup", "billing_anchor_day",
                             "initial_payment_method_id", "cancel_requested_ts", "cancel_channel", "closed_ts",
                             "is_customer_initiated_cancel", "close_reason_code"],
    "billing_history": ["transaction_id", "account_id", "subscription_id", "payment_method_id", "invoice_id",
                        "transaction_ts", "transaction_type", "attempt_number", "amount_usd", "currency",
                        "billing_period_start", "billing_period_end", "pmt_status", "final_invoice_result",
                        "failure_code", "gateway", "next_billing_date"],
    "membership_events": ["event_id", "account_id", "subscription_id", "event_ts", "event_type", "source",
                          "device_id", "payment_method_id"],
    "consent_events": ["account_id", "consent_type", "new_value", "changed_ts", "source"],
    "viewing_activity": ["view_id", "account_id", "profile_id", "device_id", "start_ts", "duration", "title_id",
                         "episode_id", "supplemental_video_type", "attributes", "bookmark", "latest_bookmark",
                         "is_offline_download", "subtitle_language"],
    "playback_events": ["view_id", "event_seq", "event_type", "client_ts", "server_received_ts",
                        "session_offset_ms", "media_offset_ms"],
    "playback_quality": ["playback_id", "view_id", "account_id", "device_id", "title_id", "client_ts",
                         "app_version", "network_type", "isp_name", "geo_state", "cdn_pop", "startup_time_ms",
                         "rebuffer_count", "rebuffer_duration_ms", "played_duration_ms", "avg_bitrate_kbps",
                         "peak_resolution", "error_code", "exit_before_video_start"],
    "search_history": ["search_id", "account_id", "profile_id", "device_id", "is_kids", "search_ts",
                       "query_typed", "displayed_title_id", "action", "section"],
    "clickstream": ["event_id", "app_session_id", "account_id", "profile_id", "device_id", "event_type", "page",
                    "title_id", "client_ts", "server_received_ts"],
    "ratings": ["rating_id", "account_id", "profile_id", "title_id", "rating_type", "thumbs_value", "device_id",
                "event_ts"],
    "my_list": ["list_item_id", "account_id", "profile_id", "title_id", "added_ts", "removed_ts", "add_source"],
    "login_events": ["login_event_id", "account_id", "device_id", "event_ts", "event_type", "auth_method",
                     "ip_hash", "geo_state", "failure_reason"],
    "support_contacts": ["contact_id", "account_id", "contact_ts", "channel", "contact_reason", "resolution",
                         "handle_time_sec", "csat_score", "agent_tier", "device_id"],
    "communications_log": ["message_id", "account_id", "channel", "message_type", "campaign_id",
                           "template_version", "sent_ts", "delivered_ts", "bounce_type", "opened_ts", "clicked_ts",
                           "unsubscribed_ts", "device_id"],
}
SIM_TABLES = list(TABLES.keys())

REF = None   # per-process reference data (catalog, plan)


def get_ref():
    global REF
    if REF is None:
        REF = {"cat": Catalog(CFG["seed"]), "plan": Plan(CFG)}
    return REF


def L(*vals):
    return ",".join("" if v is None else str(v) for v in vals)


# --------------------------------------------------------------------------------------
# Per-account simulation
# --------------------------------------------------------------------------------------
ACTIVE, PENDING, GRACE, LAPSED = 0, 1, 2, 3
FAIL_CODES_CARD = [("INSUFFICIENT_FUNDS", 0.42), ("DO_NOT_HONOR", 0.24), ("GENERIC_DECLINE", 0.14),
                   ("PROCESSOR_TIMEOUT", 0.08), ("CARD_RESTRICTED", 0.05), ("LOST_OR_STOLEN", 0.03),
                   ("INVALID_ACCOUNT", 0.04)]
FAIL_CODES_STORE = [("STORE_BILLING_RETRY", 0.7), ("STORE_PAYMENT_DECLINED", 0.3)]
FAIL_CODES_PP = [("PAYPAL_FUNDING_FAILED", 0.6), ("PAYPAL_INSTRUMENT_DECLINED", 0.3), ("PROCESSOR_TIMEOUT", 0.1)]
ERROR_CODES = ["JF-1011", "JF-1011", "JF-5003", "JF-2002", "JF-3104", "JF-1001", "JF-7020"]
SUPPORT_RES = ["RESOLVED", "RESOLVED", "RESOLVED", "RESOLVED_WORKAROUND", "ESCALATED", "UNRESOLVED",
               "CUSTOMER_ABANDONED"]


def pick_code(R, lst):
    x = R.random()
    for c, p in lst:
        x -= p
        if x <= 0:
            return c
    return lst[-1][0]


class Sim:
    def __init__(self, idx, out):
        ref = get_ref()
        self.cat = ref["cat"]
        P = self.P = ref["plan"]
        self.idx = idx
        self.out = out
        self.R = random.Random(P.seed * 1_000_003 + idx * 7_919)
        self.aid = int(P.account_id[idx])
        self.cohort = int(P.cohort[idx])
        self.typ = TYPES[int(P.typ[idx])]
        self.tp = TP[self.typ]
        self.test = int(P.test[idx])
        self.st = STATES[int(P.state[idx])]
        self.state_code = self.st[0]
        self.zip3 = int(P.zip3[idx])
        self.tz = TZ_ZIP3.get(self.zip3, self.st[2])
        self.bb = P.bb[self.zip3]
        self.mu = float(P.mu[idx])
        self.Rb = float(P.Rbase[idx]) * CFG["sit_scale"]
        rel = float(P.Rbase[idx]) / TP[self.typ]["R"]
        self.use_mult = 1.0 if self.typ == "passive" else min(4.0, max(0.3, rel ** -CFG["b_use"]))
        self.exo_mult = min(2.5, max(0.25, rel ** 0.6))
        self.kappa = float(P.kappa[idx])
        self.channel = CHANNELS[int(P.channel[idx])]
        self.created_s = int(P.created[idx])
        self.chase_tp = int(P.chase[idx])
        self.counters = {}
        self.subs = []
        self.pms = []
        self.profiles = []
        self.devices = []
        self.views_by_key = {}
        self.view_rows = []
        self.cs_seq = 0
        self.last_act_end = -10 ** 9

    # ------------------------------------------------------------------ ids
    ID_BASE = {"tx": 300_000_000, "me": 200_000_000, "cm": 900_000_000, "lg": 500_000_000, "sc": 2_000_000,
               "sr": 4_000_000_000, "rt": 600_000_000, "ml": 700_000_000, "inv": 0, "as": 0}

    def nid(self, kind, span):
        c = self.counters.get(kind, 0)
        self.counters[kind] = c + 1
        return self.ID_BASE.get(kind, 0) + self.idx * span + c

    def w(self, table, line):
        self.out[table].append(line)

    # ------------------------------------------------------------------ setup
    def setup(self):
        R = self.R
        tp = self.tp
        self.binge = min(0.85, max(0.08, R.gauss(tp["binge"], 0.12)))
        self.night_shift = R.random() < 0.05
        self.has_kids = (self.typ == "family" and R.random() < 0.85) or (self.typ != "family" and R.random() < 0.09)
        self.shared = R.random() < (0.09 if self.typ != "passive" else 0.02)
        self.budget = R.random() < 0.22
        self.student = R.random() < (0.07 if self.typ in ("adult", "binger", "casual", "chaser", "serial") else 0.01)
        self.dev = R.gauss(0, 0.3)
        self.declining = False
        self.dec_target = 0.0
        if self.cohort == 0 and R.random() < CFG["decline_onset"] / (CFG["decline_onset"] + CFG["decline_recover"]):
            # incumbents start in the stationary mix: some are already part-way through a decline
            self.declining = True
            self.dec_target = -R.uniform(1.0, 2.3)
            self.dev = self.dec_target * R.uniform(0.2, 1.0) + R.gauss(0, 0.2)
        self.shock = 0.0
        self.effects = {}  # name -> (mult, until_day)
        self.gap_start = None
        self.chase_done = None
        self.bad_log = []  # (day, n)
        self.n_prior_vol = 0
        self.status = LAPSED
        self.post_cancel_mult = 1.0
        self.consent = {}
        self.winback_day = None
        self.last_ptype = None
        self.return_day = None
        self.email_dom = EMAIL_DOM[bisect.bisect_right(cumsum(EMAIL_W), R.random() * sum(EMAIL_W))]
        if self.test:
            self.email_dom = "jetflix-qa.test" if self.test == 1 else "jetflix.com"
        self.apple_mpp = self.email_dom in APPLE_MAIL or R.random() < 0.18
        self.phone = R.random() < 0.58
        # payment method type preference
        ch = self.channel
        x = R.random()
        if ch == "ios_app_store":
            self.pay_pref = "APPLE" if x < 0.86 else "CARD"
        elif ch == "google_play":
            self.pay_pref = "GOOGLE" if x < 0.84 else "CARD"
        elif ch == "smart_tv_app":
            self.pay_pref = "ROKU" if x < 0.36 else "AMAZON" if x < 0.56 else "CARD" if x < 0.88 else "PAYPAL"
        else:
            self.pay_pref = "CARD" if x < 0.60 else "PAYPAL" if x < 0.78 else "APPLE" if x < 0.915 else "GOOGLE"
        self.card_funding = "debit" if R.random() < (0.42 if self.budget else 0.3) else "credit"
        if R.random() < 0.035:
            self.card_funding = "prepaid"
        self.card_brand = wchoice(R, ["VISA", "MASTERCARD", "AMEX", "DISCOVER"], cumsum([52, 28, 12, 8]))
        # home network
        self.isp = wchoice(R, ISPS, cumsum(ISP_W))
        if self.st[4] and R.random() < 0.2:
            self.isp = R.choice(["Windstream", "Frontier", "CenturyLink", "Starlink", "Mediacom"])
        self.home_ips = [hhash("ip", self.aid, k) for k in range(3)]
        self.remote_state = R.choice([s[0] for s in STATES[:30]]) if self.shared else None
        # vacations and household change
        self.vac = []
        nv = poisson(R, 1.5 if self.typ != "passive" else 0.6)
        for _ in range(nv):
            while True:
                s = R.randrange(-30, WIN_DAYS)
                m = MON[di(s)]
                acc = 0.35 + (0.65 if m in (6, 7, 8) else 0) + (0.5 if m == 12 and DOM[di(s)] > 18 else 0) + \
                    (0.4 if m == 11 and 22 <= DOM[di(s)] <= 28 else 0) + (0.3 if m == 3 else 0)
                if R.random() < acc / 1.2:
                    break
            ln = R.randint(3, 16)
            self.vac.append((s, s + ln, R.uniform(0.0, 0.3), R.choice([x[0] for x in STATES])))
        self.hh_change = None
        if R.random() < 0.085:
            self.hh_change = (R.randrange(0, WIN_DAYS), wchoice(R, ["move", "split", "new_baby"], cumsum([60, 25, 15])))
        # tentpole interest
        self.tp_interest = set()
        for k, (nm, kind, g, rel, _, _) in enumerate(TENTPOLES):
            p = 0.16 * TP_STRENGTH[k] * (1.6 if self.typ == "binger" else 0.4 if self.typ == "passive" else 1.0)
            if g in KIDS_G:
                p = 0.45 if self.has_kids else 0.02
            if R.random() < p:
                self.tp_interest.add(k)
        if self.chase_tp >= 0:
            self.tp_interest.add(self.chase_tp)

    def consent_init(self, ts):
        R = self.R
        c = {
            "email_marketing": int(R.random() < (0.64 if self.channel not in ("ios_app_store", "google_play") else 0.5)),
            "email_surveys": int(R.random() < 0.48),
            "email_kids_activity": int(self.has_kids and R.random() < 0.55),
            "sms_transactional": int(self.phone and R.random() < 0.72),
            "sms_informational": 0,
            "whatsapp": int(self.phone and R.random() < 0.07),
            "marketing_matched_identifiers": int(R.random() < 0.46),
            "ccpa_do_not_sell_share": int(R.random() < (0.07 if self.state_code != "CA" else 0.16)),
            "test_participation": int(R.random() < 0.86),
        }
        c["sms_informational"] = int(c["sms_transactional"] and R.random() < 0.38)
        self.consent = c
        for k, v in c.items():
            self.w("consent_events", L(self.aid, k, v, fmt(ts), "SIGNUP"))

    def consent_change(self, k, v, ts, src):
        if self.consent.get(k) == v:
            return
        self.consent[k] = v
        self.w("consent_events", L(self.aid, k, v, fmt(ts), src))

    # ------------------------------------------------------------------ profiles & devices
    def add_profile(self, ts, kids=False, owner=False, remote=False):
        R = self.R
        k = len(self.profiles)
        if k >= 8:
            return None
        pid = 3_000_000 + self.idx * 20 + k
        if kids:
            name = R.choice(KIDS_NAMES)
            prefs = cumsum([1.0, 0.9])
            genres = KIDS_G
        else:
            name = R.choice(PROFILE_NAMES)
            alpha = [R.gammavariate(0.6, 1) for _ in ADULT_G]
            if self.typ == "movie":
                alpha[3] += 0.4
                alpha[2] += 0.3
            prefs = cumsum([a + 0.02 for a in alpha])
            genres = ADULT_G
        p = {"id": pid, "kids": kids, "name": name, "created": ts, "deleted": None, "hard_del": False,
             "genres": genres, "prefs": prefs, "auto_next": R.random() < 0.92, "auto_prev": R.random() < 0.8,
             "inprog": [], "watched": set(), "mylist": {}, "owner": owner, "remote": remote,
             "pser": min(0.95, max(0.05, R.gauss(self.tp["pser"], 0.12))),
             "w": (1.0 if owner else 0.55 if not kids else 0.75) * (0.6 if remote else 1.0),
             "lang": "es" if R.random() < 0.06 else "en", "avatar": R.randrange(1, 140),
             "maturity": "TV-Y7" if kids and R.random() < 0.4 else "TV-PG" if kids else "ALL"}
        self.profiles.append(p)
        if ts >= 0:
            self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(ts),
                                          "PROFILE_CREATED", "WEB" if R.random() < 0.3 else "TV", None, None))
        return p

    def add_device(self, ts, cat=None, remote=False, christmas=False):
        R = self.R
        k = len(self.devices)
        if k >= 39:
            return None
        if cat is None:
            cat = wchoice(R, ["TV", "STREAMING_STICK", "MOBILE", "TABLET", "WEB", "GAME_CONSOLE"],
                          cumsum([33, 30, 18, 7, 8, 4] if not self.has_kids else [30, 28, 17, 13, 7, 5]))
        cands = DM_CAT[cat]
        mi = wchoice(R, cands, cumsum([DEVICE_MODELS[i][5] for i in cands]))
        m = DEVICE_MODELS[mi]
        plat = m[1]
        lag = R.expovariate(1.0 / PLAT_LAG[plat]) if plat != "web" else 0
        if R.random() < 0.07:
            lag += R.uniform(40, 160)
        dev = {"id": 6_000_000 + self.idx * 40 + k, "mi": mi, "cat": cat, "plat": plat, "first": ts,
               "last": None, "deact": None, "lag": lag, "cap": m[9], "push": m[8] and R.random() < 0.62,
               "remote": remote, "raw": R.choice(m[3]), "os": R.choice(m[10]), "q": m[6] * math.exp(R.gauss(0, 0.1)),
               "kbps": m[7], "w": 1.0, "esn": hhash("esn", self.aid, k), "ver_first": None, "ver_last": None,
               "skew": R.gauss(0, 90) if R.random() < 0.02 else 0.0}
        if cat in BIG_SCREEN:
            dev["w"] = 2.2
        elif cat == "MOBILE":
            dev["w"] = 0.7
        elif cat == "TABLET":
            dev["w"] = 0.6
        else:
            dev["w"] = 0.5
        if remote:
            dev["w"] *= 0.9
        self.devices.append(dev)
        if ts >= 0:
            self.login(ts, dev, register=True)
        return dev

    def app_ver_idx(self, dev, d):
        lag = dev["lag"]
        v = 0
        for j, (_, rd) in enumerate(APP_RELEASES):
            if rd + lag <= d:
                v = j
        if dev["cap"] is not None:
            v = min(v, dev["cap"])
        return v

    def login(self, ts, dev, register=False, remote=None):
        R = self.R
        if ts < 0 or ts >= WIN_END:
            return
        rem = dev["remote"] if remote is None else remote
        st = self.remote_state if rem else self.travel_state(int(ts // 86400))
        ip = hhash("r", self.aid) if rem else (R.choice(self.home_ips) if dev["cat"] != "MOBILE" or R.random() < 0.5
                                              else hhash("m", self.aid, R.randrange(50)))
        if dev["cat"] in BIG_SCREEN:
            meth = "TV_CODE" if R.random() < 0.55 else "PASSWORD"
        elif dev["cat"] == "WEB":
            meth = "PASSWORD" if R.random() < 0.8 else "EMAIL_LINK"
        else:
            meth = "PASSWORD" if R.random() < 0.6 else "EMAIL_LINK" if R.random() < 0.6 else "BIOMETRIC_TOKEN"
        if register and R.random() < 0.09:
            self.w("login_events", L(self.nid("lg", 5000), self.aid, dev["id"], fmt(ts - R.randint(20, 600)),
                                     "LOGIN_FAILURE", "PASSWORD", ip, st, R.choice(["BAD_PASSWORD", "BAD_PASSWORD",
                                                                                    "UNKNOWN_EMAIL", "RATE_LIMITED"])))
        line = L(self.nid("lg", 5000), self.aid, dev["id"], fmt(ts), "LOGIN_SUCCESS", meth, ip, st, None)
        self.w("login_events", line)
        if R.random() < 0.002:
            self.w("login_events", line)  # duplicate delivery from auth service

    def cur_sub_id(self):
        return self.subs[-1]["id"] if self.subs else None

    # ------------------------------------------------------------------ payment methods
    def new_pm(self, ts, ptype=None, src="WEB"):
        R = self.R
        ptype = ptype or self.pay_pref
        k = len(self.pms)
        pm = {"id": 9_000_000 + self.idx * 30 + k, "type": ptype, "added": ts, "removed": None, "rsrc": None,
              "updated": None, "exp": None}
        if ptype == "CARD":
            yrs = R.uniform(0.6, 4.5)
            ed = min(D_MAX - 50, int(ts // 86400 + yrs * 365))
            dd = _DATES[di(ed)]
            pm["exp"] = (dd.month, dd.year)
            pm["brand"], pm["funding"] = self.card_brand, self.card_funding
        self.pms.append(pm)
        if ts >= LAUNCH_DAY * 86400:
            self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(ts),
                                          "PAYMENT_METHOD_ADDED", src, None, pm["id"]))
            if ptype in ("CARD", "PAYPAL"):
                self.w("billing_history", L(self.nid("tx", 3000), self.aid, self.cur_sub_id(), pm["id"], None,
                                            fmt(ts), "VERIFY", 1, "0.00", "USD", None, None, "approved",
                                            "AUTHORIZATIONS", None, self.gateway(pm), None))
        return pm

    def remove_pm(self, pm, ts, src):
        if pm and pm["removed"] is None:
            pm["removed"] = ts
            pm["rsrc"] = src
            self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(ts),
                                          "PAYMENT_METHOD_REMOVED", src, None, pm["id"]))

    def gateway(self, pm):
        return {"CARD": "card_gw_1", "PAYPAL": "PAYPAL", "APPLE": "APPLE_APP_STORE", "GOOGLE": "GOOGLE_PLAY",
                "ROKU": "ROKU_PAY", "AMAZON": "AMAZON_APPSTORE"}[pm["type"]]

    def pm_class(self, pm):
        return "CARD" if pm["type"] == "CARD" else "PAYPAL" if pm["type"] == "PAYPAL" else "APP_STORE"

    def card_expired(self, pm, ts):
        if pm["type"] != "CARD":
            return False
        m, y = pm["exp"]
        last = calendar.monthrange(y, m)[1]
        return ts // 86400 > day_of(date(y, m, last))

    # ------------------------------------------------------------------ billing
    def charge(self, sub, pm, ts, ptype, attempt, pstart, pend, force_ok=None, invoice=None):
        R = self.R
        cls = self.pm_class(pm)
        if force_ok is not None:
            ok = force_ok
        elif self.card_expired(pm, ts):
            ok = False
        else:
            p = {"CARD": CFG["fail_card"], "APP_STORE": CFG["fail_store"], "PAYPAL": CFG["fail_paypal"]}[cls]
            if cls == "CARD" and pm.get("funding") == "prepaid":
                p += 0.035
            elif cls == "CARD" and pm.get("funding") == "debit":
                p += 0.004
            if self.budget:
                p *= 1.6
                if DOM[di(int(ts // 86400))] >= 24:
                    p *= 1.4
            if attempt > 1:
                p = 1 - {2: 0.36, 3: 0.32, 4: 0.27}.get(attempt, 0.25) * (1.25 if DOM[di(int(ts // 86400))] in (1, 2, 15, 16) else 1.0)
            ok = R.random() >= p
        code = None
        if not ok:
            if self.card_expired(pm, ts):
                code = "EXPIRED_CARD"
            elif cls == "CARD":
                code = pick_code(R, FAIL_CODES_CARD)
            elif cls == "PAYPAL":
                code = pick_code(R, FAIL_CODES_PP)
            else:
                code = pick_code(R, FAIL_CODES_STORE)
        inv = invoice or "INV-%d-%03d" % (self.aid, self.inv_no())
        nb = fmt_date(pend) if ok else None
        self.w("billing_history", L(self.nid("tx", 3000), self.aid, sub["id"], pm["id"], inv, fmt(ts), ptype, attempt,
                                    "%.2f" % CFG["price"], "USD", fmt_date(pstart), fmt_date(pend),
                                    "approved" if ok else "declined", "COMPLETED" if ok else "DECLINED", code,
                                    self.gateway(pm), nb))
        return ok, code, inv

    # ------------------------------------------------------------------ subscriptions
    def open_sub(self, ts, signup_type, prehistory=False):
        R = self.R
        seq = len(self.subs) + 1
        sid = 1_000_000 + self.idx * 20 + len(self.subs)
        sub = {"id": sid, "seq": seq, "type": signup_type, "open": ts, "anchor": DOM[di(int(ts // 86400))],
               "k": 0, "cancel": None, "cancel_ch": None, "close": None, "vol": None, "reason": None, "pm": None}
        self.subs.append(sub)
        self.w("membership_events", L(self.nid("me", 2000), self.aid, sid, fmt(ts), "SUBSCRIPTION_STARTED",
                                      self.signup_src(), None, None))
        if seq > 1 and R.random() < 0.8:
            ptype = self.last_ptype
        else:
            ptype = self.pay_pref
        pm = self.new_pm(ts - R.randint(20, 100), ptype, src=self.signup_src())
        if not prehistory and R.random() < 0.02 and pm["type"] in ("CARD", "PAYPAL"):
            # first card declined at signup, a second one (re-entered) goes through
            self.charge(sub, pm, ts - R.randint(5, 60), "CHARGE", 1, ts, add_months(ts, 1, sub["anchor"]), force_ok=False)
            self.remove_pm(pm, ts - R.randint(1, 4), "USER_REPLACED")
            pm = self.new_pm(ts - 1, ptype, src=self.signup_src())
        sub["pm"] = pm
        sub["pm0"] = pm["id"]
        self.last_ptype = ptype
        self.charge(sub, pm, ts, "CHARGE", 1, ts, add_months(ts, 1, sub["anchor"]), force_ok=True)
        sub["next"] = add_months(ts, 1, sub["anchor"])
        self.status = ACTIVE
        self.sub = sub
        if ts >= 0:
            self.comm(ts + R.randint(30, 300), "EMAIL", "WELCOME" if seq == 1 else "WELCOME_BACK", None, transactional=True)
        return sub

    def signup_src(self):
        ch = self.channel
        return {"ios_app_store": "IOS", "google_play": "ANDROID", "smart_tv_app": "TV"}.get(ch, "WEB")

    def close_sub(self, ts, voluntary, reason):
        sub = self.sub
        sub["close"] = ts
        sub["vol"] = 1 if voluntary else 0
        sub["reason"] = reason
        self.status = LAPSED
        self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(ts), "SUBSCRIPTION_CLOSED",
                                      "SYSTEM", None, None))
        if not voluntary:
            self.remove_pm(sub["pm"], ts, "SYSTEM_DUNNING_EXHAUSTED")
        self.close_ts = ts
        self.gap_start = None
        self.chase_done = None
        self.effects = {}
        if voluntary:
            self.n_prior_vol += 1

    def cancel(self, ts, d, via_cs=False):
        R = self.R
        sub = self.sub
        pm = sub["pm"]
        if pm["type"] in ("APPLE", "GOOGLE", "ROKU", "AMAZON"):
            ch = {"APPLE": "APPLE_SUBSCRIPTIONS", "GOOGLE": "GOOGLE_PLAY", "ROKU": "ROKU", "AMAZON": "AMAZON"}[pm["type"]]
            src = "APP_STORE_NOTIFICATION"
            notify = min(ts + R.randint(5, 3600 * (6 if R.random() < 0.1 else 1)), sub["next"] - 60)
        else:
            if via_cs:
                ch = "CUSTOMER_SERVICE"
            else:
                x = R.random()
                ch = "WEB" if x < 0.56 else "IOS_APP" if x < 0.70 else "ANDROID_APP" if x < 0.80 else "TV_APP"
            src = {"WEB": "WEB", "IOS_APP": "IOS", "ANDROID_APP": "ANDROID", "TV_APP": "TV",
                   "CUSTOMER_SERVICE": "CS_AGENT"}[ch]
            notify = ts
        sub["cancel"] = notify
        sub["cancel_ch"] = ch
        self.status = PENDING
        self.cancel_day = d
        self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(notify), "CANCEL_REQUESTED",
                                      src, None, pm["id"]))
        self.remove_pm(pm, notify, "USER_CANCELLED" if src != "APP_STORE_NOTIFICATION" else "STORE_AUTO_RENEW_OFF")
        self.comm(notify + R.randint(20, 400), "EMAIL", "CANCEL_CONFIRMATION", None, transactional=True)
        self.post_cancel_mult = R.choice([0.25, 0.5, 0.7, 0.9, 1.1, 1.3])
        # some unsubscribe from marketing around cancellation
        if self.consent.get("email_marketing") and R.random() < 0.06:
            self.consent_change("email_marketing", 0, notify + R.randint(3600, 5 * 86400), "ACCOUNT_SETTINGS")
        if ch in ("WEB", "IOS_APP", "ANDROID_APP", "TV_APP") and ts >= SHORT_START:
            dev = self.pick_device_cat({"WEB": "WEB", "IOS_APP": "MOBILE", "ANDROID_APP": "MOBILE",
                                        "TV_APP": "TV"}[ch], d)
            if dev:
                asid = self.nid("as", 100000) + 8_000_000_000
                prof = self.owner_profile()
                t = ts - R.randint(40, 300)
                ver = self.app_ver_idx(dev, d)
                for j, (ev, pg) in enumerate([("app_launch", "home"), ("page_view", "account"),
                                              ("page_view", "membership_cancel"), ("click", "cancel_confirm")]):
                    self.click(asid, prof, dev, ev, pg, None, t + j * R.randint(8, 70), ver)

    def reverse_cancel(self, ts):
        R = self.R
        sub = self.sub
        pm = self.new_pm(ts, sub["pm"]["type"], src="WEB" if sub["pm"]["type"] in ("CARD", "PAYPAL") else "APP_STORE_NOTIFICATION")
        sub["pm"] = pm
        self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(ts + 2), "CANCEL_REVERSED",
                                      "WEB" if pm["type"] in ("CARD", "PAYPAL") else "APP_STORE_NOTIFICATION", None, pm["id"]))
        sub["cancel"] = None
        sub["cancel_ch"] = None
        self.status = ACTIVE
        self.post_cancel_mult = 1.0

    # ------------------------------------------------------------------ prehistory (before window)
    def prehistory(self):
        R = self.R
        cs = self.created_s
        # account exists a few minutes before the first subscription opens
        self.acct_created_s = max(LAUNCH_DAY * 86400 + 60, cs - R.randint(150, 900))
        self.consent_init(self.acct_created_s)
        self.add_profile(cs, owner=True)
        self.first_device(self.acct_created_s)
        self.extra_household(cs)
        if self.cohort == 1:
            return
        # plan prior (closed) periods arithmetically, then emit them
        periods = []
        if self.cohort == 0:
            n_prior = 0
            if self.typ == "serial":
                n_prior = R.choice([1, 1, 2, 2, 3])
            elif self.typ == "chaser":
                n_prior = R.choice([0, 1, 1, 2])
            elif R.random() < 0.11:
                n_prior = 1
            cur_open = cs
            if n_prior:
                cur_open = min(int(cs + (-cs) * R.uniform(0.35, 0.92)), -2 * 86400)
                t = cs
                for _ in range(n_prior):
                    months = 1 + min(9, int(R.expovariate(1 / 2.2)))
                    close = add_months(t, months, DOM[di(t // 86400)])
                    if close + 10 * 86400 > cur_open:
                        break
                    periods.append((t, close, True))
                    t = close + R.randint(10, 200) * 86400 + R.randint(0, 86000)
                    if t >= cur_open - 5 * 86400:
                        break
                if not periods:
                    cur_open = cs
        else:
            n_per = 1 + (R.random() < 0.3) + (self.typ == "serial" and R.random() < 0.5)
            t = cs
            for _ in range(n_per):
                months = 1 + min(10, int(R.expovariate(1 / (2.5 if self.typ in ("serial", "chaser") else 5.0))))
                anchor = DOM[di(t // 86400)]
                while months > 1 and add_months(t, months, anchor) > -15 * 86400:
                    months -= 1
                close = add_months(t, months, anchor)
                if close > -15 * 86400:
                    break
                periods.append((t, close, R.random() >= 0.1))
                t = close + 7 * 86400 + R.randint(20, 240) * 86400
                if t > -30 * 86400:
                    break
        for (o, close, vol) in periods:
            sub = self.open_sub(o, "NEW" if not self.subs else "REJOIN", prehistory=True)
            if vol:
                self.run_prewindow_renewals(sub, close)
                c = max(sub["open"] + 3600, close - R.randint(1, 27) * 86400 - R.randint(0, 86000))
                self.cancel_at_pre(c)
                self.close_sub(close, True, "MEMBER_CANCELLED")
            else:
                self.run_prewindow_renewals(sub, close)
                pend = add_months(sub["open"], sub["k"] + 2, sub["anchor"])
                inv = "INV-%d-%03d" % (self.aid, self.inv_no())
                for a, off in enumerate([0, 1, 3, 5]):
                    self.charge(sub, sub["pm"], close + off * 86400 + R.randint(0, 3600), "CHARGE" if a == 0 else "RETRY",
                                a + 1, close, pend, force_ok=False, invoice=inv)
                self.close_sub(close + 7 * 86400, False, "PAYMENT_DECLINED_GRACE_EXPIRED")
        if self.cohort == 0:
            sub = self.open_sub(cur_open, "NEW" if not self.subs else "REJOIN", prehistory=True)
            self.run_prewindow_renewals(sub, 0)
            # some incumbents already have a cancel pending on 2025-10-01
            if R.random() < 0.024 * (1.6 if self.typ in ("serial", "chaser", "casual") else 1.0):
                last_r = add_months(sub["open"], sub["k"], sub["anchor"])
                c = max(last_r + 3600, -R.randint(1, 25) * 86400 - R.randint(0, 86000))
                if c < 0 and c < sub["next"] - 3600:
                    self.cancel_at_pre(c)
        else:
            self.status = LAPSED
            self.return_day = int(self.P.rejoin_day[self.idx])
            self.winback_day = None

    def inv_no(self):
        self.n_inv = getattr(self, "n_inv", 0) + 1
        return self.n_inv

    def run_prewindow_renewals(self, sub, until):
        """Renewals before `until` and before the window start (rare failures always recover)."""
        R = self.R
        lim = min(until, 0) if until else 0
        while sub["next"] < lim:
            r = sub["next"]
            pstart, pend = r, add_months(sub["open"], sub["k"] + 2, sub["anchor"])
            inv = "INV-%d-%03d" % (self.aid, self.inv_no())
            if R.random() < 0.012:
                self.charge(sub, sub["pm"], r + R.randint(0, 1800), "CHARGE", 1, pstart, pend, force_ok=False, invoice=inv)
                self.charge(sub, sub["pm"], r + 86400 * R.choice([1, 3]) + R.randint(0, 3600), "RETRY", 2, pstart, pend,
                            force_ok=True, invoice=inv)
            else:
                self.charge(sub, sub["pm"], r + R.randint(0, 1800), "CHARGE", 1, pstart, pend, force_ok=True, invoice=inv)
            sub["k"] += 1
            sub["next"] = add_months(sub["open"], sub["k"] + 1, sub["anchor"])
        # card expiry before the window: the network account updater refreshed the card
        pm = sub["pm"]
        if pm["type"] == "CARD" and self.card_expired(pm, lim) and pm["removed"] is None:
            m, y = pm["exp"]
            pm["updated"] = (date(y, m, 1) - T0D).days * 86400 + R.randint(0, 86400 * 25)
            pm["exp"] = (R.randint(1, 12), y + R.randint(3, 4))

    def cancel_at_pre(self, c):
        sub = self.sub
        sub["cancel"] = c
        ch = "WEB" if sub["pm"]["type"] in ("CARD", "PAYPAL") else {"APPLE": "APPLE_SUBSCRIPTIONS", "GOOGLE": "GOOGLE_PLAY",
                                                                     "ROKU": "ROKU", "AMAZON": "AMAZON"}[sub["pm"]["type"]]
        sub["cancel_ch"] = ch
        self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(c), "CANCEL_REQUESTED",
                                      "WEB" if ch == "WEB" else "APP_STORE_NOTIFICATION", None, sub["pm"]["id"]))
        self.remove_pm(sub["pm"], c, "USER_CANCELLED" if ch == "WEB" else "STORE_AUTO_RENEW_OFF")
        self.status = PENDING
        self.cancel_day = int(c // 86400)
        self.post_cancel_mult = self.R.choice([0.3, 0.6, 0.9, 1.1])

    def first_device(self, ts):
        R = self.R
        ch = self.channel
        if ch in ("ios_app_store", "google_play"):
            cat = "MOBILE" if R.random() < 0.8 else "TABLET"
        elif ch == "smart_tv_app":
            cat = "TV" if R.random() < 0.5 else "STREAMING_STICK"
        else:
            cat = wchoice(R, ["WEB", "TV", "STREAMING_STICK", "MOBILE"], cumsum([45, 20, 20, 15]))
        d = self.add_device(ts, cat)
        if cat == "MOBILE" and ch == "ios_app_store":
            # app-store signups are on iOS models
            ios = [i for i in DM_CAT["MOBILE"] if DEVICE_MODELS[i][1] == "ios"]
            self._set_model(d, R.choice(ios))
        elif cat == "MOBILE" and ch == "google_play":
            andr = [i for i in DM_CAT["MOBILE"] if DEVICE_MODELS[i][1] == "android"]
            self._set_model(d, R.choice(andr))
        if self.pay_pref == "ROKU" and d["plat"] != "roku":
            self._set_model(d, R.choice([i for i, m in enumerate(DEVICE_MODELS) if m[1] == "roku"]))
        if self.pay_pref == "AMAZON" and d["plat"] != "fireos":
            self._set_model(d, R.choice([i for i, m in enumerate(DEVICE_MODELS) if m[1] == "fireos" and m[0] != "TABLET"]))
        self.signup_dev = d

    def _set_model(self, d, mi):
        m = DEVICE_MODELS[mi]
        R = self.R
        d.update({"mi": mi, "cat": m[0], "plat": m[1], "cap": m[9], "raw": R.choice(m[3]), "os": R.choice(m[10]),
                  "q": m[6] * math.exp(R.gauss(0, 0.1)), "kbps": m[7], "push": m[8] and R.random() < 0.62,
                  "w": 2.2 if m[0] in BIG_SCREEN else 0.7 if m[0] == "MOBILE" else 0.6})

    def extra_household(self, cs):
        """Additional profiles/devices: created shortly after signup or later (pre-window or in-window)."""
        R = self.R
        typ = self.typ
        n_adult = {"family": R.choice([1, 1, 2]), "adult": R.choice([0, 1, 1, 2]), "binger": R.choice([0, 1, 1]),
                   "casual": R.choice([0, 0, 1]), "chaser": R.choice([0, 0, 1]), "serial": R.choice([0, 1]),
                   "passive": R.choice([0, 0, 0, 1]), "movie": R.choice([0, 1])}[typ]
        n_kids = (R.choice([1, 1, 2]) if self.has_kids else 0)
        if self.test:
            n_adult, n_kids = R.randint(1, 4), R.randint(0, 2)
        self.pending_profiles = []
        for j in range(n_adult + n_kids):
            delay = R.expovariate(1 / 6.0) * 86400 if R.random() < 0.75 else R.uniform(10, 400) * 86400
            self.pending_profiles.append((cs + int(delay), j >= n_adult))
        if self.shared:
            self.pending_profiles.append((cs + int(R.uniform(5, 300) * 86400), "remote"))
        n_dev = {"family": R.randint(2, 5), "adult": R.randint(1, 3), "binger": R.randint(1, 4),
                 "casual": R.randint(0, 2), "chaser": R.randint(0, 2), "serial": R.randint(0, 2),
                 "passive": R.randint(0, 1), "movie": R.randint(1, 3)}[typ]
        if self.test:
            n_dev = R.randint(6, 25)
        self.pending_devices = []
        for j in range(n_dev):
            if R.random() < 0.6:
                t = cs + int(R.expovariate(1 / 12.0) * 86400)
            else:
                t = cs + int(R.uniform(15, 500) * 86400)
                # new TVs and sticks around the holidays
                if R.random() < 0.15:
                    t = (day_of(date(2025, 12, 25)) + R.randint(0, 3)) * 86400 + R.randint(40000, 80000)
            self.pending_devices.append((t, None, False))
        if self.shared:
            self.pending_devices.append((cs + int(R.uniform(5, 300) * 86400), wchoice(R, ["TV", "STREAMING_STICK", "MOBILE"], cumsum([3, 4, 3])), True))
        self.pending_profiles.sort(key=lambda x: x[0])
        self.pending_devices.sort(key=lambda x: x[0])
        self.flush_household(min(0, cs) if self.cohort == 1 else 0)

    def flush_household(self, upto, floor=None):
        # items whose planned time fell inside a lapse are created on the first day back
        while self.pending_profiles and self.pending_profiles[0][0] <= upto:
            t, kind = self.pending_profiles.pop(0)
            if floor is not None and t < floor:
                t = floor + self.R.randint(3600, 80000)
            self.add_profile(t, kids=(kind is True), remote=(kind == "remote"))
        while self.pending_devices and self.pending_devices[0][0] <= upto:
            t, cat, rem = self.pending_devices.pop(0)
            if floor is not None and t < floor:
                t = floor + self.R.randint(3600, 80000)
            self.add_device(t, cat, remote=rem)

    # ------------------------------------------------------------------ latent state
    def travel_state(self, d):
        for (s, e, m, st) in self.vac:
            if s <= d < e:
                return st
        return self.state_code

    def vac_mult(self, d):
        for (s, e, m, st) in self.vac:
            if s <= d < e:
                return m
        return 1.0

    def update_latent(self, d):
        R = self.R
        if not self.declining:
            if R.random() < (CFG["decline_onset"] if not self.test else 0):
                self.declining = True
                self.dec_target = -R.uniform(1.0, 2.3)
        elif R.random() < CFG["decline_recover"]:
            self.declining = False
            self.dec_target = 0.0
        rho = CFG["rho"]
        self.dev = rho * self.dev + (1 - rho) * self.dec_target + 0.09 * R.gauss(0, 1) + self.shock
        self.shock = 0.0

    def eff(self, name, mult, until):
        cur = self.effects.get(name)
        if cur is None or cur[1] < until or cur[0] < mult:
            self.effects[name] = (mult, until)

    def hazard(self, d):
        sub = self.sub
        tp = self.tp
        k = sub["k"]
        ten = TENURE[k] if k < 12 else (0.68 if k < 24 else 0.6)
        m = MON[di(d)]
        h = CFG["h0"] * ten * tp["hz"] * CH_HZ[self.channel] * PAY_HZ[self.pm_class(sub["pm"])] * MON_CHURN[m]
        h *= math.exp(-CFG["b_mu"] * self.mu - CFG["b_dev"] * self.dev)
        h *= (1 + 0.32 * min(self.n_prior_vol, 4))
        h *= self.use_mult
        # cycle position: right after being charged, and the days just before renewal (reminder email)
        days_left = (sub["next"] - d * 86400) / 86400.0
        since = d - (add_months(sub["open"], k, sub["anchor"]) // 86400)
        if since <= 2:
            h *= 1.55
        elif days_left <= 3.2:
            h *= 1.95 if self.consent.get("email_marketing") else 1.3
        else:
            h *= 0.85
        if self.gap_start is not None:
            g = d - self.gap_start
            h *= 1 + (3.0 if self.typ == "binger" else 1.8) * math.exp(-g / 28.0)
        if self.chase_done is None and self.chase_tp >= 0 and d > day_of(TENTPOLES[self.chase_tp][3]) + 45:
            self.chase_done = d  # drifted off the show without finishing it
        if self.gap_start is not None and d - self.gap_start > 75:
            self.gap_start = None
        if self.chase_done is not None:
            g = d - self.chase_done
            if self.typ == "chaser":
                h *= 3.0 if g < 40 else 1.9 if g < 90 else 1.25
            else:
                h *= 1.6 if g < 40 else 1.0
        elif self.typ == "chaser" and self.chase_tp >= 0:
            h *= 0.6
        nb = 0
        for (dd, n) in self.bad_log:
            if d - dd < 14:
                nb += n
        if nb:
            h *= 1 + 0.12 * min(nb, 9)
        for name, (mult, until) in list(self.effects.items()):
            if d <= until:
                h *= mult
            else:
                del self.effects[name]
        if self.budget and m == 1:
            h *= 1.5
        if self.student and (m == 5 and DOM[di(d)] >= 10 or m == 6):
            h *= 3.2
        h *= self.kappa
        h += CFG["exo"] * tp["exo"] * self.exo_mult * (1.2 if self.budget else 1.0)
        if self.test:
            h = 0.012
        return h

    # ------------------------------------------------------------------ main loop
    def run(self):
        self.setup()
        self.prehistory()
        if self.cohort == 1:
            d0 = int(self.created_s // 86400)
            self.return_day = None
            self.status = LAPSED
            self.pending_signup = self.created_s
        elif self.cohort == 2:
            d0 = 0
            self.pending_signup = None
        else:
            d0 = -1
            self.pending_signup = None
            self.return_day = None
        self.ret_ts = None
        if self.cohort == 2:
            self.ret_ts = self.return_day * 86400 + self.evening_ts_offset(self.return_day)
        for d in range(d0, WIN_DAYS):
            self.day(d)
        self.finish()

    def evening_ts_offset(self, d):
        h = pick_hour(self.R, "action")
        return int(((h - utc_off(self.tz, d)) % 24) * 3600 + self.R.randint(0, 3599))

    def day(self, d):
        R = self.R
        ds = d * 86400
        de = ds + 86400
        # signup / return
        if self.status == LAPSED:
            ts = None
            if self.pending_signup is not None and ds <= self.pending_signup < de:
                ts = self.pending_signup
                self.pending_signup = None
                self.open_sub(ts, "NEW")
                self.after_open(ts, d, first=True)
            elif self.ret_ts is not None and ds <= self.ret_ts < de:
                ts = self.ret_ts
                self.ret_ts = None
                self.open_sub(ts, "REJOIN")
                self.after_open(ts, d, first=False)
            else:
                self.lapsed_day(d)
                return
        self.flush_household(de, floor=max(ds, self.sub["open"]))
        self.update_latent(d)
        self.day_events(d)
        # cancel decision (only for subscribers that have not cancelled)
        t_cancel = None
        if self.status == ACTIVE and ds >= self.sub["open"]:
            h = self.hazard(d)
            if R.random() < h:
                t_cancel = ds + self.evening_ts_offset(d)
                if t_cancel <= self.sub["open"] + 600:
                    t_cancel = self.sub["open"] + R.randint(900, 7200)
                if t_cancel >= de or t_cancel >= WIN_END:
                    t_cancel = min(de, WIN_END) - R.randint(60, 3000)
                if t_cancel < self.last_act_end:
                    # the member cancels after the viewing already logged for last night, never in the middle of it
                    t_cancel = self.last_act_end + R.randint(60, 1800)
                if t_cancel >= WIN_END:
                    t_cancel = None
        # renewals / grace / close today, in time order with the cancel
        self.billing_day(d, t_cancel)
        if self.status == LAPSED:
            return
        if self.status == PENDING and t_cancel is None:
            p = CFG["rev_base"] * (1.6 if self.dev > 0.2 else 1.0)
            if any(abs(d - day_of(TENTPOLES[k][3])) <= 1 for k in self.tp_interest):
                p += 0.05
            if d == self.cancel_day:
                p += 0.02
            if R.random() < p:
                t = ds + self.evening_ts_offset(d)
                if self.sub["cancel"] < t < self.sub["next"] - 600:
                    self.reverse_cancel(t)
        self.activity(d)

    def after_open(self, ts, d, first):
        R = self.R
        if first:
            self.flush_household(ts)
        if self.typ == "chaser" and self.chase_tp >= 0:
            self.chase_done = None
        if not first:
            # returning users sometimes sign in on a new device
            if R.random() < 0.15:
                self.add_device(ts + R.randint(60, 7200))
            self.gap_start = None

    def lapsed_day(self, d):
        R = self.R
        ds = d * 86400
        # win-back email 2-4 weeks after access ended (email consent only)
        if getattr(self, "winback_day", None) == d:
            self.winback_day = None
            if self.consent.get("email_marketing"):
                self.comm(ds + 15 * 3600 + R.randint(0, 7200), "EMAIL", "WINBACK", "wb-%s" % DAYSTR[di(d)][:7])
        # former members occasionally open the app and hit the rejoin screen
        if ds >= SHORT_START and self.devices and R.random() < 0.012:
            dev = R.choice(self.devices)
            if dev["first"] < ds and dev["deact"] is None:
                asid = self.nid("as", 100000) + 8_000_000_000
                t = ds + self.evening_ts_offset(d)
                ver = self.app_ver_idx(dev, d)
                self.click(asid, None, dev, "app_launch", "rejoin", None, t, ver)
                self.click(asid, None, dev, "page_view", "rejoin_plan", None, t + R.randint(3, 40), ver)

    def schedule_return(self, close_ts, voluntary):
        R = self.R
        cd = int(close_ts // 86400)
        self.winback_day = cd + R.randint(14, 28) if voluntary else None
        tp = self.tp
        if self.test:
            p90, pl = 0.9, 0.05
        elif voluntary:
            p90, pl = CFG["ret90"] * tp["r90"], CFG["ret_late"] * tp["rl"]
        else:
            p90, pl = 0.42, 0.08
        if self.student and voluntary and MON[di(cd)] in (5, 6, 7):
            p90, pl = 0.15, 0.55
        x = R.random()
        delay = None
        if x < p90:
            if R.random() < 0.18:
                delay = R.uniform(0.3, 9)
            else:
                delay = 9 + 81 * R.betavariate(1.1, 1.9)
            if not voluntary:
                delay = R.uniform(0.2, 25)
        elif x < p90 + pl:
            delay = 90 + 275 * R.betavariate(1.0, 1.4)
        if delay is not None and self.typ == "chaser" and voluntary:
            # show chasers come back for the next tentpole they care about
            nxt = [day_of(t[3]) for k, t in enumerate(TENTPOLES) if day_of(t[3]) > cd + 3]
            if nxt and R.random() < 0.7:
                tgt = nxt[0] if nxt[0] - cd <= 90 or x >= p90 else None
                if tgt:
                    delay = tgt - cd + R.uniform(-1, 6)
                    self.chase_tp = [day_of(t[3]) for t in TENTPOLES].index(nxt[0])
                    self.tp_interest.add(self.chase_tp)
        if self.student and voluntary and MON[di(cd)] in (5, 6, 7) and delay is not None:
            tgt = day_of(date(2026, 8, 20)) + R.randint(0, 25)
            delay = max(5, tgt - cd)
        if delay is not None:
            rd = cd + int(delay)
            if rd < WIN_DAYS:
                self.ret_ts = rd * 86400 + self.evening_ts_offset(rd)
                if self.ret_ts <= close_ts:
                    self.ret_ts = close_ts + R.randint(3600, 20000)

    def billing_day(self, d, t_cancel):
        R = self.R
        ds, de = d * 86400, d * 86400 + 86400
        sub = self.sub
        # card expiry handling the day before renewal
        if self.status == ACTIVE and sub["pm"]["type"] == "CARD" and ds <= sub["next"] - 86400 < de:
            pm = sub["pm"]
            if self.card_expired(pm, sub["next"]):
                x = R.random()
                if x < 0.55:  # network account updater
                    pm["exp"] = (R.randint(1, 12), pm["exp"][1] + R.randint(3, 5))
                    pm["updated"] = ds + R.randint(0, 40000)
                    self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(pm["updated"]),
                                                  "PAYMENT_METHOD_UPDATED", "ACCOUNT_UPDATER", None, pm["id"]))
                elif x < 0.75:
                    t = ds + self.evening_ts_offset(d)
                    self.remove_pm(pm, t, "USER_REPLACED")
                    sub["pm"] = self.new_pm(t + 5, "CARD")
        events = []
        if t_cancel is not None:
            events.append((t_cancel, "cancel"))
        if sub["next"] < de and self.status in (ACTIVE, PENDING):
            events.append((max(sub["next"], ds), "renew"))
        if self.status == GRACE:
            for rt in self.grace["retries"]:
                if ds <= rt < de:
                    events.append((rt, "retry"))
            if ds <= self.grace["deadline"] < de:
                events.append((self.grace["deadline"], "deadline"))
            if R.random() < 0.10 * (1.5 if self.consent.get("sms_transactional") else 1.0):
                events.append((ds + self.evening_ts_offset(d), "update"))
        events.sort()
        for t, ev in events:
            if self.status == LAPSED:
                break
            if ev == "cancel":
                if self.status == ACTIVE and t < sub["next"]:
                    self.cancel(t, d, via_cs=self.cs_cancel_flag(d, t))
            elif ev == "renew":
                r = sub["next"]
                if self.status == PENDING:
                    self.close_sub(r, True, "MEMBER_CANCELLED")
                    self.schedule_return(r, True)
                    continue
                pend = add_months(sub["open"], sub["k"] + 2, sub["anchor"])
                ok, code, inv = self.charge(sub, sub["pm"], r + R.randint(0, 1800), "CHARGE", 1, r, pend)
                if ok:
                    sub["k"] += 1
                    sub["next"] = add_months(sub["open"], sub["k"] + 1, sub["anchor"])
                else:
                    self.status = GRACE
                    self.grace = {"r": r, "inv": inv, "code": code, "att": 1, "pend": pend,
                                  "retries": [r + 86400 + R.randint(0, 7200), r + 3 * 86400 + R.randint(0, 7200),
                                              r + 5 * 86400 + R.randint(0, 7200)],
                                  "deadline": r + 7 * 86400}
                    self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(r + 1801),
                                                  "GRACE_STARTED", "SYSTEM", None, sub["pm"]["id"]))
                    self.comm(r + R.randint(1900, 9000), "EMAIL", "PAYMENT_DECLINED", None, transactional=True)
                    if self.consent.get("sms_transactional"):
                        self.comm(r + R.randint(1900, 9000), "SMS", "PAYMENT_DECLINED", None, transactional=True)
                    if R.random() < 0.22:
                        self.support(r + R.randint(3600, 3 * 86400), "PAYMENT_FAILED", d)
            elif ev in ("retry", "update") and self.status == GRACE:
                g = self.grace
                g["att"] += 1
                if ev == "update":
                    if t < g["r"]:
                        continue
                    old = sub["pm"]
                    if old["type"] in ("CARD", "PAYPAL"):
                        self.remove_pm(old, t, "USER_REPLACED")
                        sub["pm"] = self.new_pm(t + 3, "CARD" if R.random() < 0.8 else "PAYPAL")
                    ok, _, _ = self.charge(sub, sub["pm"], t + 30, "CHARGE", g["att"], g["r"], g["pend"], force_ok=True,
                                           invoice=g["inv"])
                else:
                    if self.card_expired(sub["pm"], t):
                        ok, _, _ = self.charge(sub, sub["pm"], t, "RETRY", g["att"], g["r"], g["pend"], force_ok=False,
                                               invoice=g["inv"])
                    else:
                        ok, _, _ = self.charge(sub, sub["pm"], t, "RETRY", g["att"], g["r"], g["pend"], invoice=g["inv"])
                if ok:
                    self.status = ACTIVE
                    sub["k"] += 1
                    sub["next"] = add_months(sub["open"], sub["k"] + 1, sub["anchor"])
                    self.w("membership_events", L(self.nid("me", 2000), self.aid, sub["id"], fmt(t + 31),
                                                  "GRACE_RESOLVED", "SYSTEM", None, sub["pm"]["id"]))
                    self.eff("payfail", 1.6, d + 45)
            elif ev == "deadline" and self.status == GRACE:
                self.close_sub(t, False, "PAYMENT_DECLINED_GRACE_EXPIRED")
                self.schedule_return(t, False)
        # renewal reminder ~3 days before renewal (email consent only)
        if self.status == ACTIVE and self.consent.get("email_marketing"):
            if ds <= sub["next"] - 3 * 86400 < de:
                self.comm(ds + 16 * 3600 + R.randint(0, 5400), "EMAIL", "RENEWAL_REMINDER", "rr-std-v2")
        if self.status == ACTIVE and sub["pm"]["type"] == "CARD":
            m, y = sub["pm"]["exp"]
            if d == day_of(date(y, m, 1)) + 5:
                self.comm(ds + 15 * 3600, "EMAIL", "PAYMENT_METHOD_EXPIRING", None, transactional=True)

    def cs_cancel_flag(self, d, t):
        R = self.R
        if R.random() < 0.035:
            self.support(t - R.randint(300, 1800), "CANCEL_HELP", d, force_res="RESOLVED")
            return True
        return False

    # ------------------------------------------------------------------ daily non-viewing events
    def day_events(self, d):
        R = self.R
        ds = d * 86400
        # household change
        if self.hh_change and self.hh_change[0] == d:
            kind = self.hh_change[1]
            if kind == "move":
                self.eff("hh", 2.1, d + 45)
                self.shock -= 0.25
                self.home_ips = [hhash("ip2", self.aid, k) for k in range(3)]
                if R.random() < 0.5:
                    self.add_device(ds + R.randint(36000, 80000), R.choice(["TV", "STREAMING_STICK"]))
                if R.random() < 0.3 and self.devices:
                    old = self.devices[0]
                    if old["deact"] is None:
                        old["deact"] = ds + R.randint(0, 80000)
            elif kind == "split":
                self.eff("hh", 2.6, d + 60)
                self.shock -= 0.35
                cands = [p for p in self.profiles if not p["owner"] and p["deleted"] is None and not p["kids"]]
                if cands:
                    p = R.choice(cands)
                    p["deleted"] = ds + R.randint(30000, 85000)
                    p["hard_del"] = R.random() < 0.25
                    self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(p["deleted"]),
                                                  "PROFILE_DELETED", "WEB", None, None))
            else:
                self.eff("hh", 1.3, d + 90)
                self.baby_until = d + 90
        # random profile deletion / device retirement
        if R.random() < 0.00006:
            cands = [p for p in self.profiles if not p["owner"] and p["deleted"] is None]
            if cands:
                p = R.choice(cands)
                p["deleted"] = ds + R.randint(0, 86000)
                self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(p["deleted"]),
                                              "PROFILE_DELETED", "WEB", None, None))
        if R.random() < 0.0009 and len(self.devices) > 1:
            dv = R.choice(self.devices)
            if dv["deact"] is None and dv["first"] < ds:
                dv["deact"] = ds + R.randint(0, 86000)
                self.w("login_events", L(self.nid("lg", 5000), self.aid, dv["id"], fmt(dv["deact"]), "LOGOUT",
                                         None, R.choice(self.home_ips), self.state_code, None))
        if R.random() < 0.0012 and ds >= 0:
            self.add_device(ds + self.evening_ts_offset(d))
        # password resets / re-auth
        if R.random() < 0.0005:
            t = ds + self.evening_ts_offset(d)
            self.w("login_events", L(self.nid("lg", 5000), self.aid, None, fmt(t), "PASSWORD_RESET_REQUEST", "EMAIL_LINK",
                                     R.choice(self.home_ips), self.state_code, None))
            if R.random() < 0.8:
                self.w("login_events", L(self.nid("lg", 5000), self.aid, None, fmt(t + R.randint(60, 1800)),
                                         "PASSWORD_RESET_COMPLETE", "EMAIL_LINK", R.choice(self.home_ips), self.state_code, None))
                self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(t + 1900),
                                              "PASSWORD_CHANGED", "WEB", None, None))
            elif R.random() < 0.5:
                self.support(t + R.randint(1800, 86400), "LOGIN_PASSWORD", d)
        if R.random() < 0.012:
            webs = [x for x in self.devices if x["cat"] in ("WEB", "MOBILE") and x["deact"] is None and x["first"] < ds]
            if webs:
                self.login(ds + self.evening_ts_offset(d), R.choice(webs))
        if R.random() < 0.00012:
            self.w("membership_events", L(self.nid("me", 2000), self.aid, self.cur_sub_id(), fmt(ds + self.evening_ts_offset(d)),
                                          "EMAIL_CHANGED", "WEB", None, None))
        # spontaneous support contacts
        if R.random() < 0.0009 * (2.0 if self.test else 1.0):
            reason = wchoice(R, ["BILLING_QUESTION", "DEVICE_ACTIVATION", "CONTENT_AVAILABILITY", "ACCOUNT_SHARING",
                                 "APP_BUG", "OTHER", "REFUND_REQUEST"], cumsum([25, 18, 14, 6, 10, 20, 7]))
            self.support(ds + self.evening_ts_offset(d), reason, d)
        # charged then complained ("I forgot to cancel") right after a renewal
        if self.status == ACTIVE:
            since = d - (add_months(self.sub["open"], self.sub["k"], self.sub["anchor"]) // 86400)
            if since in (0, 1) and self.sub["k"] > 0 and R.random() < 0.0045 * (1.8 if self.dev < -0.4 else 1.0):
                self.support(ds + self.evening_ts_offset(d), "REFUND_REQUEST", d, force_res="UNRESOLVED")
                self.eff("refund", 4.0, d + 4)
        # tentpole release day
        for k in self.tp_interest:
            if d == day_of(TENTPOLES[k][3]):
                self.shock += 0.18
        # marketing comms
        self.marketing(d)

    def marketing(self, d):
        R = self.R
        ds = d * 86400
        if self.status not in (ACTIVE, PENDING, GRACE):
            return
        # monthly "New on Jetflix" digest on the first Thursday
        if DOW[di(d)] == 3 and DOM[di(d)] <= 7 and self.consent.get("email_marketing"):
            self.comm(ds + 14 * 3600 + R.randint(0, 3 * 3600), "EMAIL", "NEW_ON_JETFLIX_DIGEST", "dg-%s" % DAYSTR[di(d)])
        for k, tpl in enumerate(TENTPOLES):
            if d == day_of(tpl[3]):
                camp = "tp-%02d-%s" % (k + 1, DAYSTR[di(d)])
                if self.consent.get("email_marketing"):
                    self.comm(ds + 13 * 3600 + R.randint(0, 7200), "EMAIL", "NEW_RELEASE", camp, interest=k in self.tp_interest)
                if self.consent.get("sms_informational") and TP_STRENGTH[k] >= 0.7:
                    self.comm(ds + 17 * 3600 + R.randint(0, 3600), "SMS", "NEW_RELEASE", camp, interest=k in self.tp_interest)
                for dv in (self.devices if TP_STRENGTH[k] >= 0.7 else ()):
                    if dv["push"] and dv["deact"] is None and dv["first"] < ds and not dv["remote"]:
                        self.comm(ds + 18 * 3600 + R.randint(0, 3600), "PUSH", "NEW_RELEASE", camp, device=dv,
                                  interest=k in self.tp_interest)

    def comm(self, ts, channel, mtype, campaign, transactional=False, device=None, interest=False):
        R = self.R
        if ts < 0 or ts >= WIN_END:
            return
        bounce = None
        delivered = ts + R.randint(2, 240)
        if channel == "EMAIL" and R.random() < 0.012:
            bounce = "SOFT" if R.random() < 0.7 else "HARD"
            delivered = None
        if channel == "PUSH" and R.random() < 0.08:
            delivered = None
            bounce = "TOKEN_INVALID"
        opened = clicked = unsub = None
        if delivered is not None and channel in ("EMAIL", "PUSH"):
            eng = 1 / (1 + math.exp(-(self.mu + self.dev) * 1.4))
            base = {"WELCOME": 0.62, "WELCOME_BACK": 0.55, "RENEWAL_REMINDER": 0.26, "PAYMENT_DECLINED": 0.58,
                    "CANCEL_CONFIRMATION": 0.48, "WINBACK": 0.16, "NEW_ON_JETFLIX_DIGEST": 0.15, "NEW_RELEASE": 0.21,
                    "PAYMENT_METHOD_EXPIRING": 0.41}.get(mtype, 0.2)
            if channel == "PUSH":
                base = 0.07
            p = base * (0.6 + 0.8 * eng) * (1.8 if interest else 1.0)
            if channel == "EMAIL" and self.apple_mpp and R.random() < 0.85:
                opened = delivered + R.randint(1, 900)  # privacy-protection prefetch "open"
            elif R.random() < min(0.95, p):
                opened = delivered + int(R.expovariate(1 / 14000.0))
            if opened is not None:
                pc = (0.05 + 0.1 * eng) * (3.0 if interest else 1.0)
                if channel == "PUSH":
                    pc = 0.7
                if R.random() < pc and (not self.apple_mpp or R.random() < 0.5):
                    clicked = opened + R.randint(2, 600)
                if channel == "EMAIL" and not transactional and R.random() < 0.0015 * (5 if self.status == PENDING else 1):
                    unsub = opened + R.randint(5, 300)
                    self.consent_change("email_marketing", 0, unsub, "EMAIL_UNSUBSCRIBE_LINK")
        if channel == "SMS" and R.random() < 0.004 and not transactional:
            unsub = delivered + R.randint(60, 7200) if delivered else None
            if unsub:
                self.consent_change("sms_informational", 0, unsub, "SMS_STOP")
        self.w("communications_log", L(self.nid("cm", 5000), self.aid, channel, mtype, campaign,
                                       "v%d" % (1 + (ts > 150 * 86400)) if not transactional else "t1", fmt(ts),
                                       fmt(delivered) if delivered else None, bounce,
                                       fmt(opened) if opened else None, fmt(clicked) if clicked else None,
                                       fmt(unsub) if unsub else None, device["id"] if device else None))

    def support(self, ts, reason, d, force_res=None, device=None):
        R = self.R
        if ts < 0 or ts >= WIN_END:
            return
        ch = wchoice(R, ["CHAT", "PHONE", "EMAIL", "SOCIAL"], cumsum([52, 30, 14, 4]))
        res = force_res or R.choice(SUPPORT_RES)
        if reason == "PLAYBACK_ISSUE" and R.random() < 0.35:
            res = "RESOLVED_WORKAROUND"
        ht = int(R.lognormvariate(math.log(420 if ch == "CHAT" else 540 if ch == "PHONE" else 600), 0.6)) if ch != "EMAIL" else -1
        csat = R.choice([1, 2, 3, 4, 5, 5, 4]) if R.random() < 0.28 else None
        if csat and res in ("UNRESOLVED", "CUSTOMER_ABANDONED"):
            csat = R.choice([1, 1, 2, 3])
        tier = "TIER2" if res == "ESCALATED" else "BILLING" if reason in ("BILLING_QUESTION", "PAYMENT_FAILED", "REFUND_REQUEST") else "TIER1"
        self.w("support_contacts", L(self.nid("sc", 1000), self.aid, fmt(ts), ch, reason, res, ht, csat, tier,
                                     device["id"] if device else None))
        if res in ("UNRESOLVED", "CUSTOMER_ABANDONED", "ESCALATED"):
            self.eff("support", 2.6 if res != "ESCALATED" else 1.8, d + 30)
            self.shock -= 0.12
        else:
            self.eff("support_ok", 1.12, d + 30)

    # ------------------------------------------------------------------ viewing
    def owner_profile(self):
        for p in self.profiles:
            if p["owner"]:
                return p
        return self.profiles[0]

    def live_profiles(self, ts):
        return [p for p in self.profiles if p["created"] <= ts and (p["deleted"] is None or p["deleted"] > ts)]

    def live_devices(self, ts, remote=False):
        return [x for x in self.devices if x["first"] <= ts and (x["deact"] is None or x["deact"] > ts) and x["remote"] == remote]

    def pick_device_cat(self, cat, d):
        ds = d * 86400
        c = [x for x in self.devices if x["first"] <= ds and x["deact"] is None and
             (x["cat"] == cat or (cat == "TV" and x["cat"] in BIG_SCREEN))]
        if not c:
            c = [x for x in self.devices if x["first"] <= ds and x["deact"] is None]
        return self.R.choice(c) if c else None

    def access_end(self):
        if self.status == PENDING:
            return self.sub["next"]
        if self.status == GRACE:
            return self.grace["deadline"]
        return 10 ** 12

    def activity(self, d):
        R = self.R
        ds = d * 86400
        sub = self.sub
        acc_from = sub["open"]
        acc_to = min(self.access_end(), WIN_END)
        dw = DOW[di(d)]
        hol = HOL.get(d)
        rate = self.Rb * DOW_VIEW[dw] * MON_VIEW[MON[di(d)]] * HOL_VIEW.get(hol, 1.0)
        vm = self.vac_mult(d)
        rate *= vm
        rate *= math.exp(CFG["a_mu"] * self.mu + CFG["a_dev"] * self.dev)
        if self.gap_start is not None:
            rate *= 0.72
        if self.status == PENDING:
            rate *= self.post_cancel_mult
        if getattr(self, "baby_until", -1) >= d:
            rate *= 0.6
        focus = None
        for k in self.tp_interest:
            r = day_of(TENTPOLES[k][3])
            if r <= d <= r + 24:
                focus = k
                rate *= 1.35 if k != self.chase_tp else 1.9
                break
        if self.typ == "chaser" and self.chase_tp >= 0 and self.chase_done is None:
            focus = self.chase_tp
            rate *= 1.4
        if self.test:
            rate = 0.6
        weekend = dw >= 5 or hol in ("thanksgiving", "christmas", "new_year", "memorial", "july4", "labor")
        n = poisson(R, rate)
        n_bad = 0
        # browse-only app sessions (no playback)
        nb = poisson(R, rate * (0.15 if self.gap_start is None else 0.4) + 0.006)
        profs = self.live_profiles(ds + 43200)
        if not profs:
            return
        pw = cumsum([p["w"] * (1.0 if not p["kids"] else (1.4 if weekend else 1.0)) for p in profs])
        for _ in range(n):
            prof = wchoice(R, profs, pw)
            n_bad += self.sitting(d, prof, acc_from, acc_to, weekend, vm < 1.0, focus)
        for _ in range(nb):
            prof = wchoice(R, profs, pw)
            self.browse(d, prof, acc_from, acc_to, weekend)
        if n_bad:
            self.bad_log.append((d, n_bad))
            self.shock -= 0.045 * n_bad
        if len(self.bad_log) > 30:
            self.bad_log = self.bad_log[-20:]

    def sitting_start(self, d, prof, weekend, dev_cat):
        R = self.R
        if prof["kids"]:
            key = "kids_we" if weekend else "kids_wd"
        elif dev_cat in ("MOBILE", "TABLET"):
            key = "mobile"
        else:
            key = "adult_we" if weekend else "adult_wd"
        shift = 10 if (self.night_shift and not prof["kids"]) else 0
        h = pick_hour(R, key, shift)
        tz = self.tz
        return d * 86400 + int((h - utc_off(tz, d)) * 3600) + R.randint(0, 3599), h

    def choose_device(self, prof, ts, travelling):
        R = self.R
        devs = self.live_devices(ts, remote=prof["remote"])
        if not devs:
            devs = self.live_devices(ts, remote=not prof["remote"])
        if not devs:
            return None
        ws = []
        for x in devs:
            w = x["w"]
            if travelling:
                w *= 4.0 if x["cat"] in ("MOBILE", "TABLET") else 0.05
            if prof["kids"] and x["cat"] == "TABLET":
                w *= 3.0
            ws.append(w)
        return wchoice(R, devs, cumsum(ws))

    def browse(self, d, prof, acc_from, acc_to, weekend):
        R = self.R
        ts0 = d * 86400 + 43200
        dev = self.choose_device(prof, ts0, False)
        if dev is None:
            return
        ts, h = self.sitting_start(d, prof, weekend, dev["cat"])
        if ts < max(acc_from, 0) or ts >= acc_to or dev["first"] > ts or prof["created"] > ts:
            return
        ver = self.app_ver_idx(dev, d)
        asid = self.nid("as", 100000) + 8_000_000_000
        t = ts
        if ts >= SHORT_START:
            self.click(asid, prof, dev, "app_launch", "home", None, t, ver)
        n = 1 + poisson(R, 1.4)
        for j in range(n):
            t += R.randint(10, 120)
            ti = self.sample_title(prof, d)
            if ti is None:
                continue
            if ts >= SHORT_START:
                self.click(asid, prof, dev, "page_view", "title_detail", self.cat.T[ti]["id"], t, ver)
            if R.random() < 0.08:
                self.add_mylist(prof, ti, t + 3, "title_detail")
                if ts >= SHORT_START:
                    self.click(asid, prof, dev, "click", "add_to_my_list", self.cat.T[ti]["id"], t + 3, ver)
        if R.random() < 0.25:
            self.search(d, prof, dev, t + R.randint(5, 60), asid, ver, None)

    def sitting(self, d, prof, acc_from, acc_to, weekend, travelling, focus):
        R = self.R
        cat = self.cat
        dev = self.choose_device(prof, d * 86400 + 43200, travelling)
        if dev is None:
            return 0
        ts, lh = self.sitting_start(d, prof, weekend, dev["cat"])
        if ts < max(acc_from, 0) or ts >= acc_to or dev["first"] > ts or prof["created"] > ts:
            return 0
        ver = self.app_ver_idx(dev, d)
        if dev["ver_first"] is None:
            dev["ver_first"] = ver
        dev["ver_last"] = ver
        asid = self.nid("as", 100000) + 8_000_000_000
        short = ts >= SHORT_START
        t = ts
        if short:
            self.click(asid, prof, dev, "app_launch", "home", None, t, ver)
            if len(self.profiles) > 1:
                t += R.randint(3, 25)
                self.click(asid, prof, dev, "click", "profile_select", None, t, ver)
            t += R.randint(4, 60)
        # autoplaying preview on big screens
        if dev["cat"] in BIG_SCREEN and prof["auto_prev"] and R.random() < 0.22:
            ti = self.sample_title(prof, d)
            dur = R.randint(5, 75)
            if ti is not None and t + dur < min(acc_to, WIN_END):
                self.view_row(prof, dev, t, dur, ti, None, "HOOK", "Autoplayed: user action: None; ", dur, asid, ver, d, False)
                t += dur + R.randint(2, 30)
        # choose what to watch
        item = None
        if focus is not None and R.random() < (0.85 if focus == self.chase_tp else 0.55) and not prof["kids"]:
            ti = cat.tentpole_idx[focus]
            item = self.item_for(prof, ti, d)
        if item is None:
            ip = [x for x in prof["inprog"] if self.next_available(x, d)]
            if ip and R.random() < (0.72 if not prof["kids"] else 0.6):
                item = ip[-1] if R.random() < 0.7 else R.choice(ip)
            else:
                via_search = R.random() < (0.07 if dev["cat"] in BIG_SCREEN else 0.14)
                ti = None
                if via_search:
                    ti = self.search(d, prof, dev, t, asid, ver, "play")
                    t += R.randint(8, 50)
                if ti is None:
                    if prof["mylist"] and R.random() < 0.35:
                        ti = R.choice(list(prof["mylist"].keys()))
                        if not cat.available(ti, d):
                            ti = None
                    if ti is None:
                        ti = self.sample_title(prof, d)
                if ti is None:
                    return 0
                item = self.item_for(prof, ti, d)
                if item is None:
                    return 0
                if short and R.random() < 0.55:
                    self.click(asid, prof, dev, "page_view", "title_detail", cat.T[ti]["id"], t, ver)
                    t += R.randint(4, 40)
                    dur = R.randint(20, 150)
                    if R.random() < 0.06 and t + dur < min(acc_to, WIN_END):
                        self.view_row(prof, dev, t, dur, ti, None, "TRAILER", None, dur, asid, ver, d, False)
                        t += dur + 3
        if short:
            self.click(asid, prof, dev, "click", "play", cat.T[item["ti"]]["id"], t, ver)
        t += R.randint(1, 4)
        # binge loop
        n_bad = 0
        leave_on = dev["cat"] in BIG_SCREEN and R.random() < 1 / 3500.0
        binge = self.binge * (1.15 if weekend else 1.0) * (0.75 if lh in (23, 0, 1) else 1.0) * min(1.25, math.exp(0.35 * self.dev))
        n_eps = 0
        autoplayed = False
        while True:
            if t >= acc_to or t >= WIN_END:
                break
            res = self.play(d, prof, dev, item, t, asid, ver, autoplayed, acc_to, leave_on)
            if res is None:
                break
            t_end, completed, bad = res
            n_bad += bad
            n_eps += 1
            t = t_end
            if not completed:
                break
            nxt = self.advance(prof, item, d)
            if nxt is None:
                break
            item = nxt
            if leave_on and n_eps < 40 and t - ts < 12 * 3600:
                autoplayed = True
                t += R.randint(5, 15)
                continue
            if R.random() < binge and n_eps < 9:
                autoplayed = prof["auto_next"] and R.random() < 0.85
                t += R.randint(5, 15) if autoplayed else R.randint(15, 600)
                continue
            break
        return n_bad

    def item_for(self, prof, ti, d):
        cat = self.cat
        t = cat.T[ti]
        for x in prof["inprog"]:
            if x["ti"] == ti:
                return x if self.next_available(x, d) else None
        if t["nep"]:
            start = 0
            # returning fans of an older series jump straight to the newest season
            if ti in cat.tentpole_idx and t["tp"][1] > 0:
                seasons = [cat.ep_season[j] for j in range(t["ep0"], t["ep0"] + t["nep"])]
                last_s = max(seasons)
                if self.R.random() < 0.7:
                    start = seasons.index(last_s)
            elif ti in prof["watched"]:
                return None
            item = {"ti": ti, "pos": start, "bm": 0}
            if not self.next_available(item, d):
                return None
        else:
            if ti in prof["watched"] and self.R.random() < 0.9:
                return None
            item = {"ti": ti, "pos": 0, "bm": 0}
        prof["inprog"].append(item)
        if self.gap_start is not None and not prof["kids"] and self.R.random() < 0.5:
            self.gap_start = None  # found something new to watch
        if len(prof["inprog"]) > 12:
            prof["inprog"].pop(0)
        return item

    def next_available(self, item, d):
        cat = self.cat
        t = cat.T[item["ti"]]
        if not cat.available(item["ti"], d):
            return False
        if t["nep"]:
            if item["pos"] >= t["nep"]:
                return False
            return cat.ep_rel[t["ep0"] + item["pos"]] <= d
        return True

    def advance(self, prof, item, d):
        """Item completed: move to next episode or finish the title."""
        cat = self.cat
        t = cat.T[item["ti"]]
        item["bm"] = 0
        if t["nep"]:
            item["pos"] += 1
            if item["pos"] < t["nep"]:
                if cat.ep_rel[t["ep0"] + item["pos"]] <= d:
                    return item
                return None  # next episode not released yet (weekly)
        self.finish_title(prof, item, d)
        return None

    def finish_title(self, prof, item, d):
        R = self.R
        ti = item["ti"]
        if item in prof["inprog"]:
            prof["inprog"].remove(item)
        prof["watched"].add(ti)
        if ti in prof["mylist"] and prof["mylist"][ti][1] is None and R.random() < 0.3:
            prof["mylist"][ti][1] = d * 86400 + R.randint(0, 86000)
        # rating
        if R.random() < 0.13:
            v = 3 if R.random() < 0.22 else 1 if R.random() < 0.16 + (0.2 if self.dev < -0.5 else 0) else 2
            ts = d * 86400 + R.randint(0, 86000)
            if 0 <= ts < WIN_END:
                pid = prof["id"]
                self.w("ratings", L(self.nid("rt", 5000), self.aid, pid, self.cat.T[ti]["id"], "thumb", v,
                                    self.devices[0]["id"] if self.devices else None, fmt(ts)))
        # chased tentpole finished
        if self.chase_tp >= 0 and ti == self.cat.tentpole_idx[self.chase_tp] and self.chase_done is None:
            self.chase_done = d
        # content gap: main viewer finished a series and has nothing queued
        if not prof["kids"] and self.cat.T[ti]["nep"]:
            others = [x for x in prof["inprog"] if self.next_available(x, d)]
            queued = [k for k, v in prof["mylist"].items() if v[1] is None and k not in prof["watched"]]
            if not others and not queued:
                if self.gap_start is None:
                    self.gap_start = d
                    self.shock -= 0.12

    def sample_title(self, prof, d):
        R = self.R
        cat = self.cat
        for _ in range(6):
            if prof["kids"]:
                idx, cum = cat.kids_all if R.random() < 0.5 else cat.by_genre[wchoice(R, prof["genres"], prof["prefs"])]
            elif R.random() < 0.22:
                lo = bisect.bisect_left(cat.new_days, d - 45)
                hi = bisect.bisect_right(cat.new_days, d)
                if hi - lo < 3:
                    continue
                base = cat.new_cum[lo - 1] if lo > 0 else 0.0
                x = base + R.random() * (cat.new_cum[hi - 1] - base)
                ti = cat.new_order[min(hi - 1, bisect.bisect_left(cat.new_cum, x))]
                if cat.T[ti]["kids"] and R.random() < 0.85:
                    continue
                if cat.available(ti, d):
                    return ti
                continue
            else:
                g = wchoice(R, prof["genres"], prof["prefs"])
                idx, cum = cat.by_genre[g]
            if not idx:
                continue
            ti = idx[bisect.bisect_left(cum, R.random() * cum[-1])]
            t = cat.T[ti]
            if not prof["kids"] and t["kids"] and R.random() < 0.9:
                continue
            if prof["kids"] and not t["kids"]:
                continue
            if not cat.available(ti, d):
                continue
            series = t["nep"] > 0
            if series != (R.random() < prof["pser"]) and R.random() < 0.6:
                continue
            return ti
        return None

    def add_mylist(self, prof, ti, ts, src):
        if ti in prof["mylist"] or ts < 0:
            return
        prof["mylist"][ti] = [ts, None, src]
        if self.gap_start is not None and not prof["kids"]:
            self.gap_start = None

    def search(self, d, prof, dev, ts, asid, ver, intent):
        R = self.R
        cat = self.cat
        if ts < 0 or ts >= WIN_END:
            return None
        x = R.random()
        ti = None
        disp = None
        if x < 0.06 and not prof["kids"]:
            q = R.choice(NOT_ON_SERVICE_QUERIES)
            action = "none"
            sec = "search_results"
        elif x < 0.16:
            q = R.choice(GENRE_QUERIES) if not prof["kids"] else R.choice(["kids", "cartoons", "dino", "puppy", "princess"])
            ti = self.sample_title(prof, d)
            disp = cat.T[ti]["id"] if ti is not None else None
            action = "view_details" if R.random() < 0.6 else "none"
            sec = "suggested"
        else:
            ti = self.sample_title(prof, d)
            if ti is None:
                return None
            name = cat.T[ti]["name"].lower()
            q = name[:R.randint(2, min(12, len(name)))]
            if R.random() < 0.08 and len(q) > 3:
                j = R.randrange(1, len(q) - 1)
                q = q[:j] + q[j + 1] + q[j] + q[j + 2:]
            q = q.strip() or name[:3]
            disp = cat.T[ti]["id"]
            action = intent or R.choice(["view_details", "view_details", "play", "add_to_my_list", "none"])
            sec = "search_results" if R.random() < 0.85 else "top_searches"
            if dev["cat"] in BIG_SCREEN and R.random() < 0.08:
                sec = "voice"
        if action == "add_to_my_list" and ti is not None:
            self.add_mylist(prof, ti, ts + 4, "search")
        self.w("search_history", L(self.nid("sr", 50000), self.aid, prof["id"], dev["id"], int(prof["kids"]), fmt(ts),
                                   q, disp, action, sec))
        if ts >= SHORT_START:
            self.click(asid, prof, dev, "page_view", "search", None, ts - 2, ver)
            self.click(asid, prof, dev, "search_submit", "search", disp, ts, ver)
        return ti if action == "play" else None

    def quality(self, dev, ver, d, lh):
        q = dev["q"] * (self.bb if not dev["remote"] else 1.05)
        plat = dev["plat"]
        inc = 1.0
        if APP_RELEASES[ver][0] == "9.1.0" and plat in ("fireos", "androidtv"):
            inc = 1.7
        if APP_RELEASES[ver][0] == "9.3.0" and plat == "roku":
            inc = 1.6
        if 19 <= lh <= 23:
            q *= 1.12
        return q, inc

    def play(self, d, prof, dev, item, t, asid, ver, autoplayed, acc_to, leave_on):
        """One view. Returns (end_ts, completed, bad) or None if the playback never started."""
        R = self.R
        cat = self.cat
        T = cat.T[item["ti"]]
        lh = (int((t % 86400) / 3600) + utc_off(self.tz, d)) % 24
        q, inc = self.quality(dev, ver, d, lh)
        cell = dev["cat"] == "MOBILE" and R.random() < 0.35
        if cell:
            q *= 1.35
        travelling = self.vac_mult(d) < 1.0
        offline = dev["cat"] in ("MOBILE", "TABLET") and (travelling and R.random() < 0.45 or R.random() < 0.03)
        if offline:
            q = 0.6
        startup = int(620 * q ** 1.1 * R.lognormvariate(0, 0.42) * (1.5 if inc > 1 and dev["plat"] == "roku" else 1.0))
        err_p = 0.0022 * q ** 2.2 * (4.0 if inc > 1 and dev["plat"] != "roku" else 1.0)
        if offline:
            err_p = 0.0005
        ebvs = R.random() < err_p or (startup > 7000 and R.random() < 0.45) or R.random() < 0.003
        ep = T["ep0"] + item["pos"] if T["nep"] else None
        L_rt = cat.ep_rt[ep] if ep is not None else T["rt"]
        if ebvs:
            if t >= SHORT_START:
                err = R.choice(ERROR_CODES) if R.random() < 0.6 else None
                self.qrow(None, dev, T["id"], t, ver, cell, offline, -1 if err else startup, 0, 0, 0, 0, err, 1)
            if R.random() < 0.08:
                self.support(t + R.randint(600, 20000), "PLAYBACK_ISSUE", d, device=dev)
            return None
        b0 = item["bm"]
        remaining = max(30, L_rt - b0)
        x = R.random()
        ab_p = 0.06 + 0.12 * max(0, q - 1.2) + (0.06 if item["pos"] == 0 and b0 == 0 else 0) + max(0.0, -0.07 * self.dev)
        if x < ab_p:
            watched = R.randint(20, 300)
            completed = False
        elif x < ab_p + 0.21:
            watched = int(remaining * R.uniform(0.12, 0.9))
            completed = False
        else:
            credits = R.randint(0, 120) if T["nep"] else R.randint(0, 300)
            watched = max(30, remaining - credits)
            completed = True
        if leave_on:
            completed = True
            watched = max(30, remaining - R.randint(0, 40))
        stuck = dev["cat"] in BIG_SCREEN and R.random() < 1 / 20000.0
        if stuck:
            # player never sent a stop (TV switched off at the wall / input changed): session logged for hours
            watched = int(R.uniform(3, 12.5) * 3600)
            completed = False
        # rebuffering
        rb_rate = 0.11 * q ** 2.6 * (1.5 if inc > 1 else 1.0)
        n_rb = poisson(R, rb_rate * watched / 3600.0 * 4)
        rb_ms = sum(int(R.lognormvariate(math.log(1800 * q), 0.7)) for _ in range(n_rb))
        mid_err = R.random() < err_p * 0.6
        if mid_err:
            watched = max(20, int(watched * R.uniform(0.05, 0.9)))
            completed = False
        wall_pause = 0
        n_pause = poisson(R, watched / 3600.0 * (1.4 if dev["cat"] in ("MOBILE", "TABLET") else 1.0))
        pauses = []
        for _ in range(n_pause):
            pl = int(R.lognormvariate(math.log(110), 1.1))
            pauses.append((R.uniform(0.05, 0.95), min(pl, 5400)))
            wall_pause += min(pl, 5400)
        wall = watched + wall_pause + rb_ms // 1000 + startup // 1000
        if t + wall > acc_to:
            watched = max(1, int(acc_to - t - wall_pause - startup // 1000 - rb_ms // 1000 - 1))
            if watched <= 1:
                return None
            completed = False
            wall = acc_to - t - 1
        if t + wall >= WIN_END:
            watched = max(1, int(WIN_END - t - wall_pause - 2))
            wall = WIN_END - t - 1
            completed = False
        bm_end = b0 + watched if not completed else L_rt
        if stuck:
            bm_end = L_rt
        if completed:
            item["bm"] = 0
        else:
            item["bm"] = min(L_rt - 30, b0 + watched)
        bad = int(mid_err or (watched > 60 and rb_ms / 1000.0 / max(watched, 1) > 0.02) or startup > 6000)
        attrs = None
        if autoplayed:
            attrs = "Autoplayed: user action: None; " if R.random() < 0.8 else "Autoplayed: user action: Unspecified; "
        elif dev["cat"] == "WEB" and R.random() < 0.05:
            attrs = "Autoplayed: user action: User_Interaction; "
        if T["branched"]:
            attrs = (attrs or "") + "Has branched playback; "
        if R.random() < 0.003:
            attrs = (attrs or "") + "View was hidden; "
        vid = self.view_row(prof, dev, t, watched, item["ti"], ep, None, attrs, bm_end, asid, ver, d, offline)
        self.last_act_end = max(self.last_act_end, t + wall)
        if t >= SHORT_START:
            self.playtrace(vid, prof, t, startup, b0, watched, pauses, offline, dev, T["nep"] > 0 and item["pos"] > 0)
            pbr = int(dev["kbps"] / q ** 0.8 * R.lognormvariate(0, 0.12))
            pbr = min(pbr, dev["kbps"])
            if cell:
                pbr = min(pbr, 1800)
            self.qrow(vid, dev, T["id"], t, ver, cell, offline, startup, n_rb, rb_ms, watched * 1000, pbr,
                      R.choice(ERROR_CODES) if mid_err else None, 0)
        if bad and R.random() < 0.015:
            self.support(t + wall + R.randint(60, 7200), "PLAYBACK_ISSUE", d, device=dev)
        return t + wall, completed, bad

    def view_row(self, prof, dev, t, watched, ti, ep, supp, attrs, bm_end, asid, ver, d, offline):
        R = self.R
        vid = 1_000_000_000 + self.idx * 100_000 + self.counters.get("v", 0)
        self.counters["v"] = self.counters.get("v", 0) + 1
        if t < 0:
            return vid
        T = self.cat.T[ti]
        sub_lang = None
        if ver >= APP_V9 or dev["plat"] == "web" and d >= APP_RELEASES[APP_V9][1]:
            sub_lang = "off" if R.random() < 0.78 else ("en" if prof["lang"] == "en" and R.random() < 0.8 else
                                                        "es" if R.random() < 0.6 else R.choice(["en", "es", "fr", "ko"]))
        key = (prof["id"], ep if ep is not None else ti, supp is not None)
        row = [vid, self.aid, prof["id"], dev["id"], fmt(t), hms(watched), T["id"],
               self.cat.ep_id[ep] if ep is not None else None, supp, attrs, hms(bm_end), None,
               int(offline), sub_lang]
        self.view_rows.append(row)
        if supp is None:
            self.views_by_key[key] = len(self.view_rows) - 1
        if dev["last"] is None or t + watched > dev["last"]:
            dev["last"] = t + watched
        self.last_act_end = max(self.last_act_end, t + watched)
        return vid

    def playtrace(self, vid, prof, t, startup, b0, watched, pauses, offline, dev, skip_intro):
        R = self.R
        t_ms = t * 1000 + int(dev["skew"] * 1000)
        evs = [("start", 0, b0 * 1000)]
        so = startup
        mo = b0 * 1000
        evs.append(("playing", so, mo))
        marks = []
        if skip_intro and R.random() < 0.3:
            marks.append((R.uniform(0.0, 0.04), "skip"))
        for frac, pl in pauses:
            marks.append((frac, ("pause", pl)))
        if R.random() < 0.15:
            marks.append((R.uniform(0.1, 0.9), "seek"))
        marks.sort(key=lambda x: x[0])
        played = 0
        wall = so
        for frac, m in marks:
            target = int(watched * 1000 * frac)
            step = max(0, target - played)
            wall += step
            mo += step
            played += step
            if m == "skip":
                jump = R.randint(55, 95) * 1000
                evs.append(("reposition", wall, mo))
                mo += jump
                evs.append(("playing", wall + 400, mo))
                wall += 400
            elif m == "seek":
                jump = R.randint(-120, 300) * 1000
                evs.append(("reposition", wall, mo))
                mo = max(0, mo + jump)
                evs.append(("playing", wall + 600, mo))
                wall += 600
            else:
                evs.append(("paused", wall, mo))
                wall += m[1] * 1000
                evs.append(("playing", wall, mo))
        wall += max(0, watched * 1000 - played)
        mo += max(0, watched * 1000 - played)
        evs.append(("stopped", wall, mo))
        late = offline or R.random() < 0.004
        for seq, (ev, so_, mo_) in enumerate(evs):
            cts = t_ms + so_
            if late:
                srv = t * 1000 + so_ + int(R.uniform(1800, 3 * 86400) * 1000)
            else:
                srv = t * 1000 + so_ + R.randint(40, 900)
            if srv >= WIN_END * 1000:
                continue
            line = L(vid, seq, ev, fmt_ms(cts), fmt_ms(srv), so_, mo_)
            self.w("playback_events", line)
            if R.random() < 0.0025:
                self.w("playback_events", line)

    def qrow(self, vid, dev, title_id, t, ver, cell, offline, startup, n_rb, rb_ms, played_ms, kbps, err, ebvs):
        R = self.R
        if t >= WIN_END:
            return
        pid = 7_000_000_000 + self.idx * 100_000 + self.counters.get("qp", 0)
        self.counters["qp"] = self.counters.get("qp", 0) + 1
        net = "offline_download" if offline else "cellular" if cell else ("ethernet" if dev["cat"] in BIG_SCREEN and R.random() < 0.25 else "wifi")
        isp = R.choice(MOBILE_CARRIERS) if cell else (None if offline else self.isp)
        st = self.remote_state if dev["remote"] else self.travel_state(int(t // 86400))
        res = None
        if kbps:
            res = "1080p" if kbps >= 4000 else "720p" if kbps >= 2000 else "480p"
        rbd = rb_ms
        if APP_RELEASES[ver][1] < 27 and dev["plat"] != "web":
            rbd = -1  # pre-8.11 clients did not report stall duration
        pop = None if offline else R.choice(CDN_POPS[self.tz]) + "%03d" % R.randint(1, 12)
        self.w("playback_quality", L(pid, vid, self.aid, dev["id"], title_id, fmt(t),
                                     version_string(R, dev["plat"], ver), net, isp, st, pop, startup, n_rb, rbd,
                                     played_ms, kbps if kbps else None, res, err, ebvs))

    def click(self, asid, prof, dev, ev, page, title_id, t, ver):
        R = self.R
        if t < SHORT_START or t >= WIN_END:
            return
        self.cs_seq += 1
        eid = 10_000_000_000 + self.idx * 1_000_000 + self.cs_seq
        cts = t + int(dev["skew"])
        srv = t + (R.randint(0, 2) if R.random() > 0.01 else R.randint(600, 2 * 86400))
        if srv >= WIN_END:
            return
        line = L(eid, asid, self.aid, prof["id"] if prof else None, dev["id"], ev, page, title_id, fmt(cts), fmt(srv))
        self.w("clickstream", line)
        if R.random() < 0.003:
            self.w("clickstream", line)

    # ------------------------------------------------------------------ final rows
    def finish(self):
        R = self.R
        aid = self.aid
        # viewing rows with latest bookmark
        latest = set(self.views_by_key.values())
        for i, row in enumerate(self.view_rows):
            if row[8] is None:
                row[11] = row[10] if i in latest else "Not latest view"
            else:
                row[11] = "Not latest view"
            line = L(*row)
            self.w("viewing_activity", line)
            if R.random() < 0.0004:
                self.w("viewing_activity", line)
        # profiles (hard-deleted profiles are purged from the profile table; their history remains)
        for p in self.profiles:
            if p["hard_del"]:
                continue
            self.w("profiles", L(p["id"], aid, p["name"], int(p["kids"]), p["maturity"], p["lang"], p["avatar"],
                                 int(p["auto_next"]), int(p["auto_prev"]), int(p["owner"]), fmt(p["created"]),
                                 fmt(p["deleted"]) if p["deleted"] is not None else None))
            for ti, (a, r, src) in p["mylist"].items():
                if a >= WIN_END:
                    continue
                self.w("my_list", L(self.nid("ml", 5000), aid, p["id"], self.cat.T[ti]["id"], fmt(a),
                                    fmt(r) if r is not None and r < WIN_END else None, src))
        # devices
        for x in self.devices:
            if x["first"] >= WIN_END:
                continue
            m = DEVICE_MODELS[x["mi"]]
            raw_cat = R.choice(CAT_RAW[x["cat"]])
            last = x["last"] if x["last"] is not None else x["first"] + R.randint(60, 3600)
            if x["deact"] is not None:
                last = min(last, x["deact"])
            last = min(last, WIN_END - 1)
            vf = x["ver_first"] if x["ver_first"] is not None else self.app_ver_idx(x, int(x["first"] // 86400))
            vl = x["ver_last"] if x["ver_last"] is not None else vf
            osv = x["os"] if R.random() > 0.01 else "-1"
            self.w("devices", L(x["id"], aid, raw_cat, csv_val(x["raw"]), x["plat"], m[2], csv_val(m[4]), osv,
                                version_string(R, x["plat"], vf), version_string(R, x["plat"], vl), x["esn"],
                                int(x["push"]), fmt(x["first"]), fmt(max(last, x["first"])),
                                fmt(x["deact"]) if x["deact"] is not None and x["deact"] < WIN_END else None))
        # payment methods
        for pm in self.pms:
            if pm["added"] >= WIN_END:
                continue
            if pm["type"] == "CARD":
                prov, brand, fund = "card", pm["brand"], pm["funding"]
                em, ey = pm["exp"]
            else:
                prov = {"PAYPAL": "PAYPAL", "APPLE": "APPLE_APP_STORE", "GOOGLE": "GOOGLE_PLAY", "ROKU": "ROKU_PAY",
                        "AMAZON": "AMAZON_APPSTORE"}[pm["type"]]
                brand = fund = em = ey = None
            mtype = "CARD" if pm["type"] == "CARD" else "PAYPAL" if pm["type"] == "PAYPAL" else "APP_STORE_BILLING"
            bz = self.zip3 if pm["type"] in ("CARD", "PAYPAL") and R.random() > 0.03 else None
            self.w("payment_methods", L(pm["id"], aid, mtype, prov, brand, fund, em, ey,
                                        ("%03d" % bz) if bz is not None else None, fmt(pm["added"]),
                                        fmt(pm["updated"]) if pm["updated"] is not None and pm["updated"] < WIN_END else None,
                                        fmt(pm["removed"]) if pm["removed"] is not None and pm["removed"] < WIN_END else None,
                                        pm["rsrc"] if pm["removed"] is not None and pm["removed"] < WIN_END else None))
        # subscription history
        for s in self.subs:
            if s["open"] >= WIN_END:
                continue
            closed = s["close"] if s["close"] is not None and s["close"] < WIN_END else None
            canc = s["cancel"] if s["cancel"] is not None and s["cancel"] < WIN_END else None
            self.w("subscription_history", L(s["id"], aid, s["seq"], s["type"], fmt(s["open"]), "STD_MONTHLY_US_1599",
                                             "Standard", "15.99", "MONTHLY", 2, "HD_1080P", 0, 0, s["anchor"], s["pm0"],
                                             fmt(canc) if canc is not None else None, s["cancel_ch"] if canc is not None else None,
                                             fmt(closed) if closed is not None else None,
                                             s["vol"] if closed is not None else None,
                                             s["reason"] if closed is not None else None))
        # account row (consent flags as of extraction)
        c = self.consent
        su = self.signup_dev
        by = None
        if R.random() < 0.31:
            by = R.randint(1950, 2006)
            if R.random() < 0.01:
                by = R.choice([1900, 1901, 2025])
        gender = R.choice(["F", "M", "F", "M", "X"]) if R.random() < 0.19 else None
        z = "%03d" % self.zip3
        if self.pay_pref in ("APPLE", "GOOGLE", "ROKU", "AMAZON") and R.random() < 0.08 or R.random() < 0.01:
            z = None
        tz = self.tz if R.random() > 0.02 else R.choice(list(TZ_STD.keys()))
        atype = "CONSUMER" if not self.test else ("QA_TEST" if self.test == 1 else "EMPLOYEE")
        self.w("accounts", L(aid, fmt(self.acct_created_s), atype, self.channel, su["plat"], su["cat"], self.state_code, z, tz,
                             "es-US" if self.profiles[0]["lang"] == "es" else "en-US", self.email_dom,
                             int(R.random() < 0.94), int(self.phone), by, gender, c["email_marketing"],
                             c["email_surveys"], c["email_kids_activity"], c["sms_transactional"], c["sms_informational"],
                             c["whatsapp"], c["marketing_matched_identifiers"], c["ccpa_do_not_sell_share"],
                             c["test_participation"], int(self.has_kids and R.random() < 0.3), int(R.random() < 0.11)))


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------
def run_batch(args):
    batch_id, idxs, out_dir = args
    get_ref()
    out = {t: [] for t in SIM_TABLES}
    part_dir = os.path.join(out_dir, "_parts")
    stats = {t: [0, 0] for t in SIM_TABLES}
    files = {t: gzip.open(os.path.join(part_dir, "%s.%05d.gz" % (t, batch_id)), "wt", encoding="utf-8",
                          newline="", compresslevel=5) for t in SIM_TABLES}

    def flush():
        for t in SIM_TABLES:
            buf = out[t]
            if buf:
                s = "\n".join(buf) + "\n"
                files[t].write(s)
                stats[t][0] += len(buf)
                stats[t][1] += len(s.encode())
                buf.clear()

    for n, i in enumerate(idxs):
        Sim(int(i), out).run()
        if n % 50 == 49:
            flush()
    flush()
    for f in files.values():
        f.close()
    return batch_id, stats


def merge(out_dir, n_batches, stats):
    part_dir = os.path.join(out_dir, "_parts")
    sizes = {}
    for t in SIM_TABLES:
        path = os.path.join(out_dir, t + ".csv.gz")
        header = (",".join(TABLES[t]) + "\n").encode()
        with open(path, "wb") as f:
            f.write(gzip.compress(header))
            for b in range(n_batches):
                pp = os.path.join(part_dir, "%s.%05d.gz" % (t, b))
                with open(pp, "rb") as g:
                    shutil.copyfileobj(g, f)
        rows = sum(s[t][0] for s in stats)
        raw = sum(s[t][1] for s in stats) + len(header)
        sizes[t] = (rows, raw, os.path.getsize(path))
    shutil.rmtree(part_dir)
    return sizes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--batch-size", type=int, default=500)
    ap.add_argument("--sample-every", type=int, default=1, help="simulate only every k-th account (testing)")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.seed is not None:
        CFG["seed"] = args.seed
    os.makedirs(os.path.join(args.out, "_parts"), exist_ok=True)
    t0 = time.time()
    ref = get_ref()
    n1, n2 = ref["cat"].write(args.out)
    idx = list(range(0, CFG["n_accounts"], args.sample_every))
    batches = [(b, idx[i:i + args.batch_size], args.out) for b, i in enumerate(range(0, len(idx), args.batch_size))]
    print("accounts=%d batches=%d workers=%d" % (len(idx), len(batches), args.workers), flush=True)
    stats = []
    if args.workers > 1:
        with Pool(args.workers) as pool:
            for b, s in pool.imap_unordered(run_batch, batches):
                stats.append(s)
                print("  batch %d done (%.0fs)" % (b, time.time() - t0), flush=True)
    else:
        for bt in batches:
            b, s = run_batch(bt)
            stats.append(s)
            print("  batch %d done (%.0fs)" % (b, time.time() - t0), flush=True)
    sizes = merge(args.out, len(batches), stats)
    sizes["catalog"] = (n1[0], n1[1], os.path.getsize(os.path.join(args.out, "catalog.csv.gz")))
    sizes["episodes"] = (n2[0], n2[1], os.path.getsize(os.path.join(args.out, "episodes.csv.gz")))
    with open(os.path.join(args.out, "_manifest.tsv"), "w") as f:
        f.write("table\trows\tuncompressed_bytes\tgzip_bytes\n")
        for t, (r, raw, gz) in sorted(sizes.items()):
            f.write("%s\t%d\t%d\t%d\n" % (t, r, raw, gz))
    tot = sum(v[1] for v in sizes.values())
    print("done in %.0fs, total uncompressed %.1f MB" % (time.time() - t0, tot / 1e6))
    for t, (r, raw, gz) in sorted(sizes.items()):
        print("  %-22s %11d rows %9.1f MB raw %8.1f MB gz" % (t, r, raw / 1e6, gz / 1e6))


if __name__ == "__main__":
    main()
