# GROUND TRUTH: SEALED

> **Do not read until your own analysis is finished.** This file describes the hidden behaviour model behind
> the Jetflix data: who the users are, what drives cancellations, how strong each driver is, and the
> exceptions built in on purpose. `generate_jetflix_data.py` (beyond its table definitions) and
> `GROUND_TRUTH_SEALED_difficulty_check.py` reveal the same information.

All parameters refer to the final run (seed 20261001). "Hazard" is the daily probability that a subscriber
who has not cancelled clicks cancel. All effects multiply unless stated. Nothing in this file is written
to the data.

---

## 1. Hidden user types (never output)

| Type | Share of new signups | Share of incumbents (active 2025-10-01) | Share of lapsed returners | Viewing intensity (median sittings/day before scaling) | Satisfaction mean | Hazard multiplier | Return multiplier (90d / later) |
|---|---|---|---|---|---|---|---|
| family (multi-profile, often kids) | 15% | 23% | 8% | 0.30 | +0.20 | 0.68 | 0.75 / 1.0 |
| adult (single/couple, regular) | 24% | 26% | 17% | 0.21 | +0.08 | 0.92 | 0.9 / 1.0 |
| binger (series-driven) | 13% | 13% | 12% | 0.30 | 0.00 | 0.95 | 1.0 / 1.0 |
| casual (light, occasional) | 17% | 12% | 13% | 0.105 | -0.10 | 1.12 | 0.7 / 0.9 |
| show chaser | 6% base + release spikes | 3% | 22% | 0.25 | -0.10 | 1.05 + chase logic | 1.35 / 1.5 |
| serial churner | 8% | 5% | 20% | 0.20 | -0.25 | 1.75 | 2.0 / 1.6 |
| passive payer (pays, barely watches) | 7% | 11% | 2% | 0.022 | 0.00 | 0.42 | 0.4 / 0.6 |
| movie lover | 10% | 7% | 6% | 0.17 | +0.05 | 0.92 | 0.85 / 1.0 |

