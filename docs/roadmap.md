# Roadmap: OTT Churn Reduction

**Goal:** increase OTT revenue by reducing churn
**Deliverable:** churn probability model + separate rule layer on top

---

## 1. Machine Learning Life Cycle

1. Business understanding
2. Data understanding
3. Data preparation
4. Modeling
5. Evaluation
6. Deployment
7. Online experiments
8. Monitoring and maintenance
9. Iterate or retire

Development cycle (inside 3-5): prepare data → engineer features → train → evaluate → error analysis → repeat

---

## 2. How to use this file

For every stage: check entry → do the work → check exit (including 4C) → update status and log decisions in `docs/decisions/`

---

## 3. Problem Framing 

- Target
- Problem
- What is needed
- Scope

---

## 4. Business Understanding

Two parts: **4A** is general industry knowledge to study (just enough, not a deep dive). **4B** is what to define and check in this project specifically. **4C** is the short check to run at the end of every stage.

### 4A. Industry: what to study

| Topic | What to learn | Study before |
|---|---|---|
| How OTT makes money | Subscription, ads, hybrid, plan tiers | Stage 1 |
| Key terms | ARPU, churn, CAC, LTV, retention | Stage 1 |
| Revenue formula | Subscribers × ARPU × how long they stay | Stage 1 |
| Cost structure | Content, streaming infrastructure, marketing | Stage 1 |
| Voluntary vs involuntary churn | Cancelling by choice vs payment failure | Stage 1-2 |
| Subscription mechanics | Billing cycle, renewal, grace period, card failure, cancel flow | Stage 2 |
| Why OTT users churn | Price, lack of content, finished a show, streaming quality, payment issues, competitors, seasons/big events | Stage 2-4 |
| Privacy rules for user data | Consent, opt-outs, what data is allowed (e.g. DPDP in India) | Stage 2 |
| Offer and discount practices | What works, what trains users to wait for discounts | Stage 7 |

### 4B. Project: what to define and check in the model

| Item | What to define or check | When |
|---|---|---|
| Churn definition and prediction window | What counts as churn, how many days ahead we predict | Define Stage 1, re-check after Stage 2 |
| Economics | Cost of an offer, value of a saved user, break-even | Define Stage 1, refine after Stage 3, re-check Stage 6 |
| Metrics | Model metrics and business metrics | Define Stage 1, measure Stage 6 and 8 |
| Guardrails | Side effects that would stop a "win" | Define Stage 1, check Stage 7, 8, 10 |
| Leakage | Every feature is known at prediction time | Stage 2, 4 |
| Limited capacity (ranking) | How many users we can act on, evaluate the top of the list | Stage 3 (validation), 6 |
| Predict churn vs who can be saved | v1 targets by risk, uplift later | Stage 5, revisit Stage 11 |
| Cost to serve | Model is cheap enough for the value it creates | Stage 5, 9 |
| Cost-based threshold | Cut-off chosen from cost vs profit | Stage 6 |
| Offer gaming | Rules so users don't cancel just to get a discount | Stage 7 |
| Follow-up fatigue | Cap on follow-ups | Stage 7, 8 |
| Privacy and consent | Allowed data, opt-outs | Stage 2, 4, 9 |
| Ownership after launch | Who maintains the model and rules | Stage 9-10 |

### 4C. Check at the end of every stage

1. Is it still the same problem as defined in Stage 1?
2. Did I learn anything that changes the economics or the metric?
3. Could this stage's output break a guardrail?

If something is off (the problem drifted, the economics changed, or a guardrail is at risk), go back, update Stage 1 or 4B, and log the reason in `docs/decisions/`.

---

## 5. Stages

-  0. Problem framing
-  1. Success metric and economics
-  2. Data understanding
-  3. EDA and baseline
-  4. Feature engineering
-  5. Modeling
-  6. Evaluation and threshold
-  7. Rule layer (business logic)
-  8. Online experiments (shadow, A/B)
-  9. Deployment
-  10. Monitoring and maintenance
-  11. Iterate or retire



Location: `docs/decisions/` (one file per decision: decision, alternatives, why)