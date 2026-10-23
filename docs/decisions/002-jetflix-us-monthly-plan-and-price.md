# 002: Jetflix US offers one monthly plan at $15.99

**Date:** 2026-10-22
**Status:** Accepted
**Stage:** 0-1 (problem framing, success metric and economics)
**Related:** [001 scope to one region](001-scope-v1-to-one-region.md)

## Decision
Jetflix (a fictional, Netflix-like platform) sells one ad-free Standard plan in the US:
**monthly billing at $15.99 per month**. No 3-month, 6-month, or 12-month plans in v1.

## Context
Jetflix is a portfolio project, not a real app, so the pricing is an assumption.
It still needs to be realistic, because the economics later in the project
follow from it. The platform is scoped to the US region (see decision 001).

## Alternatives considered
1. **Four plan lengths (1, 3, 6, 12 months):** $15.99 / $44.99 / $84.99 / $149.99.
2. **Monthly + annual only:** $15.99 and $149.99 (about 22% off) or $159.99 (about 17% off).
3. **Monthly only (chosen).**

## Why monthly only
- **It matches the market.** Netflix's US help center says it does not offer
  annual, multi-month, or lifetime plans.
- **Long plans are rare industry-wide.** Antenna estimated that only about 4% of
  subscriptions across 41 SVOD services were annual plans at the end of Q1 2024.
  This is older data, so treat it as a ballpark.
- **No market data exists for 3 and 6-month plans.** Any share given to them
  would be a guess.
- **Long-plan groups would be too small to model.** With 100,000 subscribers and a
  realistic mix (mostly monthly), long plans would produce only about 3% of renewal
  decisions each month, because those users decide only every 3 to 12 months.
- **It makes the churn problem cleaner.** Every user decides every month, so one
  churn definition and one prediction window apply to everyone, and all 100,000
  users contribute a renewal decision each month.

## Why $15.99
- Netflix's US ad-free Standard plan is $19.99/month, so $15.99 is below the
  market leader.
- Antenna reported the average price paid for ad-free plans at about $13.88 in
  early 2025, so $15.99 is above the average.
- It sits between the two, which makes it believable for a Netflix-like platform.

## Consequences
- Average revenue per user equals the plan price, so no plan mix is needed.
- Offers in the rule layer cannot include a switch to a longer plan.
- Plan and price are kept in config, so adding plan lengths later does not
  require rewriting the pipeline.

## Sources
- Netflix Help Center, Plans and Pricing (US): https://help.netflix.com/pt-pt/node/24926/us
- Antenna, Understanding the Relationship Between Annual Plans and Promotions:
  https://www.antenna.live/insights/understanding-the-relationship-between-annual-plans-and-promotions
- Antenna, Q1'25 State of Subscriptions Report (average price paid):
  https://antenna.live/insights/antenna-q125-state-of-subscriptions-report-premium-svod-2024-year-in-review