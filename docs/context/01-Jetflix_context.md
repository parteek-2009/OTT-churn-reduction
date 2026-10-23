# Jetflix: How the Platform Works (US, v1)

Jetflix is a fictional, Netflix-like streaming platform built for a portfolio project.
Every value below is an assumption set for this project, not real data.

## Basics
- **Region:** United States (USD)
- **Platform age:** 3 years

## Plan and pricing
- One ad-free Standard plan, billed monthly only
- **Price:** $15.99 per month

## Billing
- Renewal is automatic, charged every month on the signup date.
- The payment gateway is reliable, so failed payments are rare.
- The platform already handles users who try to exploit the grace period.
- If a failed payment is not recovered by the end of the grace period, access ends.

## Cancelling
- Cancelling stops the next renewal. Access continues until the end of the paid month.

## Size and growth
- **Subscribers:** 100,000
- **New user rate:** 7% per month
- **Churn rate:** 5% per month (voluntary churn)
- **Net growth:** 2% per month

## Derived numbers
These follow from the values above. They are not separate assumptions.

| Item | Value |
|---|---|
| New users per month | 7,000 |
| Churned users per month | 5,000 (about 1,150 per week) |
| Net change per month | +2,000 |
| Subscribers after one year | about 126,800 |
| Monthly revenue | about $1.6 million |
| Yearly revenue | about $19.2 million |
| Revenue lost to churn per month | about $80,000 |
| Expected lifetime | 20 months (1 / 0.05) |

## Scope of the model
- The model predicts **voluntary churn only**. Involuntary churn from payment failure is out of scope.

## Costs and value
All values are assumptions, informed by industry benchmarks and Netflix's 2025 SEC filings.
See decision 003 for the reasoning and sources.

### Cost to serve (per user, per month)
- **Payment processing:** about $1.50
- **Streaming delivery:** about $1.50
- **Support and tech:** about $0.80 (assumption)
- **Total cost to serve:** about $3.80 (about 24% of the $15.99 price)

### Margin
- **Margin per user:** about $12.19 per month (about 76%), counting variable costs only.
  Content is excluded because it is mostly fixed.
- **Cautious check:** gross margin of about 49%, which charges each user a share of content cost.

### Acquisition and value
- **CAC:** about $70 per new subscriber (industry median is about $68, range $68-$110)
- **LTV:** about $244 (margin per user x 20-month expected lifetime)
- **LTV:CAC:** about 3.5 (about 2.2 at the cautious margin)
- **Acquisition spend:** about $490,000 per month (7,000 new users x $70)
- **Cost to replace churned users:** about $350,000 per month (5,000 x $70)

### Company-level costs
- **Content:** 30% of revenue (assumption; Netflix spends about 36% for reference)
- **Overhead** (technology, product, management, finance): 8% of revenue (assumption, no source)

## Company view (per month)

| Line | Amount | % of revenue |
|---|---|---|
| Revenue (100,000 x $15.99) | $1,599,000 | 100% |
| Cost to serve | -$380,000 | 24% |
| Content | -$479,700 | 30% |
| **Gross profit** | **$739,300** | **46%** |
| Acquisition | -$490,000 | 31% |
| Overhead | -$127,920 | 8% |
| **Operating profit** | **$121,380** | **7.6%** |

Jetflix is profitable, at about $1.46 million a year. Acquisition is the largest cost after
content, and replacing churned users accounts for about $350,000 of it, which is why
reducing churn matters.