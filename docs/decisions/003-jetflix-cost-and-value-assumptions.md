# 003: Jetflix cost and value assumptions

**Date:** 2026-10-23
**Status:** Accepted
**Stage:** 0-1 (problem framing, success metric and economics)
**Related:** [001 scope to one region](001-scope-v1-to-one-region.md),
[002 monthly plan and price](002-jetflix-us-monthly-plan-and-price.md),
[Jetflix platform](../About-OTT-Jetflix.md),
[Domain knowledge](../Domain_knowledge.md)

## Decision
Use these values for Jetflix's economics:

| Item | Value |
|---|---|
| Subscribers | 100,000 (7% join and 5% churn per month) |
| Cost to serve | about $3.80 per user per month (payment $1.50, delivery $1.50, support and tech $0.80) |
| Margin per user | about $12.19 per month (about 76%), variable costs only |
| Cautious margin check | about 49% (gross margin, after a share of content cost) |
| CAC | about $70 |
| LTV | about $244 (margin x 20-month lifetime) |
| LTV:CAC | about 3.5 (about 2.2 at the cautious margin) |
| Content | 30% of revenue (assumption) |
| Overhead | 8% of revenue (assumption) |
| Operating profit | about $121,000 per month (7.6% of revenue) |

## Context
Jetflix is fictional, so these numbers are assumptions. They still need to be realistic,
because the break-even math for retention offers (Stage 1) depends on them, and the
company needs to be profitable for the project's story to make sense.
They were checked against Netflix's 2025 SEC filings and industry benchmarks.

## Alternatives considered
**Margin**
1. **Operating margin (about 29.5%, Netflix 2025):** rejected. It includes marketing and
   overhead, which do not change when one user is saved.
2. **Gross margin (about 49%):** kept as a cautious check, not the base case. It charges
   every user a share of content cost, even though content is mostly fixed.
3. **Marginal margin (about 76%, chosen):** matches the question the project asks,
   which is what one saved user is worth.

**CAC**
1. **$60 (my first guess):** rejected, below the industry range found.
2. **$68 (median for streaming and media subscriptions):** the low end of the range.
3. **$70 (chosen):** just above the median and inside the range found ($68-$110).
   It leaves Jetflix comfortably profitable.
4. **$85:** considered first, inside the $80-$110 range reported for entertainment and
   streaming brands. Rejected because it left operating profit at only about 1%.
5. **$110 or more:** the top of the range, and too pessimistic for a platform
   growing 2% a month.

**Number of subscribers**
1. **50,000:** with the placeholder content and overhead costs, it gave a small loss.
2. **100,000 (chosen):** gives the model about 5,000 churners a month to learn from.

**Company-level costs**
1. **Content 35% and overhead 10% (first placeholders):** gave a loss at 50,000 users.
2. **Content 30% and overhead 8% (chosen):** assumptions, with content set a little
   below Netflix's roughly 36% because Jetflix is much smaller. Overhead has no source.

## Why these numbers
- **Payment, about $1.50:** card payments cost 2.9% plus $0.30 per charge (about $0.76 on
  $15.99), and app-store billing costs 15-30% ($2.40-$4.80). Assuming about a third of
  users pay through app stores gives a blend of about $1.50.
- **Delivery, about $1.50:** one hour of 1080p video is about 2.25 GB, and CDN rates run
  from about $0.005 to $0.02 per GB and up. This gives about $0.70-$2.70 per user per month,
  depending on how much they watch. The suggested value sits in the middle.
- **Support and tech, about $0.80:** no good source found. This is an assumption.
- **Margin is variable costs only** because content (the largest cost) is paid for
  whether or not one user stays. This is the same logic as in the domain notes.
- **Cross-check:** Netflix's cost of revenues was about 51% of revenue in 2025, and most of
  that is content amortization (about 36% of revenue). The rest, which includes delivery,
  payments and support, is about 15%. A smaller platform pays more per user, so about 24% for
  Jetflix is consistent.
- **100,000 subscribers:** the main reason is data. At 5% churn, 5,000 users leave each
  month, which gives the model more examples than 50,000 subscribers would. The user count
  does not create profit by itself, because when every cost is a share of revenue the profit
  margin stays the same at any size. Profit comes from the CAC, content and overhead
  assumptions.
- **LTV:CAC of about 3.5** is above the common 3:1 benchmark, so Jetflix is plausible
  as a sustainable platform.

## Company view (per month)
| Line | Amount | % of revenue |
|---|---|---|
| Revenue (100,000 x $15.99) | $1,599,000 | 100% |
| Cost to serve | -$380,000 | 24% |
| Content | -$479,700 | 30% |
| Gross profit | $739,300 | 46% |
| Acquisition (7,000 x $70) | -$490,000 | 31% |
| Overhead | -$127,920 | 8% |
| **Operating profit** | **$121,380** | **7.6%** |

## Consequences
- A saved user is worth about $12.19 per month of margin, which sets the ceiling for
  offer cost in the break-even math.
- At the cautious 49% margin, LTV:CAC drops to about 2.2, so the break-even math should be
  run with both margins.
- Acquisition costs about $490,000 per month, and replacing the 5,000 users who churn
  costs about $350,000 of it. This supports the case for retention.
- Jetflix has a cushion before it turns to a loss. Profit reaches zero at a CAC of about
  $87, content at about 37.6% of revenue, or overhead at about 15.6% of revenue.
- With about 1,150 churners a week, outreach capacity will need to be set well above the
  earlier placeholder when the capacity block is decided.

## Open items
- Support and tech cost has no source.
- The one-third app-store share is an assumption.
- Content (30%) and overhead (8%) are assumptions. Overhead has no source.

## Sources
- Netflix Form 10-K, FY2025 (operating margin 29.5%):
  https://www.sec.gov/Archives/edgar/data/1065280/000106528026000034/nflx-20251231.htm
- Netflix Form 10-Q, Q3 2025 (cost of revenues as a share of revenue):
  https://www.sec.gov/Archives/edgar/data/1065280/000106528025000406/nflx-20250930.htm
- Netflix filings analysis (content amortization about 36% of revenue):
  https://sec-api.io/insights/financial-analysis-of-netflix-q2-2026-filings-and-scenarios-to-2029
- CAC benchmarks by industry, 2026 (streaming median $68):
  https://www.digitalapplied.com/blog/customer-acquisition-cost-benchmarks-2026-industry
- CAC ranges for entertainment and streaming ($80-$110):
  https://www.chargebee.com/blog/understanding-cac-relevance-saas-company/
- Deloitte, streaming services and churn (marketing spend per subscriber):
  https://www.deloitte.com/us/en/insights/industry/technology/video-streaming-services-churn-rate.html
- OTT CDN costs:
  https://setplex.com/resource-hub/ott-cdn-costs
- Video streaming egress cost per viewer-hour:
  https://egresscost.com/use-cases/video-streaming
- Apple and Stripe fee rates:
  https://www.builtbyfoundry.io/blog/app-link-out-checkout-6-rates-2026