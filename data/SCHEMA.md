# Jetflix raw data: schema and data dictionary

Jetflix is a fictional, Netflix-like streaming service (US only, one ad-free Standard plan at $15.99/month).
This document describes the raw operational extract in `data/`, in the style of the cover sheet Netflix
sends with a Member Information Request. It describes what each system stores, not what the data shows.

| | |
|---|---|
| Extract date | 2026-10-01 03:12 UTC |
| Data window | 2025-10-01 00:00 UTC to 2026-09-30 23:59 UTC |
| Sample | exactly 50,000 accounts that held an active subscription at any time in the window |
| Format | one gzipped CSV per table, UTF-8, header row, comma-separated, `"` quoting where needed |
| Timestamps | ISO-8601 UTC (`2026-03-14T21:07:55Z`; playback events carry milliseconds) |
| Dates | `YYYY-MM-DD` (billing period dates, catalog availability, episode release dates) |
| Missing values | empty field = NULL. `-1` means the system did not capture or could not measure a value |
| Generator | `generate_jetflix_data.py` (seed 20261001). Validation: `validate_jetflix_data.py` -> `validation_report.md` |

> The generator contains the hidden behaviour model. If you want a blind analysis, read only its
> `TABLES` definition, the same as you would avoid `GROUND_TRUTH_SEALED.md`.

