# 4A Summary: OTT Business Understanding

Industry knowledge needed before Stage 1 of the OTT churn project.

---

## 1. How OTT makes money

- **Subscription (SVOD):** the user pays a recurring fee (Netflix, Prime Video).
- **Advertising (AVOD):** content is free and advertisers pay (YouTube, free tiers).
- **Hybrid:** a cheaper tier with ads next to an ad-free premium tier.

## 2. Key terms

| Term | Meaning | Formula |
|---|---|---|
| Churn rate | Share of subscribers lost in a period | lost ÷ subscribers at start |
| Retention | Share still subscribed after a period | 1 − churn |
| ARPU | Average revenue per user | revenue ÷ average subscribers |
| CAC | Cost to acquire one subscriber | acquisition spend ÷ new subscribers |
| LTV | Lifetime value of a subscriber | ARPU × margin × lifetime |

- Expected lifetime ≈ 1 ÷ monthly churn (for eg. 5% monthly churn means about 20 months).
- ARPU is blended across tiers, so it hides segment differences.
- The 1/churn shortcut assumes constant churn, but real churn is highest early in a subscriber's life.its just for first guess and a baseline. 

## 3. Revenue formula

**Revenue ≈ subscribers × ARPU × months they stay**

Example (made-up numbers): ARPU ₹150/month.
- At 5% monthly churn, lifetime is 20 months, so revenue per subscriber is ₹3,000.
- At 4% monthly churn, lifetime is 25 months, so revenue per subscriber is ₹3,750 (**+25%**).

One percentage point of churn is worth a 25% gain in lifetime revenue. This is the business case for the project.

## 4. Cost structure

- **Content:** the largest cost and mostly fixed, so it does not grow with subscriber count.
- **Streaming infrastructure:** CDN, bandwidth, encoding. Scales with usage.
- **Marketing and acquisition:** this is CAC.
- **Payment fees, support, tech and people:** smaller but real.

Because content is already paid for, keeping a subscriber is cheap and winning a new one is expensive. That makes retention high-margin. A retention offer is worth giving only if **the value of the saved user exceeds the cost of the offer**, including discounts given to people who would have stayed anyway.

## 5. Voluntary vs involuntary churn

- **Voluntary:** the user decides to cancel or not renew. Fixes: content, offers, nudges, plan changes.
- **Involuntary:** a payment fails (expired card, low balance, bank decline, mandate failure) and the user never meant to leave. Fixes: payment retries, reminders, easy payment-method updates.

The two need different treatments. A discount for a failed card is wasted money, and a payment reminder does nothing for a bored user.

## 6. Subscription mechanics

- **Billing cycle:** the period the user has paid for.
- **Renewal:** automatic (saved mandate) or manual (user must recharge). Manual renewal gives a naturally higher lapse rate.
- **Failed payment and grace period:** platforms retry for some days and keep access active (dunning).
- **Cancel flow:** cancelling usually stops the *next* renewal, and the user keeps access until the period ends.
- **Pause, downgrade, win-back:** other exits and re-entries that the churn label must handle.



## 7. Why OTT users churn (hypotheses to test in Stage 2-4)

| Reason | Feature it hints at |
|---|---|
| Price vs perceived value | Plan tier, price changes, discount history |
| Content gap | Declining watch time, days since last session |
| Finished the show | Last-episode completion |
| Streaming quality | Buffering rate, playback errors |
| Payment problems | Failed payments, retry count |
| Competitors or bundles | Hard to see directly; use proxies |
| Seasonality and events | Signup month, big-event cohorts, tenure |

Treat these as hypotheses, not facts. Check which ones your data can actually see.

## 8. Privacy rules (Stage 2)


- **Consent and purpose:** use data only for what the user agreed to.
- **Data minimization:** don't collect or use more than needed.
- **Withdrawal and erasure:** users can withdraw consent or request deletion.
- **Marketing contact rules:** opt-ins and opt-outs apply to SMS, WhatsApp, and email offers.

This decides which features the model may use and whom the rule layer may contact. The rules are still being phased in, so confirm the current position with compliance.

## 9. Offers and discount practices (Stage 7)

Typical retention offers: a discounted month or two, a free period, a cheaper plan, a pause option, a bundle, or a non-monetary nudge ("new season just dropped").

- Targeted, time-limited offers beat blanket discounts.
- **Offer gaming:** users learn that cancelling triggers a discount and cancel on purpose.
- **Wasted discounts:** money given to people who would have stayed anyway.
- **Price shock:** many users churn when the discount ends.

This is why the roadmap separates the churn model (who is at risk) from the rule layer (what to do about it).

---

## Carry into Stage 1

1. Churn controls the "months they stay" term, and retention is high-margin because content cost is fixed.
2. Offers cost money, so you need break-even math.
3. Voluntary and involuntary churn need different fixes. Decide how to handle them.
4. The churn event lags the real decision, so define churn and the prediction window deliberately.
5. Privacy and offer gaming limit what the system is allowed to do.
