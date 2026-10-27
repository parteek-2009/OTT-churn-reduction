# 18 — communications_log

## What is this dataset?

All **outbound messages** sent to members — emails, SMS, and push notifications. Full analysis
window.

## What does one row represent?

One row = one message sent to one account.

## Size

| Fact | Value |
|---|---|
| Rows | 893,619 |
| Columns | 13 |
| Memory (approx.) | 453.78 MB |

Expected: ~893,619 rows.

## Important columns

- **`message_id`** — unique ID. Primary key.
- **`account_id`** — the account that received the message.
- **`channel`** — `EMAIL`, `SMS`, or `PUSH`.
- **`message_type`** — the type of message:
  - *Transactional* (sent regardless of consent): `WELCOME`, `WELCOME_BACK`,
    `CANCEL_CONFIRMATION`, `PAYMENT_DECLINED`, `PAYMENT_METHOD_EXPIRING`.
  - *Consent-based*: `RENEWAL_REMINDER`, `NEW_ON_JETFLIX_DIGEST`, `NEW_RELEASE`, `WINBACK`.
- **`sent_ts`** / **`delivered_ts`** — when sent and delivered.
- **`bounce_type`** — `SOFT`, `HARD`, or `TOKEN_INVALID` when delivery failed.
- **`opened_ts`** / **`clicked_ts`** — engagement with the message.
- **`unsubscribed_ts`** — when the member unsubscribed via this message.
- **`device_id`** — target device for PUSH messages.

## Date ranges

- `sent_ts`: 2025-10-01 to 2026-09-30
- `delivered_ts`: 2025-10-01 to 2026-10-01

## Missing values

| Column | Missing count | Missing % |
|---|---|---|
| `unsubscribed_ts` | 892,993 | 99.93% |
| `bounce_type` | 876,372 | 98.07% |
| `clicked_ts` | 866,810 | 97.0% |
| `device_id` | 787,904 | 88.17% |
| `opened_ts` | 589,610 | 65.98% |

> Most timestamp columns (`delivered_ts`, `opened_ts`, `clicked_ts`, `unsubscribed_ts`) are NULL
> when that event did not occur — expected.

## Duplicate rows

Fully duplicated rows: **0** (0.0%)

## Channel distribution

  - `EMAIL` — 746,830 (83.6%)
  - `PUSH` — 105,702 (11.8%)
  - `SMS` — 41,087 (4.6%)

## Message type distribution

  - `NEW_RELEASE` — 387,515 (43.4%)
  - `NEW_ON_JETFLIX_DIGEST` — 224,136 (25.1%)
  - `RENEWAL_REMINDER` — 213,674 (23.9%)
  - `CANCEL_CONFIRMATION` — 21,508 (2.4%)
  - `WELCOME` — 19,900 (2.2%)

## Potential relationships

- `account_id` → `accounts`.
- `device_id` → `devices` (for PUSH messages only).

## Anything unusual?

- **Apple Mail Privacy Protection** pre-fetches emails, which records an `opened_ts` a few seconds
  after delivery whether or not the user actually read the message. Email open rates are therefore
  inflated and unreliable as a true engagement signal.
- Win-back messages (`WINBACK`) are sent 14–28 days after access ends, only to email-marketing
  consenters.
- WhatsApp consent is collected but no WhatsApp messages are sent (no rows with `channel = WHATSAPP`).

## What can this dataset help us understand?

- Whether communications (renewal reminders, win-back) affect re-subscription rates.
- Email/SMS engagement as a predictor of churn or retention.
- How message delivery failures (bounces) relate to account status.