General notes (as on Netflix's cover sheet):
- Different systems keep data for different periods. `playback_events`, `playback_quality` and `clickstream`
  keep only the most recent 90 days (2026-07-03 to 2026-09-30). The other activity tables cover the full window.
  Account-level tables (`accounts`, `profiles`, `devices`, `payment_methods`, `subscription_history`,
  `billing_history`, `membership_events`, `consent_events`) keep full history from account creation, which for
  some accounts starts at platform launch (2023-10-01).
- Snapshot tables (`accounts`, `profiles`, `devices`, `payment_methods`) show the state **as of extraction**.
  Consent flags, deletion timestamps and last-seen values can therefore reflect events after a given analysis
  date. Use the event tables (`consent_events`, `membership_events`) to rebuild state at a point in time.
- Values come from several ingestion systems, so some categorical strings are not normalised (for example
  `devices.device_category` holds `TV`, `Smart TV` and `tv`).
- There is no country column: everything is US. Times are UTC. Viewers' local times differ by state and DST.

## Tables

| # | Table | Grain | Rows | Retention | Primary key |
|---|---|---|---|---|---|
| 1 | accounts | one row per account | 50,000 | snapshot | account_id |
| 2 | profiles | one row per profile (purged profiles removed) | 101,584 | snapshot | profile_id |
| 3 | devices | one row per registered device | 153,144 | snapshot | device_id |
| 4 | payment_methods | one row per payment method ever added | 65,246 | full history | payment_method_id |
| 5 | subscription_history | one row per subscription period | 61,331 | full history | subscription_id |
| 6 | billing_history | one row per charge attempt or authorisation | 677,917 | full history | transaction_id |
| 7 | membership_events | account change log | 271,991 | full history | event_id |
| 8 | consent_events | consent changes (incl. initial values at signup) | 451,401 | full history | (account_id, consent_type, changed_ts) |
| 9 | viewing_activity | one row per playback (title or episode view, previews, trailers) | 3,326,139 | window | view_id |
| 10 | playback_events | play-trace events per view | 3,922,212 | 90 days | (view_id, event_seq) |
| 11 | playback_quality | QoE telemetry per playback attempt | 791,633 | 90 days | playback_id |
| 12 | search_history | one row per search | 171,925 | window | search_id |
| 13 | clickstream | app/web UI events | 2,158,373 | 90 days | event_id |
| 14 | ratings | thumbs ratings | 58,124 | window | rating_id |
| 15 | my_list | My List items | 95,650 | window (adds) | list_item_id |
| 16 | login_events | sign-ins, failures, resets, sign-outs | 198,805 | window | login_event_id |
| 17 | support_contacts | customer-service contacts | 16,247 | window | contact_id |
| 18 | communications_log | email, SMS and push messages sent | 893,619 | window | message_id |
| 19 | catalog | titles (fictional) | 3,345 | reference | title_id |
| 20 | episodes | episodes of series titles | 25,240 | reference | episode_id |

Total: 13.5 million rows, 1.41 GB uncompressed, 0.28 GB gzipped. Exact counts and sizes are in `validation_report.md`.

## Relationships

```
accounts 1-* profiles ------------------------------+
accounts 1-* devices ---------------------------+   |
accounts 1-* payment_methods 1-* billing_history|   |
accounts 1-* subscription_history 1-* billing_history
accounts 1-* membership_events (-> subscription_id, payment_method_id, device_id)
accounts 1-* consent_events / login_events (-> device_id) / support_contacts (-> device_id)
accounts 1-* communications_log (-> device_id for PUSH)
viewing_activity  -> account_id, profile_id, device_id, title_id, episode_id
  1-* playback_events (view_id)
  1-0..1 playback_quality (view_id; NULL view_id = attempt that never started)
search_history / ratings / my_list -> account_id, profile_id, title_id (search: displayed_title_id)
clickstream -> account_id, profile_id, device_id, title_id, app_session_id groups one app session
catalog 1-* episodes
```

Known orphans (kept, as in real extracts): profiles purged under a deletion request are removed from
`profiles`, but their historical rows remain in `viewing_activity`, `search_history`, `ratings` and
`clickstream` (about 0.04% of viewing rows). `playback_quality.view_id` is NULL when playback failed before
video start, because no viewing row is written for those attempts.

---

## 1. accounts

The account owner's record as of extraction. No names, emails, phone numbers or addresses are included.

| Column | Type | Description |
|---|---|---|
| account_id | int | Account identifier. Increases with creation time; gaps belong to accounts outside the sample. |
| account_created_ts | ts | When the account record was created (a few minutes before the first subscription opened). |
| account_type | str | `CONSUMER`, `EMPLOYEE` (staff accounts, billed normally) or `QA_TEST` (internal test accounts). About 0.1% are not CONSUMER. |
| signup_channel | str | Attributed acquisition channel at account creation: `organic_direct`, `paid_search`, `paid_social`, `referral_link`, `ios_app_store`, `google_play`, `smart_tv_app`, `affiliate`, `tv_ad_campaign`. |
| signup_platform | str | Platform of the device used at signup (`web`, `ios`, `android`, `roku`, `fireos`, `tizen`, ...). |
| signup_device_category | str | Category of that device (`WEB`, `MOBILE`, `TABLET`, `TV`, `STREAMING_STICK`). |
| state | str | US state (2-letter, includes DC) from billing address or, for app-store payers, IP geolocation at signup. |
| zip3 | str | First three digits of the ZIP code. NULL when unknown (app-store payers with no billing address, ~2%). |
| account_timezone | str | IANA time zone set on the account at signup (device locale); occasionally differs from the state's zone. |
| preferred_language | str | `en-US` or `es-US`. |
| email_domain | str | Domain of the account email (no local part). |
| email_verified | 0/1 | Email address confirmed. |
| phone_on_file | 0/1 | A phone number is stored. |
| birth_year | int | Optional, self-reported (~30% filled). Contains a few implausible values as entered. |
| gender | str | Optional, self-reported `F`, `M`, `X` (~19% filled). |
| email_consent_marketing | 0/1 | Eligible for marketing email (renewal reminder, digests, release announcements, win-back). As of extraction. |
| email_consent_surveys | 0/1 | Eligible for survey emails. |
| email_consent_kids_activity | 0/1 | Eligible for kids & family emails. |
| sms_consent_transactional | 0/1 | Eligible for transactional SMS (payment problems). |
| sms_consent_informational | 0/1 | Eligible for informational SMS (new release alerts). |
| whatsapp_consent | 0/1 | Opted in to WhatsApp messages (no WhatsApp messages are sent today). |
| marketing_matched_identifiers_consent | 0/1 | Eligible for promotional communications on third-party services. |
| ccpa_do_not_sell_share | 0/1 | Member opted out of sale/sharing of personal information (state privacy laws). |
| test_participation | 0/1 | Account setting allowing participation in product tests (default on). |
| parental_pin_enabled | 0/1 | Profile lock / parental PIN set. |
| two_step_verification_enabled | 0/1 | Extra sign-in verification enabled. |

## 2. profiles

| Column | Type | Description |
|---|---|---|
| profile_id | int | Profile identifier. |
| account_id | int | Owning account. |
| profile_name | str | Name typed by the member (household nicknames). |
| is_kids | 0/1 | Kids profile. |
| maturity_level | str | `ALL` for standard profiles; `TV-Y7` or `TV-PG` cap for kids profiles. |
| profile_language | str | `en` or `es`. |
| avatar_id | int | Selected icon. |
| autoplay_next_episode | 0/1 | Autoplay next episode setting (as of extraction). |
| autoplay_previews | 0/1 | Autoplay previews while browsing on TV (as of extraction). |
| is_account_owner | 0/1 | The account's primary profile. |
| created_ts | ts | Profile creation time. |
| deleted_ts | ts | When the profile was deleted; NULL if it still exists. |

## 3. devices

One row per device registration (a device signed in to the account).

| Column | Type | Description |
|---|---|---|
| device_id | int | Device registration identifier. |
| account_id | int | Account. |
| device_category | str | Device class as reported by the ingestion path; not normalised (`TV`/`Smart TV`/`tv`, `STREAMING_STICK`/`Streaming Stick`/`stb`, `MOBILE`/`Mobile`/`phone`, `TABLET`/`Tablet`, `WEB`/`Browser`/`web`, `GAME_CONSOLE`/`Game Console`). |
| device_type_raw | str | Device description string as reported by the client, e.g. `Roku Express 3930X Streaming Stick`, `Samsung 2019 UHD TV (Kant-S) Smart TV`, `Chrome PC (Halo)`. Spelling varies for the same model. |
| platform | str | `roku`, `fireos`, `tizen`, `webos`, `vizio`, `vidaa`, `androidtv`, `tvos`, `ios`, `android`, `web`, `playstation`, `xbox`. |
| manufacturer | str | NULL for browsers. |
| model_code | str | Hardware model code (`3930X`, `AFTMM`, `iPhone14,5`, ...). NULL for browsers. |
| os_version | str | Last reported OS version; `-1` when not reported. |
| app_version_first | str | App version at first use (web: player build `halo-...`). Formats vary (`9.1.0`, `v9.1.0`, `tv-9.1.0`, `9.1.0 (build 22587)`). |
| app_version_last | str | App version at last use. Some older TV models cannot update past 8.12.x. |
| esn_hash | str | Hashed device serial / ESN. |
| push_enabled | 0/1 | Push notifications allowed (mobile and tablet apps). |
| first_seen_ts | ts | Registration time. |
| last_seen_ts | ts | Last playback or sign-in seen from this device (capped at window end). |
| deactivated_ts | ts | Signed out / removed from the account; NULL if still registered. |

## 4. payment_methods

| Column | Type | Description |
|---|---|---|
| payment_method_id | int | Identifier. A re-added card is a new row. |
| account_id | int | Account. |
| method_type | str | `CARD`, `APP_STORE_BILLING`, `PAYPAL`. |
| provider | str | `card`, `PAYPAL`, `APPLE_APP_STORE`, `GOOGLE_PLAY`, `ROKU_PAY`, `AMAZON_APPSTORE`. |
| card_brand | str | `VISA`, `MASTERCARD`, `AMEX`, `DISCOVER` (cards only). |
| card_funding | str | `credit`, `debit`, `prepaid` (cards only). |
| card_exp_month, card_exp_year | int | Current expiry on file (cards only). The network account updater can refresh it in place. |
| billing_zip3 | str | Billing ZIP3 (card and PayPal); NULL for app-store billing or when missing. |
| added_ts | ts | When the method was added. |
| last_updated_ts | ts | Last in-place update (account-updater expiry refresh); NULL if never updated. |
| removed_ts | ts | When it was removed; NULL if still on file. |
| removal_source | str | `USER_CANCELLED` (member removed it to cancel membership), `STORE_AUTO_RENEW_OFF` (store notified that auto-renew was turned off), `USER_REPLACED` (replaced by another method), `SYSTEM_DUNNING_EXHAUSTED` (detached after the grace period ended unpaid). |

## 5. subscription_history

One row per subscription period. A member who leaves and comes back gets a new period on the same account.

| Column | Type | Description |
|---|---|---|
| subscription_id | int | Period identifier. |
| account_id | int | Account. |
| period_seq | int | 1 for the first period of the account, 2 for the next, ... |
| signup_type | str | `NEW` (first period) or `REJOIN`. |
| opened_ts | ts | When the period started (first successful charge). Also sets the billing anchor. |
| plan_code, plan_name | str | `STD_MONTHLY_US_1599`, `Standard` (the only plan). |
| plan_price_usd | dec | 15.99. |
| billing_cycle | str | `MONTHLY`. |
| max_concurrent_streams | int | 2. |
| max_video_quality | str | `HD_1080P`. |
| has_ads | 0/1 | 0. |
| is_free_trial_at_signup | 0/1 | 0 (Jetflix has no trials). |
| billing_anchor_day | int | Day of month renewals are charged (clamped to the last day in shorter months). |
| initial_payment_method_id | int | Payment method charged when the period opened. |
| cancel_requested_ts | ts | When the member cancelled (removed the payment method or turned off store auto-renew), for the cancel that ended the period. NULL if the period was not cancelled. A cancel that was later reversed is not shown here; see `membership_events`. If a cancel is pending at extraction, this is set and `closed_ts` is NULL. |
| cancel_channel | str | Where the cancel was made: `WEB`, `IOS_APP`, `ANDROID_APP`, `TV_APP`, `CUSTOMER_SERVICE`, `APPLE_SUBSCRIPTIONS`, `GOOGLE_PLAY`, `ROKU`, `AMAZON`. |
| closed_ts | ts | When access ended. For a member cancel: the next renewal time (end of the paid month). For an unpaid renewal: 7 days after the renewal (end of grace). NULL while open. |
| is_customer_initiated_cancel | 0/1 | 1 = ended by the member's cancel; 0 = closed by the system after the grace period. NULL while open. |
| close_reason_code | str | `MEMBER_CANCELLED` or `PAYMENT_DECLINED_GRACE_EXPIRED`. |

## 6. billing_history

Every charge attempt, retry and verification. All amounts are USD, no tax lines, no refunds.

| Column | Type | Description |
|---|---|---|
| transaction_id | int | Identifier. |
| account_id, subscription_id, payment_method_id | int | Keys. |
| invoice_id | str | Invoice the attempt belongs to; retries share the invoice of the failed renewal. NULL for `VERIFY`. |
| transaction_ts | ts | When the gateway processed it. Renewals run within ~30 minutes after the anchor time. |
| transaction_type | str | `CHARGE` (first attempt, or a charge after the member updated the payment method during grace), `RETRY` (automatic retry on day 1, 3 and 5 of grace), `VERIFY` ($0.00 authorisation when a card or PayPal account is added). |
| attempt_number | int | 1 for the first attempt of an invoice, then 2, 3, ... |
| amount_usd | dec | 15.99 for charges and retries; 0.00 for verifications. |
| currency | str | `USD`. |
| billing_period_start, billing_period_end | date | Paid month the invoice covers. |
| pmt_status | str | `approved` or `declined`. |
| final_invoice_result | str | `COMPLETED`, `DECLINED`, or `AUTHORIZATIONS` (verifications). |
| failure_code | str | For declines: `INSUFFICIENT_FUNDS`, `DO_NOT_HONOR`, `GENERIC_DECLINE`, `EXPIRED_CARD`, `PROCESSOR_TIMEOUT`, `CARD_RESTRICTED`, `LOST_OR_STOLEN`, `INVALID_ACCOUNT`, `PAYPAL_FUNDING_FAILED`, `PAYPAL_INSTRUMENT_DECLINED`, `STORE_BILLING_RETRY`, `STORE_PAYMENT_DECLINED`. |
| gateway | str | `card_gw_1`, `PAYPAL`, `APPLE_APP_STORE`, `GOOGLE_PLAY`, `ROKU_PAY`, `AMAZON_APPSTORE`. |
| next_billing_date | date | Next renewal date after an approved charge; NULL otherwise. |

## 7. membership_events

Account change log written by the membership service.

| Column | Type | Description |
|---|---|---|
| event_id | int | Identifier. |
| account_id | int | Account. |
| subscription_id | int | Period current at the time (NULL before the first period). |
| event_ts | ts | Event time. |
| event_type | str | `SUBSCRIPTION_STARTED`, `SUBSCRIPTION_CLOSED`, `CANCEL_REQUESTED`, `CANCEL_REVERSED` (member re-added a payment method before the renewal, so the subscription continues), `PAYMENT_METHOD_ADDED`, `PAYMENT_METHOD_REMOVED`, `PAYMENT_METHOD_UPDATED`, `GRACE_STARTED`, `GRACE_RESOLVED`, `PROFILE_CREATED`, `PROFILE_DELETED`, `PASSWORD_CHANGED`, `EMAIL_CHANGED`. |
| source | str | `WEB`, `IOS`, `ANDROID`, `TV`, `APP_STORE_NOTIFICATION`, `CS_AGENT`, `ACCOUNT_UPDATER`, `SYSTEM`. |
| device_id | int | Mostly NULL (not captured by this service). |
| payment_method_id | int | For payment-method and cancel events. |

## 8. consent_events

| Column | Type | Description |
|---|---|---|
| account_id | int | Account. |
| consent_type | str | `email_marketing`, `email_surveys`, `email_kids_activity`, `sms_transactional`, `sms_informational`, `whatsapp`, `marketing_matched_identifiers`, `ccpa_do_not_sell_share`, `test_participation`. |
| new_value | 0/1 | Value after the change. |
| changed_ts | ts | When it changed (account creation for initial values). |
| source | str | `SIGNUP`, `ACCOUNT_SETTINGS`, `EMAIL_UNSUBSCRIBE_LINK`, `SMS_STOP`. |

## 9. viewing_activity

One row per playback, as in Netflix's ViewingActivity table. A series watched episode after episode produces one
row per episode. Views shorter than a few seconds that never started are not written (see `playback_quality`).

| Column | Type | Description |
|---|---|---|
| view_id | int | Playback identifier (joins to `playback_events`, `playback_quality`). |
| account_id, profile_id, device_id | int | Keys. |
| start_ts | ts | When playback started. |
| duration | `HH:MM:SS` | Time played (pauses excluded). A few sessions on TVs report many hours when the player never sent a stop. |
| title_id | int | Title (movie, series, special). |
| episode_id | int | Episode for series; NULL for movies, specials and previews. |
| supplemental_video_type | str | NULL for the title itself; `HOOK` (autoplayed preview while browsing on TV) or `TRAILER`. |
| attributes | str | Semicolon-terminated flags, e.g. `Autoplayed: user action: None; ` (next episode or preview played without interaction), `Autoplayed: user action: Unspecified; `, `Autoplayed: user action: User_Interaction; `, `Has branched playback; `, `View was hidden; `. NULL when none. |
| bookmark | `HH:MM:SS` | Playback position when the view ended. Equal to the runtime when the episode/movie was finished. |
| latest_bookmark | str | Same as `bookmark` for the profile's most recent view of that title/episode, otherwise `Not latest view`. |
| is_offline_download | 0/1 | Played from a downloaded file on mobile/tablet. |
| subtitle_language | str | `off`, `en`, `es`, ... Only logged by app 9.0.0+ (released 2026-02-10, staggered rollout by platform) and the web player from that date; NULL before and on older clients. |

## 10. playback_events (last 90 days)

Play traces within a view, like Netflix's PlaybackRelatedEvents.

| Column | Type | Description |
|---|---|---|
| view_id | int | Playback. |
| event_seq | int | Order within the view as sent by the client. |
| event_type | str | `start`, `playing`, `paused`, `reposition` (seek, skip intro, +/-10s), `stopped`. |
| client_ts | ts(ms) | Device clock time. A small share of devices have clocks off by up to a few minutes. |
| server_received_ts | ts(ms) | When the event reached the server. Offline/downloaded playback and flaky networks arrive hours or days late. |
| session_offset_ms | int | Milliseconds since the start of the view (wall clock, includes pauses). |
| media_offset_ms | int | Position in the video. |

About 0.25% of rows are exact duplicates (client re-sends).

## 11. playback_quality (last 90 days)

One row per playback attempt, including attempts that failed before video started. Metrics follow
CTA-2066 / common QoE definitions.

| Column | Type | Description |
|---|---|---|
| playback_id | int | Attempt identifier. |
| view_id | int | Matching view; NULL when the attempt never started (exit before video start). |
| account_id, device_id, title_id | int | Keys. |
| client_ts | ts | Attempt start. |
| app_version | str | App/player version at the time (formats vary, see devices). |
| network_type | str | `wifi`, `ethernet`, `cellular`, `offline_download`. |
| isp_name | str | Home ISP or mobile carrier as resolved from IP; NULL for offline playback. |
| geo_state | str | State resolved from IP (differs from the account state when travelling or for viewers outside the home). |
| cdn_pop | str | CDN point of presence that served the stream; NULL offline. |
| startup_time_ms | int | Time from play request to first frame; `-1` when playback failed before starting. |
| rebuffer_count | int | Number of stalls after start. |
| rebuffer_duration_ms | int | Total stall time; `-1` on clients older than 8.11.0 that did not report it. |
| played_duration_ms | int | Time played. |
| avg_bitrate_kbps | int | Average video bitrate; NULL when nothing played. |
| peak_resolution | str | `480p`, `720p`, `1080p`; NULL when nothing played. |
| error_code | str | Player error, e.g. `JF-1011` (network timeout), `JF-5003` (CDN unreachable), `JF-2002` (DRM license), `JF-3104` (decoder), `JF-1001`, `JF-7020`. NULL if none. |
| exit_before_video_start | 0/1 | The attempt ended before any video played. |

## 12. search_history

| Column | Type | Description |
|---|---|---|
| search_id | int | Identifier. |
| account_id, profile_id, device_id | int | Keys. |
| is_kids | 0/1 | Search made on a kids profile. |
| search_ts | ts | Time. |
| query_typed | str | Text as typed (prefixes, typos, genre words, names of shows Jetflix does not carry). |
| displayed_title_id | int | Title shown/selected from the results; NULL when nothing matched. |
| action | str | `play`, `view_details`, `add_to_my_list`, `none`. |
| section | str | `search_results`, `suggested`, `top_searches`, `voice`. |

## 13. clickstream (last 90 days)

| Column | Type | Description |
|---|---|---|
| event_id | int | Identifier. |
| app_session_id | int | Groups events of one app/web session. |
| account_id, profile_id, device_id | int | Keys (profile NULL before a profile is chosen, e.g. the rejoin screen of a former member). |
| event_type | str | `app_launch`, `page_view`, `click`, `search_submit`. |
| page | str | `home`, `title_detail`, `search`, `profile_select`, `play`, `add_to_my_list`, `account`, `membership_cancel`, `cancel_confirm`, `rejoin`, `rejoin_plan`. For `click`, the element clicked. |
| title_id | int | Title involved, when any. |
| client_ts | ts | Device time (can be skewed). |
| server_received_ts | ts | Ingestion time (about 1% arrive late). |

About 0.3% of rows are exact duplicates. Cancels made in an app store produce no Jetflix clickstream.

## 14. ratings

| Column | Type | Description |
|---|---|---|
| rating_id | int | Identifier. |
| account_id, profile_id, title_id | int | Keys. |
| rating_type | str | `thumb`. |
| thumbs_value | int | `1` thumbs down, `2` thumbs up, `3` two thumbs up ("love this"). |
| device_id | int | Device recorded with the rating (may not be the device used to watch). |
| event_ts | ts | Time. |

## 15. my_list

| Column | Type | Description |
|---|---|---|
| list_item_id | int | Identifier. |
| account_id, profile_id, title_id | int | Keys. |
| added_ts | ts | When added. |
| removed_ts | ts | When removed; NULL if still on the list. |
| add_source | str | `title_detail`, `search`. |

## 16. login_events

| Column | Type | Description |
|---|---|---|
| login_event_id | int | Identifier. |
| account_id | int | Account. |
| device_id | int | Device; NULL for password-reset events. |
| event_ts | ts | Time. |
| event_type | str | `LOGIN_SUCCESS`, `LOGIN_FAILURE`, `LOGOUT`, `PASSWORD_RESET_REQUEST`, `PASSWORD_RESET_COMPLETE`. |
| auth_method | str | `PASSWORD`, `EMAIL_LINK`, `TV_CODE`, `BIOMETRIC_TOKEN`. |
| ip_hash | str | Hashed IP address. |
| geo_state | str | State resolved from IP. |
| failure_reason | str | `BAD_PASSWORD`, `UNKNOWN_EMAIL`, `RATE_LIMITED` for failures. |

A handful of rows are duplicated by the auth service.

## 17. support_contacts

| Column | Type | Description |
|---|---|---|
| contact_id | int | Identifier. |
| account_id | int | Account. |
| contact_ts | ts | When the contact started. |
| channel | str | `CHAT`, `PHONE`, `EMAIL`, `SOCIAL`. |
| contact_reason | str | Agent-selected reason: `BILLING_QUESTION`, `PAYMENT_FAILED`, `REFUND_REQUEST`, `PLAYBACK_ISSUE`, `DEVICE_ACTIVATION`, `LOGIN_PASSWORD`, `ACCOUNT_SHARING`, `CONTENT_AVAILABILITY`, `CANCEL_HELP`, `APP_BUG`, `OTHER`. |
| resolution | str | `RESOLVED`, `RESOLVED_WORKAROUND`, `ESCALATED`, `UNRESOLVED`, `CUSTOMER_ABANDONED`. |
| handle_time_sec | int | Agent handle time; `-1` for email (not measured). |
| csat_score | int | Post-contact survey 1-5; NULL when not answered (~70%). |
| agent_tier | str | `TIER1`, `TIER2`, `BILLING`. |
| device_id | int | Device the issue concerns, when recorded. |

## 18. communications_log

| Column | Type | Description |
|---|---|---|
| message_id | int | Identifier. |
| account_id | int | Account. |
| channel | str | `EMAIL`, `SMS`, `PUSH`. |
| message_type | str | Transactional (sent regardless of marketing consent): `WELCOME`, `WELCOME_BACK`, `CANCEL_CONFIRMATION`, `PAYMENT_DECLINED`, `PAYMENT_METHOD_EXPIRING`. Consent-based: `RENEWAL_REMINDER` (generic, ~3 days before each renewal), `NEW_ON_JETFLIX_DIGEST` (monthly), `NEW_RELEASE` (email, informational SMS, push), `WINBACK` (2-4 weeks after access ends). |
| campaign_id | str | Campaign key for marketing sends (e.g. `tp-05-2026-01-16`, `dg-2026-03-05`, `rr-std-v2`). |
| template_version | str | Template version. |
| sent_ts | ts | Sent. |
| delivered_ts | ts | Delivered; NULL when bounced / token invalid. |
| bounce_type | str | `SOFT`, `HARD`, `TOKEN_INVALID`. |
| opened_ts | ts | First open. Note: Apple Mail Privacy Protection pre-fetches messages, which records an "open" seconds after delivery whether or not the person read it. |
| clicked_ts | ts | First click. |
| unsubscribed_ts | ts | Unsubscribe from this message (email link or SMS STOP). |
| device_id | int | Target device for PUSH. |

## 19. catalog

| Column | Type | Description |
|---|---|---|
| title_id | int | Identifier. |
| title_name | str | Fictional title. |
| title_type | str | `MOVIE`, `SERIES`, `LIMITED_SERIES`, `SPECIAL`. |
| primary_genre, secondary_genre | str | Genres (secondary often NULL). |
| maturity_rating | str | US TV or MPA rating; NULL for a few titles. |
| original_language | str | ISO 639-1. |
| release_year | int | Original release year. |
| runtime_min | int | Movies and specials. |
| num_seasons, num_episodes | int | Series. |
| is_jetflix_original | 0/1 | Jetflix original. |
| is_kids_content | 0/1 | Kids content. |
| has_branched_playback | 0/1 | Interactive title. |
| studio | str | Producing studio (fictional). |
| promo_tier | str | Marketing priority assigned by the content team: `A` (big launches), `B`, `C`; NULL for older library titles. |
| available_from | date | First day on Jetflix (new seasons of a series may arrive later; see `episodes.release_date`). |
| available_until | date | Last day before the licence ended; NULL if still available. |

## 20. episodes

| Column | Type | Description |
|---|---|---|
| episode_id | int | Identifier. |
| title_id | int | Series. |
| season_number, episode_number | int | Position. |
| episode_title | str | Episode title. |
| runtime_sec | int | Runtime. |
| release_date | date | Date the episode became available (weekly-release seasons drop one episode a week). |

---

## Research sources

What real platforms record, and how it shaped the tables:

- **Netflix Member Information Request data dictionary (2021)**, https://innovation.consumerreports.org/wp-content/uploads/2022/03/Netflix-data-dictionary-2021.pdf
  Table set and column semantics: account consent flags (email, SMS transactional/informational, WhatsApp,
  matched identifiers, test participation), SubscriptionHistory (opened/closed timestamps, customer-initiated
  cancel flag, free-trial flag, plan category, max streams), billing (`Pmt Status`, `Final Invoice Result`
  values such as COMPLETED / AUTHORIZATIONS, next billing date), ViewingActivity (duration, autoplay
  `Attributes` strings, supplemental video type, bookmark and `Not latest view`), PlaybackRelatedEvents
  (start/paused/reposition/playing/stopped with session and media offsets), Ratings (thumbs values), Search
  history (query typed, action, section), My List, the "UTC everywhere" and "-1/NULL = not captured" conventions,
  and the note that tables are kept for different periods.
- **Netflix Privacy Statement**, https://help.netflix.com/legal/privacy
  Categories collected automatically: device and network identifiers, IP, connection type, app logs and
  performance data, playback events, search queries, clicks and page views, records of messages sent and
  interactions with them, customer-service communications, payment method and history.
- **The Walt Disney Company privacy policy**, https://privacy.thewaltdisneycompany.com/en/current-privacy-policy/ and
  **Hulu US state privacy rights**, https://hulu.com/your-us-state-privacy-rights
  Disney collects registration data (including optional gender and date of birth), transaction and payment
  information, device type, unique device identifiers and IP address, viewing and usage frequency,
  approximate location from IP, and communications; it offers US state rights including deletion and
  "Do Not Sell or Share My Personal Information". Used for the optional `birth_year`/`gender`,
  `ccpa_do_not_sell_share`, IP-derived `geo_state`, and purged profiles. (The Hulu URL now redirects to the
  Disney+ homepage, so the Disney policy, which covers Hulu, was the reference.)
- **KKBOX WSDM Cup 2018 churn data (Gregory, "Predicting Customer Churn: Extreme Gradient Boosting with Temporal
  Data", arXiv:1802.03396)**, https://arxiv.org/pdf/1802.03396
  Subscription-streaming schema split into members, transactions (payment method, plan days, list price,
  amount paid, auto-renew, cancel flag, transaction and expiry dates) and daily user logs; churn defined from
  the absence of a renewal after expiry. Used for the transaction-level billing table, cancel flag on the
  period, and the raw (unaggregated) activity tables.
- **Streaming QoE metrics: CTA-2066 "Streaming Quality of Experience Events, Properties and Metrics"**
  (https://shop.cta.tech/products/cta-2066, summary via https://www.forasoft.com/learn/video-streaming/articles-streaming/qoe-metrics-streaming)
  and **Dobrian et al., "Understanding the Impact of Video Quality on User Engagement"**
  (https://cacm.acm.org/research/understanding-the-impact-of-video-quality-on-user-engagement; the page
  returned 403 during research, content used from the published paper's known findings).
  Event model (playback request, start, stall, failure, rendition change) and session metrics: startup time,
  stall count and duration, played bitrate, failures, exit before video start. Buffering hurts engagement
  most; long startup times drive abandonment.
- **Antenna, "The Rise of the Show Chaser"**, https://antenna.live/post/the-rise-of-the-show-chaser
  Serial churners (3+ premium SVOD cancels in two years) are about a quarter of US streamers; 38% of serial
  churners made 3+ cancels within three months of subscribing; six-month retention 56% for non-serial
  churners vs 29% for show chasers; weighted win-back about 23% by month 3 and 41% by month 12. Used for
  rejoin as a new period on the same account and the release-driven signup spikes.
- Project documents in `docs/` (platform facts, churn definition, governance notes).
- Real device naming (Roku/Amazon/Samsung/LG model codes, Apple hardware identifiers) and US card-decline
  codes follow public conventions; ISP names are real US providers resolved from IP, as a real log would show.

## Decisions

Every assumption made while building the extract. Rates and targets are validated in `validation_report.md`.

**Scope and sample**
1. *Sample composition.* 27,900 accounts (55.8%) were active on 2025-10-01; 19,900 accounts were created during
   the window; 2,200 accounts were former subscribers before the window who came back during it. The prompt
   asked for "about half" already subscribed. 55.8% was needed so that the monthly join rate (7%) and growth
   (2%) hold with exactly 50,000 accounts, because members who churn and return inside the window add joins
   without adding accounts.
2. *Rates are measured on the sample.* The sample's active base grows from ~27,900 to ~35,000 over the year.
   This matches the rates, not the platform's absolute 100,000.
3. *Join* = any new subscription period (new account or rejoin). *Voluntary churn* = a period closed after a member
   cancel, counted in the month access ends. A cancel reversed before the renewal is not churn (matches the
   project's churn definition).
4. *History depth.* Subscription periods, billing, payment methods, membership and consent events go back to
   account creation (as far as platform launch, 2023-10-01), as a billing system keeps them. Viewing, search,
   ratings, My List, logins, support and communications cover the window only. Playback events, quality
   telemetry and clickstream keep the last 90 days (2026-07-03 to 2026-09-30), the stated retention allowance.
5. *Test accounts.* 30 `QA_TEST` and 20 `EMPLOYEE` accounts (0.1%). They are billed like members and QA accounts
   cancel and re-subscribe often (they test the flows). They are flagged in `account_type`, not removed.

**Billing and membership**
6. *Anchor and timing.* The renewal anchor is the day-of-month and time of the period's first charge; months
   without that day bill on their last day. Renewal charges post within 30 minutes of the anchor time.
7. *Cancel mechanics.* Card and PayPal members cancel by removing the payment method (`USER_CANCELLED`).
   App-store members turn off auto-renew in the store, and Jetflix learns of it from a server notification
   minutes to hours later (`STORE_AUTO_RENEW_OFF`), so those cancels have no Jetflix clickstream. Cancel
   reversal = re-adding a payment method before renewal (a new `payment_methods` row and `CANCEL_REVERSED`).
8. *Grace and dunning.* A failed renewal opens a 7-day grace period with retries on days 1, 3 and 5 (each a
   `RETRY` row), plus member updates of the payment method (a new `CHARGE`). Access continues during grace.
   The anchor does not move after a late recovery. If grace ends unpaid, the period closes at renewal + 7 days
   with `is_customer_initiated_cancel = 0`. App-store retries are logged the same way, with store failure codes.
9. *Card expiry.* Cards carry expiry dates. Before a renewal on an expired card, the network account updater
   refreshes about half (`PAYMENT_METHOD_UPDATED`, source `ACCOUNT_UPDATER`). Some members replace the card
   themselves; the rest fail with `EXPIRED_CARD`. Expiries before the window were refreshed by the updater.
10. *Verification authorisations.* Adding a card or PayPal account writes a $0.00 `VERIFY` row. Every charge and
    retry is exactly $15.99. There are no tax lines and no refunds.
11. *Signup declines.* About 2% of card/PayPal signups have a declined first card, removed and replaced within
    minutes. The subscription opens on the successful charge.
12. *Rejoin.* A returning member gets a new subscription period, a new payment method row, a new anchor and the
    same profiles and devices (profiles persist, as on Netflix).
13. *Cancels during grace* are not modelled (grace lasts 7 days and is rare).

**Product and content**
14. *Catalog.* 3,345 fictional titles (2,023 movies, 1,091 series, 121 limited series, 110 stand-up specials) and
    25,240 episodes. Some licensed titles leave the service (`available_until`). 13 big Jetflix launches in the
    window, marked promo tier `A` along with a few other titles. Two of them release weekly. All names are
    invented; a few may coincide with real titles by chance.
15. *Viewing rows.* One row per title/episode playback, like Netflix. Autoplayed previews on TVs (`HOOK`) and
    trailers are logged as supplemental views. A finished view's bookmark equals the runtime.
16. *Engagement level.* About 5 viewing hours per subscriber-month (median account ~18 hours over its months in
    the window), heavy-tailed: 3,796 accounts (7.6%) never play anything in the window. This fits a mid-tier
    service rather than Netflix (roughly 2 hours per member per day). It also keeps the extract within the
    ~1.5 GB budget while retaining all 50,000 accounts and every table.
17. *App release train.* Versions 8.9.0 to 9.4.0 with platform-specific adoption lags. Some old TV and stick
    models cannot update past 8.12.x. Version 9.0.0 (2026-02-10) added `subtitle_language` logging. Clients
    before 8.11.0 did not report stall duration (`-1`).
18. *Time zones.* Activity is generated in local time from the account's state/ZIP3 time zone, including split
    states and US DST rules, then stored in UTC. Travel changes `geo_state` in telemetry and logins.
19. *Communications.* The generic renewal reminder (3 days before renewal) and win-back (14-28 days after access
    ends) go only to email-marketing consenters, per the platform facts. Transactional messages go to everyone
    with the relevant channel. Release announcements go by email (consent), informational SMS (consent) and push
    (devices with push enabled, bigger launches only). WhatsApp consent is stored but nothing is sent. Opens
    include Apple Mail Privacy Protection pre-fetch opens.
20. *Consent state.* `accounts` holds consent flags as of extraction; changes (unsubscribe links, SMS STOP,
    settings) are in `consent_events`.
21. *Support.* Contacts come from billing problems, playback problems, login problems, and general questions.
    Jetflix has no refund policy, so `REFUND_REQUEST` contacts are common after renewals.

**Raw-data characteristics (kept at low rates)**
22. Duplicates: playback events ~0.25%, clickstream ~0.3%, a few login and viewing rows.
23. Late and out-of-order: offline/downloaded playback reports hours to days late (`server_received_ts`); ~1% of
    clickstream arrives late; ~2% of devices have skewed clocks, so `client_ts` can be minutes off or a few
    seconds past the window end.
24. Sentinels: `-1` for startup time of failed attempts, stall duration on old clients, handle time of email
    contacts, unreported OS version. NULLs where a system would not capture a value (zip3 for app-store payers,
    optional demographics, model code for browsers, CSAT not answered).
25. Messy strings: unnormalised device categories, several spellings per device model, varied app-version formats.
26. Orphans: profiles purged on request are absent from `profiles`, but their history rows remain. Quality rows
    of attempts that never started have no `view_id`.
27. Outliers: autoplay chains of many episodes on TVs, and rare stuck sessions where a TV player reports 3-12
    hours of continuous play.
28. *IDs* are integers from separate ranges per table. Within a table they increase per account. They carry no
    meaning beyond identity.

**What is deliberately not in the data**
29. No engineered fields: no churn flags, segments, scores, totals, current-status summaries, churn reasons or
    cancellation-survey answers. Everything is an operational record or a setting as stored.
