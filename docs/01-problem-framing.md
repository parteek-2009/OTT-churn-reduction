# Problem framing
 
## The business problem
 
I'm the lead AI engineer at an OTT platform. In a leadership meeting, the goal for the next phase is set: increase revenue. The question then comes to me: what should we do?
 
## Step 1: Where can revenue come from?
 
Lets assume after doing some discussions we currently have 6 levers,
 
1. Acquire more subscribers.
2. Raise the subscription price.
3. Reduce churn (keep the users we already have).
4. Win back users who already left.
5. Cut costs (content spend, streaming infrastructure). This improves profit, not revenue.
6. Shorten the subscription period (shorter plans).
## Step 2: Ruling out what doesn't fit right now
 
**Acquisition.** Mostly a marketing task. If the platform already has good marketing, an AI team probably shouldn't start here.
 
**Price.** Risky, and not something we can act on right now.
 
**Win-back.** Much harder. These users may have settled on another platform, or left for reasons we don't control.
 
**Costs.** Most of the spend goes into marketing and other areas where the owning teams already know what they're doing. I'd still validate that assumption.
 
**Shorter plans.** This would hurt. Our OTT is well known, so I'd expect heavy backlash on social media.
 
That leaves churn. Keeping a user who is about to leave is more achievable than the other options, and data and ML can help with it directly.
 
## Step 3: First attempt at framing churn
 
To stop customers from churning, I first need to know which ones are going to.
 
My first idea was binary classification. Predict churn (yes or no) for each user, then send discounts and offers to everyone flagged "yes".
 
## Step 4: First improvement, since users differ
 
That treats every flagged user the same, but they aren't the same. Some have a low chance of churning, and a small nudge may keep them. Others have a high chance and may need something stronger. A yes/no label throws that information away.
 
So I changed the framing to probabilistic classification. We still train on churn yes/no labels, but we use the predicted probability of churning instead of the hard label. Users are grouped into risk tiers (high, medium, low) with different urgency thresholds, and an automated pipeline sends the offers. The business team designs the exact discounts for each tier.
 
At this point the goal looked clear: give every user a churn probability.
 
## Step 5: The gap
 
While thinking through the offers, I hit a problem. A high churn probability doesn't tell us whether an offer will change that user's decision.
 
Users fall into four types:
 
| Type | Behavior | Value of an offer |
|---|---|---|
| Persuadables | Would churn without an offer, stay with one | Target these |
| Sure things | Stay either way | Wasted discount |
| Lost causes | Leave either way | Wasted discount |
| Sleeping dogs | Would have stayed, but the offer prompts them to cancel | Actively harmful |
 
A user with a 95% churn probability could be a lost cause, and a discount on them is wasted money. So I was asking the wrong question. It should be "who will the offer actually change?" instead of "who will churn?"
 
## Step 6: Finding who the offer changes
 
We can't look at one user and say which type they are. We'd have to see the same person both with an offer and without one, and each person only lives one version.
 
So we work with groups, using an experiment:
 
1. Pull out the users whose churn probability is above the threshold.
2. Split them into risk groups (for example 90%+, 70-90%, 50-70%).
3. Inside each group, give half the users an offer and the other half nothing.
4. Compare how many users stay in each half.
The difference in stay rate between the two halves tells us how much the offer helped that kind of user.
 
The comparison has to be offer group against no-offer group at the same time, because a before/after comparison can't separate the offer from everything else that changes over time (new shows, seasons, holidays).
 
## Step 7: Using the results
 
1. For each risk group, calculate the gain: stay rate with the offer minus stay rate without.
2. Check whether the gain is worth the offer's cost, compared to the revenue kept by retaining the user.
3. Send offers to the groups with the biggest gain until the budget runs out. Skip groups where the offer did nothing or made things worse.
4. Each time the churn list refreshes, send offers to the chosen groups through the pipeline.
5. Keep a small group with no offer, so we can keep measuring whether the offers still work as user behavior shifts.
## Step 8: Finding out why users left
 
The offers handle users who are about to leave, but some will still churn. Some churners will also be users we never predicted, because they showed no clear pattern. Either way, once a user has churned, the next question is why.
 
I'd work it like this:
 
1. Take the users who churned, both the ones we predicted and the ones we missed.
2. Look at their data before they left: searches per session, time taken to find something to watch, buffering or playback errors, failed payments, days since last login, and so on.
3. Put each churned user into a reason group, for example:
   - Could not find content (many searches, nothing played). In our control.
   - Playback problems (buffering, errors). In our control.
   - Payment failures. In our control.
   - Content ran out. Partly in our control.
   - Moved to a competitor, price, life changes. Mostly outside our control.
   - No clear pattern. Unknown.
4. Count the users in each group and take the groups that are in our control and have the biggest numbers. That list, with the numbers, tells the product team what to improve first.
"No clear pattern" stays its own group instead of forcing a reason on it. Its size shows how much of the churn we can currently explain.
 
An offer helps one user stay, while fixing a cause helps every future user.
 
Open problem: a user can have more than one high value at once (many searches and many playback errors, say), so putting each user into exactly one group is itself a task. Options for later are allowing more than one reason per user, or ranking the reasons.
 
A pattern isn't proof of a cause. Later we also need to check the reasons against what users say (cancellation surveys, support tickets), or test whether fixing the problem lowers churn.
 
## Things to define before building
 
While thinking through the flow, a few questions keep coming up. They decide how the model is built, so I'm noting them now and will settle each one later.
 
### 1. When do we predict?
 
For every user we know how many days are left in their subscription. We'll pick a number N and predict the churn chance N days before the subscription ends, using what similar users did when they were N days from ending. N has to leave enough time to send an offer.
 
### 2. How much past data do we use?
 
We may not use all of it. Old behavior can mislead because the platform, content and users change, so we may use only the last 2 or 3 months. Too little data can also make the model weak, so this needs checking.
 
### 3. What counts as "churned"?
 
If a subscription ends and the user comes back after a day, that isn't churn. We need a clear rule, for example: churned means the user didn't renew within X days after the subscription ended. Every label the model learns from depends on this rule, so it's the most important one to fix.
 
### 4. How does the model learn from its mistakes?
 
Once the rule in (3) is set, we compare each prediction with what actually happened (did the user churn or not). Wrong predictions are fed back so the model can be retrained, and we track whether it's getting better or worse over time.
 
### 5. Why did the user churn?
 
Users who did churn go into a reason group (Step 8). Those groups also depend on the churn rule in (3).
 
## Assumptions
 
- This is a project, so past offer experiment data isn't available. The offer vs no-offer experiment will be simulated, as if such a test had been run. I'll say so wherever the results are shown.
- Designing the actual discounts and offers is the business team's job.