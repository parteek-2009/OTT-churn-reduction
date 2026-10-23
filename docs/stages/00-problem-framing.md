# Problem Framing: OTT Churn Reduction

## Target

Increase OTT revenue by reducing subscriber churn.

## Problem

We can't tell in advance which subscribers will leave, so we can't act on them before they do. We also can't give an offer to everyone: offers cost money, so we need to know who to prioritize.

## What is needed

**Output:** a churn probability for each user, with the probability meaning how likely that user is to churn within a defined window before renewal.

**Use of the output:** a separate rule layer takes the probability (plus other signals, such as card removal and usage health) and decides the action: which group the user falls into, which offer to show, and all.

**Scope:**
- ML part: produce the churn probability only.
- Business logic (outside the model): card-removal trigger, user groups, offers, follow-ups.