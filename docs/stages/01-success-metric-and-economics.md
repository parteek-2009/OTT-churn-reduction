# Success Metric and Economics (Stage 1)

**Status:** the churn definition is done. The remaining sections are completed after the
data is built, because they depend on what the data shows and on how the rule layer is designed.

## What this file contains
1. Churn definition
2. Prediction window
3. Inputs from the platform file
4. Value of a saved user
5. Cost of an offer
6. Break-even
7. Business metrics
8. Model metrics
9. Guardrails

## Status

| Section | Status | Completed after |
|---|---|---|
| Churn definition | Done | |
| Prediction window | Open | Data is built and explored (Stage 2-3) |
| Inputs | Done | |
| Value of a saved user | Open | Data is built (how long saved users stay) |
| Cost of an offer | Open | Rule layer is designed (Stage 7) |
| Break-even | Open | Value of a saved user and cost of an offer are set |
| Business metrics | Open | Baseline is built (Stage 3) |
| Model metrics | Open | Baseline is built (Stage 3) |
| Guardrails | Open | Rule layer is designed (Stage 7) |

At the end of each stage, run the 4C check. If the economics change, update this file.

---

## 1. Churn definition

**Churner:** a subscriber who cancels their membership (removes the card) and does not
renew at the next renewal.

**Not a churner:** a subscriber who renews. This includes someone who cancelled and then
changed their mind before renewal.

**Excluded:** declined or failed payments. These are payment problems, not decisions to
leave, so the model covers voluntary churn only.

### How it plays out
- Jetflix renews automatically. To leave, a user cancels membership by removing their card.
- A user can do this at any point in the billing month, even one day before renewal,
  so the cancel date varies from user to user.
- Access continues until the end of the paid month. If no payment is received at renewal,
  access ends, and that confirms the churn.

### Who is scored
Active subscribers who have not yet cancelled at the scoring moment. Users who have already
cancelled are not scored, because the decision is made. The rule layer handles them
with the card-removal trigger described in the problem framing.

### Why this definition
- It matches how Jetflix works: automatic renewal, and leaving by removing the card.
- The target is clear and always recorded: a cancel event followed by no renewal.
- Voluntary churn only gives a clean target. Payment failures need a different fix.
- Changes of mind are handled: a user who cancels and then renews is not a churner.

## 2. Prediction window

How many days before renewal the model scores each user.

**To be completed after the data is built.** It is decided from the data (when users
actually cancel in the billing month) and from how users behave, balancing time to act
against how clear the signals are.

## 3. Inputs from the platform file

| Item | Value |
|---|---|
| Price | $15.99 per month |
| Subscribers | 100,000 |
| Churn rate | 5% per month (5,000 users) |
| Cost to serve | $3.80 per user per month |
| Margin per user | $12.19 per month (76%) |
| CAC | $70 |
| Expected lifetime | 20 months |
| LTV | $244 |

## 4. Value of a saved user

What one user is worth if the model helps keep them: margin per month times the number of
extra months they stay.

**To be completed after the data is built.** Saved users are at higher risk than average,
so they probably stay fewer months than the 20-month average. The data shows how many.

## 5. Cost of an offer

What it costs to give one flagged user an offer, including discounts given to users who
would have stayed anyway.

**To be completed after the rule layer is designed.** The offers are decided there.

## 6. Break-even

The share of flagged users an offer must save to pay for itself:
offer cost divided by the value of a saved user.

**To be completed after sections 4 and 5 are set.**

## 7. Business metrics

How success is judged in money terms: churn of flagged users compared with a control group,
incremental saves, and net profit per month after offer costs.

**To be completed after the baseline is built.**

## 8. Model metrics

How the model is judged: for example, precision at the top of the ranked list, recall, and
improvement over the v0 baseline.

**To be completed after the baseline is built.**

## 9. Guardrails

Side effects that would cancel a win: more cancellations when a discount ends, users
cancelling just to get an offer, message fatigue, and offer spending that drains profit.

**To be completed after the rule layer is designed.**