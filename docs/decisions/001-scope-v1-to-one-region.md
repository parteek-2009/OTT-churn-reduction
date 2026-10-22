# 001: Scope v1 to one region

**Date:** 2026-10-22
**Status:** Accepted
**Stage:** 0-1 (problem framing, success metric and economics)

## Decision
Build v1 of the churn model using data from one region only: [REGION : UNITED STATES].

## Context
The platform is worldwide. Plans, pricing, currency, affordability, holidays,
user behavior, payment methods, and privacy rules differ by region.

## Alternatives considered
1. **All regions in one model, no region feature:** ignores real differences
   in behavior and price, and makes the economics meaningless.
2. **One model with region as a feature:** possible, but economics (ARPU, offer
   cost, break-even) still differ per region, and each region needs enough data.
3. **Separate model per region from the start:** more build and maintenance
   cost before we know the approach works.

## Why this option
- Keeps the churn definition, economics, and evaluation clean.
- Regional differences are large enough that generalizing early would be
  guesswork.
- Lets us finish and validate the full pipeline once before repeating it.

## Consequences
- The model is not claimed to work for other regions.
- Region-specific values (currency, holiday calendar, price table, prediction
  window, offer costs) live in config, not hard-coded.
- Extending to a new region is a hypothesis to validate, not a given. It needs:
  retraining, re-checking the churn definition, new economics and threshold,
  region holidays, and consent rules.