Shares are the sampling weights. Among new signups the chaser share is set per signup day:
P(chaser) = 0.04 + 0.8 x (share of that day's signups caused by a tentpole spike). So chasers cluster in
the days after big releases, and 45% of them come through paid search, paid social, affiliate or TV-ad
campaigns. Serial churners and chasers carry prior closed periods in `subscription_history`.

Household situations, independent of type:
- **Kids** (85% of families, 9% of others): kids profiles, daytime/after-school/weekend-morning viewing, tablets.
- **Shared account** (9%, 2% of passive payers): an extra profile and device in another state (`geo_state`
  and login IPs differ). No direct churn effect.
- **Budget-stressed** (22%): more debit/prepaid cards, payment failures x1.6 (x1.4 more after the 24th of the
  month), January cancel hazard x1.5, exogenous hazard x1.2.
- **Student** (7% of adult/binger/casual/chaser/serial, 1% of others): cancel hazard x3.2 from May 10 to June 30;
  those who leave in May-July return in late August to mid-September.
- **Night-shift** (5%): adult viewing hours shifted by 10 hours.
- **Household change** (8.5% per year, one event): *move* 60% (hazard x2.1 for 45 days, satisfaction -0.25, new
  home IPs, 50% add a new TV/stick, 30% retire an old device), *split* 25% (x2.6 for 60 days, satisfaction
  -0.35, a non-kids profile deleted and 25% of those purged), *new baby* 15% (x1.3 for 90 days, viewing x0.6).

## 2. Latent state and engagement

Each account has:
- **mu**, a permanent satisfaction level ~ Normal(type mean, 0.5).
- **dev**, a daily deviation: dev(t) = 0.975 dev(t-1) + 0.025 target + 0.09 e + shocks.
  A **decline episode** starts with daily probability 1/230 and pulls `target` to -U(1.0, 2.3). It ends with
  daily probability 1/85, after which dev drifts back. Incumbents start in the stationary mix (27% already
  declining on 2025-10-01).
- **Rb**, viewing intensity, lognormal (sd 0.85) around the type median, scaled by 0.61.
- **kappa**, an unobserved inertia factor, lognormal (sd 0.25); passive payers x0.55.

Sittings per day ~ Poisson(Rb x weekday x month x holiday x vacation x exp(0.7 mu + 1.4 dev) x content state).
Within a sitting: binge continuation x min(1.25, e^(0.35 dev)); abandonment +max(0, -0.07 dev).
Low satisfaction therefore shows up as fewer sittings, shorter binges and more abandoned starts.

Shocks to dev: each bad-quality view -0.045; unresolved/abandoned/escalated support contact -0.12; reaching
a content gap -0.12; tentpole release day +0.18 for interested accounts; household events above.

## 3. The cancel hazard

```
h = 0.000300 x tenure x type x channel x payment x month x exp(-1.2 mu - 2.15 dev)
      x (1 + 0.32 x min(prior voluntary cancels, 4)) x usage x cycle position
      x content gap x chase x quality x support/refund/payment/household effects x budget x student
      x kappa
  + 0.00011 x type_exo x min(2.5, max(0.25, (Rb / type median)^0.6)) x (1.2 if budget-stressed)
```

| Driver | Strength | Where it shows in raw data |
|---|---|---|
| **Tenure** (renewals in current period) | x2.0, 1.55, 1.3, 1.15, 1.05, 1.0, 0.94, 0.88, 0.84, 0.80, 0.77, 0.75 for months 1-12; 0.68 in months 13-24; 0.60 after | `subscription_history.opened_ts`, `billing_history` |
| **Satisfaction decline** (dev) | exp(-2.15 dev): a deep decline (dev ~ -1.5) multiplies hazard by ~25 | Falling sittings/minutes, shorter binges, more abandoned views, fewer email opens/clicks, more thumbs-down |
| **Low satisfaction level** (mu) | exp(-1.2 mu), sd 0.5 | Lower viewing in general, lower email engagement |
| **Light usage** | (Rb / type median)^-0.9, clipped to 0.3-4; **not applied to passive payers** | Viewing level relative to household type |
| **Prior voluntary cancels** | +32% per earlier cancel (max 4) | `subscription_history.period_seq`, `signup_type = REJOIN` |
| **Show chaser** | x0.6 until they finish the chased title (or 45 days after release), then x3.0 for 40 days, x1.9 to day 90, x1.25 after | Signup within days of a promo-tier-A release, heavy viewing of that one title, then little else |
| **Content gap** | After a non-kids profile finishes a series with nothing else in progress and nothing unwatched on My List: x(1 + 3.0 e^(-days/28)) for bingers, x(1 + 1.8 e^(-days/28)) others. Viewing x0.72 and more browse-only sessions while it lasts. Ends on a My List add, a new title (50%), or after 75 days. | Final episode watched, no new series started, no My List adds, more browsing (clickstream) and searches |
| **Playback quality** | x(1 + 0.12 x bad views in last 14 days, max 9). Bad = stalls > 2% of play time, startup > 6 s, or mid-play error | `playback_quality` (last 90 days only), abandoned short views, `PLAYBACK_ISSUE` contacts |
| **Support** | Unresolved/abandoned x2.6 for 30 days; escalated x1.8; resolved x1.12 | `support_contacts.resolution` |
| **Refund request after renewal** | x4 for 4 days on top of the unresolved-support effect (0.45%/day chance in the 2 days after a renewal, x1.8 if dev < -0.4) | `REFUND_REQUEST` within 1 day of a renewal charge |
| **Recovered payment failure** | x1.6 for 45 days | `billing_history` declines, `GRACE_RESOLVED` |
| **Acquisition channel** | organic 0.88, paid search 1.0, paid social 1.28, referral 0.82, iOS app store 1.08, Google Play 1.10, smart-TV app 0.95, affiliate 1.32, TV ad 1.0 | `accounts.signup_channel` |
| **Payment method** | card 1.0, PayPal 1.05, app-store billing 1.13 | `payment_methods.method_type` |
| **Month** | Jan 1.28, Feb 1.05, Mar 1.0, Apr 0.97, May 1.02, Jun 1.0, Jul 0.95, Aug 1.08, Sep 1.03, Oct 1.0, Nov 0.92, Dec 0.86 | Calendar |
| **Cycle position** | x1.55 on days 0-2 after a renewal charge ("just got charged"); in the last ~3 days before renewal x1.95 **if the member has email-marketing consent (renewal reminder)** vs x1.3 without; x0.85 otherwise | Day of cancel relative to `billing_anchor_day`; `RENEWAL_REMINDER` sends |
| **Exogenous** (budget, competitor, life change with no behaviour change) | 0.00011/day x type_exo (family 0.8 ... serial 1.2), x(usage)^0.6, so it falls more on steady viewers | Nothing: no warning |
| **kappa** | lognormal sd 0.25 | Nothing (unobserved inertia) |

Notable consequences:
- **The renewal reminder raises cancels** among consenting members in the days before renewal. Members
  without email consent still cancel late in the cycle, but less.
- **Payment-method type and channel are weak.** They are real but small next to usage and decline.

**Cancel mechanics after the decision:** 3.5% of cancels are made through customer service with a
`CANCEL_HELP` contact minutes before. App-store cancels arrive as store notifications. Viewing after the
cancel changes by a random per-cancel factor (x0.25 to x1.3): some members binge out the paid month, others
stop at once. 6% unsubscribe from marketing email within 5 days of cancelling.

**Reversals** (`CANCEL_REVERSED`): daily probability 0.52% (x1.6 if dev > 0.2), +5 points within a day of
a release they care about, +2 points on the cancel day. About 6.5% of cancel requests are reversed.

## 4. Built-in exceptions

- **Temporary dips that do not lead to churn:** vacations (about 1.5 per account-year, 0.6 for passive payers;
  peaks in summer, Thanksgiving week, Christmas-New Year, March) cut viewing to 0-30% for 3-16 days with
  **no effect on hazard**. Travellers watch on phones/tablets, often downloaded (late playback events), with
  `geo_state` set to the destination. Decline episodes also recover about as often as they end in a cancel.
- **Warning signs but they stay:** low-kappa accounts, passive payers (hazard 0.42 and exempt from the
  light-usage effect), and members whose declines recover before a cancel fires.
- **Near-inactive users who keep paying:** passive payers (11% of incumbents) watch almost nothing yet have the
  lowest hazard. "Dormant" accounts (< 30 min per 28 days) are about 26% of non-churners and 26% of churners,
  so dormancy alone does not separate them.
- **Heavy users who cancel:** exogenous shocks weighted toward steady viewers, chasers who binge the release
  then leave, bingers hitting a content gap, and budget shocks in January.
- **No single near-perfect column:** the strongest single features have AUC ~0.66-0.68 (see section 7).
- **Test accounts** (`QA_TEST`, `EMPLOYEE`) cancel at 1.2%/day and rejoin within days. Exclude them.

## 5. Other designed patterns

**Involuntary churn (out of model scope):** first-attempt renewal failure 1.25% card, 0.9% app store, 1.15%
PayPal; prepaid +3.5 points, debit +0.4 points, budget-stressed x1.6 (x1.4 more after the 24th). Expired cards fail
unless the account updater (55%) or the member (20%) replaced them first. Retries on days 1/3/5 succeed 36%,
32%, 27% (x1.25 on the 1st, 2nd, 15th, 16th: paydays). Members fix the method 10%/day during grace (x1.5
with SMS consent, which gets the decline SMS). The result is 1.55% first-attempt failures and 0.23%/month
involuntary churn.

**Returns** (a new period on the same account): after a voluntary close, P(return within 90 days) =
0.225 x type factor, P(return in days 91-365) = 0.075 x type factor. 18% of quick returns come back within
9 days (regret). Chasers who return mostly (70%) time it to the next release they care about. Students who
leave in May-July come back late August. After an involuntary close, 42% return within 25 days. Measured: 24.3%
within 90 days and 31.8% by day 330 (Kaplan-Meier).

**Quality problems by device, area and app version** (affect satisfaction, abandonment and support, and are
fully visible only in the 90-day telemetry):
- Weak devices (quality factor; 1.0 is typical): Fire TV Stick 2nd Gen AFTT 1.6, Samsung 2017 Kant-M 1.6, Roku
  3800X 1.55, moto g play 1.5, LG 2018 webOS 4.0 1.45, Galaxy A14 1.4, Fire HD 10 Kids 1.35, Hisense VIDAA 1.3,
  Galaxy Tab A8 1.3, Apple TV HD 1.25. Several of these cannot update past 8.12.x.
- Area: ZIP3 broadband factor lognormal (sd 0.16), x1.22 in rural-broadband states (AL, KY, OK, IA, AR, KS, MS,
  NM, NE, ID, WV, ME, MT, SD, ND, AK, VT, WY), and 6% of ZIP3s get another x1.25.
- Evening peak (19-23 local) x1.12; cellular x1.35.
- Incident 1: app 9.1.0 on Fire TV / Android TV (2026-03-24 until devices take 9.1.2 from 2026-04-08): error rate
  x4. Before the 90-day window, so it shows only as abandoned views and `PLAYBACK_ISSUE` / `APP_BUG` contacts.
- Incident 2: app 9.3.0 on Roku (2026-07-07 until 9.3.1 from 2026-07-29, plus adoption lag): startup x1.5,
  stalls x1.5. Inside the 90-day telemetry.

**Tentpoles** (promo tier A, 13 in the window): Ironwood S3 (2025-10-17), The Hollowing (10-24), Kingdom of
Ash (11-21), Starfall Protocol (12-12), Blue Meridian S2 (2026-01-16, weekly), The Quiet Partner (02-20),
Ironwood: Origins (03-27), Paper Saints (04-24), Highwire S4 (05-22), Pip and the Moon Garden (06-19, kids),
Salt Road S2 (07-10, weekly), Northbound (08-14), The Lantern Society (09-11). Nine other titles also carry
tier A with no special behaviour (noise). Each release drives a signup spike (strength 0.45-1.0), a viewing
lift among interested accounts for 24 days, a satisfaction bump, and a higher reversal chance for pending
cancels. Weekly releases keep chasers subscribed longer.

**Seasonality of signups:** growth 2%/month; Dec-Jan high, Apr-May low; weekends x1.14; Black Friday x1.55,
Christmas Day x1.8 (new devices), New Year's Day x1.4.

## 6. Leakage traps in the raw data

These fields are legitimate operational records but are written at or after the cancel, or are
as-of-extraction snapshots:
- `subscription_history.cancel_requested_ts`, `membership_events` `CANCEL_REQUESTED`,
  `payment_methods.removed_ts` with `USER_CANCELLED` / `STORE_AUTO_RENEW_OFF`, the `CANCEL_CONFIRMATION` email,
  and clickstream `membership_cancel` / `cancel_confirm`. These are the cancel itself.
- `support_contacts` `CANCEL_HELP` minutes before a CS cancel.
- `accounts.email_consent_marketing` as of extraction (6% of cancellers unsubscribe right after cancelling), plus
  every other as-of-extraction snapshot (`profiles.deleted_ts`, `devices.last_seen_ts`/`deactivated_ts`,
  `app_version_last`, `payment_methods.last_updated_ts`).
- Viewing between cancel and close is post-decision behaviour.
- `communications_log` `WINBACK` and `WELCOME_BACK` happen after churn.
- `RENEWAL_REMINDER` stops for members with a pending cancel (no renewal to remind about).

## 7. Measured difficulty (final data)

From `GROUND_TRUTH_SEALED_difficulty_check.py`. One row per billing cycle, scored at the cycle start (just after
a successful charge). Label: the period closes voluntarily at the end of that cycle. Time split: train on cycles
starting 2025-10-31 to 2026-05-14 (195k cycles), test on cycles starting 2026-06-15 or later (82k; base rate 5.1%).
About 40 engineered features (watch minutes 7/14/30/60 days, trend, days since last view, viewing days,
views per viewing day, abandoned-view share, finale watched, new titles started, My List adds, searches with no
result, support contacts and unresolved ones, failed payments, email opens/clicks, logins, devices, profiles,
kids profiles, payment type, channel, consent, tenure, prior periods, prior cancel requests and reversals,
account age, days since the last tier-A release at period open, month).

| Result | Value |
|---|---|
| **LightGBM ROC-AUC (time split)** | **0.744** (target 0.72-0.82) |
| Rule "no viewing for 14+ days" | flags 41.6% of test cycles; precision 8.3% (base 5.1%); recall 67%; AUC 0.635 |
| Best single features (AUC) | viewing days 30d 0.676, views 30d 0.674, minutes 30d 0.670, minutes 60d 0.664, views per viewing day 0.663, days since last view 0.657, minutes 14d 0.659, viewing days 7d 0.636, tenure 0.616, cancel requests ever 0.594, prior periods 0.591 |
| Weak single features (AUC) | days since tier-A release 0.564, My List adds 0.538, trend 14/60 0.539, devices 0.523, kids profiles 0.522, finale 14d 0.517, payment type 0.515, month 0.514, email opens 0.512, channel 0.504, support 0.50, failed payments 0.50 |

Support, payment failures and finales are strong for the few accounts they touch but rare, so their
population-level AUC is near 0.5. The 90-day quality telemetry is not in this check.

**Churners with no visible warning beforehand** (voluntary cancels with 60+ days of tenure, February-September):
a warning is (a) watch time in the last 28 days below X% of the member's own average for the 12 weeks before
(when that baseline is at least 2 hours per 28 days), (b) silence for 14+ days by someone who watched on 6+
days in the prior 12 weeks, (c) dormancy (< 30 min per 28 days), or (d) a support contact in 30 days, a
declined payment in 60 days, or a series finale in 14 days.

| Drop threshold X | Churners with no warning | Non-churners flagged |
|---|---|---|
| 60% | 33.4% | 59.2% |
| **50% (headline)** | **34.5%** | 56.9% |
| 40% | 35.6% | 54.6% |
| 30% | 37.2% | 52.1% |

Per signal (at 50%), churners vs non-churners: drop 20.9% vs 12.0%; silence 22.8% vs 10.8%; dormant 25.9% vs
26.1%; event 14.0% vs 11.5%. Heavy viewers (top quartile) make up 12.9% of churners, and 4.0% of all cancels are
heavy viewers with no warning. The share with no warning sits at the top of the 25-35% target. Non-churners trip
these flags often, so no simple rule separates the groups.

## 8. Calibration results (from validation_report.md)

Voluntary churn 5.30%/month (tenure month 1 10.9%, month 2 7.2%, month 3 6.6%, ... month 12 4.4%, months 13-24
3.8%, months 25-36 2.8%); joins 7.44% (about 28% of them rejoins); net growth 1.91%; involuntary 0.23%; returns
24.3% within 90 days and 31.8% by day 330. January and October have the highest churn; March, August and December the lowest.
