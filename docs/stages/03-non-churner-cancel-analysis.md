# Stage 3: Analysis of Cancel-and-Renew Behavior (Non-Churners)

**Date:** October 2026  
**Audited Data:** 368,267 known cycles (347,933 renewed cycles, 19,479 voluntary churn cycles) from 49,950 consumer accounts  
**Code Reference:** [`src/check_non_churner_cancels.py`](file:///c:/Users/PARTEEK/OneDrive/Documents/Projects/OTT-churn-reduction/src/check_non_churner_cancels.py)  
**Output Data:** [`results/non_churner_cancel_check.json`](file:///c:/Users/PARTEEK/OneDrive/Documents/Projects/OTT-churn-reduction/results/non_churner_cancel_check.json)

---

## 1. The Questions We Investigated

1. **Do customers who did not churn ever cancel their membership and then renew?**
2. **Is cancelling their membership a strong signal of churning, both in this dataset and in OTT generally?**

---

## 2. The Answers in Simple Language

### Question 1: Do non-churners ever cancel and then renew?
**Yes, but it is rare (under 1 in 200 cycles).**

- Out of **347,933 renewed billing cycles**, exactly **1,452 cycles** (0.42%) had a member ask to cancel and then change their mind before the renewal date.
- In every one of those 1,452 cycles (100%), the member requested cancellation (`CANCEL_REQUESTED`), kept watching until their paid period ran down, and then added back a payment method (`CANCEL_REVERSED`) before their access was cut off.
- Across individual subscribers, **1,417 subscribers** (about 2.9% of all retained subscribers) experienced a "cancel and reverse" at least once during the year.
- **How long do they stay cancelled before changing their mind?**
  - They stay in the "cancelled" state for a median of **10.0 days** (mean: 11.4 days; 25th percentile: 5.1 days; 75th percentile: 17.0 days).
  - This shows members are not just "misclicking" and undoing it 10 seconds later. They deliberately turn off auto-renew, wait a week or two, and then change their mind right before the renewal deadline.

---

### Question 2: Is cancelling membership a strong signal of churning?
**Yes — it is an overwhelmingly powerful, near-certain signal of churn.**

When a member clicks "Cancel Membership" during their billing cycle:
- **93.1%** go on to churn and lose access (`VOLUNTARY_CHURN`).
- Only **6.9%** reverse their cancellation and stay (`RENEWED`).

To put this into perspective:
- **Baseline churn rate:** In any normal billing cycle, only **5.29%** of subscribers churn.
- **If a member does NOT cancel:** Their churn rate is almost zero (**0.00087%**, or less than 1 in 100,000).
- **If a member DOES cancel:** Their churn rate jumps to **93.06%**.
- **Lift:** Cancelling gives a **17.6x lift** over the average churn rate.
- **Relative Risk:** A member who cancels is **over 100,000 times more likely** to leave than someone who has not cancelled.

At the lifetime subscription level (across all 61,218 customer subscriptions):
- 26,937 subscriptions ever had a cancellation request.
- **25,141** of them (**93.3%**) closed permanently.
- Only **1,772** (**6.6%**) reversed and continued their subscription.

---

## 3. Why This Makes Sense (Industry & Platform Context)

In subscription streaming services like Netflix or Jetflix:
1. **Subscriptions renew automatically.** A customer cannot churn "by accident" or through inaction. To leave, they must deliberately navigate to Account Settings and confirm cancellation.
2. **Cancel is an explicit declaration of intent.** Unlike subtle behavioral hints (e.g., watching 30 minutes less TV this week), pressing the cancel button is the customer explicitly telling the platform: *"I do not want to pay for another month."*
3. **Industry Benchmarks:** In subscription media, 85% to 95% of users who turn off auto-renew let the subscription expire, while 5% to 15% change their mind (prompted by winback emails, new show releases, or reminder notices). The **93.1% conversion to churn** in this dataset perfectly reflects real-world subscriber behavior.

---

## 4. What This Means for Our Machine Learning Model vs Rule Layer

This finding directly confirms the core architecture established in [Stage 0: Problem Framing](file:///c:/Users/PARTEEK/OneDrive/Documents/Projects/OTT-churn-reduction/docs/stages/00-problem-framing.md):

| Customer State at Prediction Time ($T$) | How Many? | What Happens? | Who Handles Them? |
|---|---|---|---|
| **Already Cancelled at $T$** (`cancelled_at_T == True`) | 13,047 cycles (3.5% of cycles) | **93.1% will churn** if nothing is done; 6.9% save themselves. | **Separate Business Rule Layer:** Immediate card-removal save flow / winback offer. Do not waste ML score on them. |
| **Not Cancelled at $T$** (`cancelled_at_T == False`) | 355,220 cycles (96.5% of cycles) | Churn rate is low (2.0% in final 10 days), but hard to spot. | **Predictive ML Model:** Rank active users by churn risk so Jetflix can intervene *before* they ever hit the cancel button. |

### Summary of Guardrails
1. **Do not use the ML model to predict churn on users who already cancelled.** It is not an ML problem when 93% leave — it is a business intervention problem.
2. **Train the ML model only on active, uncancelled subscribers at $T$.** This ensures the model learns the true warning signs (drop in viewing hours, login frequency, playback errors) rather than taking a shortcut on the cancel button.

