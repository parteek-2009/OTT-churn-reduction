# Docs

Documentation for the OTT churn reduction project: a churn probability model plus a
separate rule layer, built for Jetflix, a fictional Netflix-like platform (US, v1).

Start with [roadmap.md](roadmap.md). It lists every stage.

## Structure

```
docs/
├── roadmap.md
├── stages/      one deliverable per roadmap stage
├── context/     stable background about the platform, the domain and the rules
├── decisions/   the reasons behind each decision
└── logs/        working notes that keep growing
```

## What each file is for

### Stages
| File | Purpose |
|---|---|
| [00-problem-framing.md](stages/00-problem-framing.md) | Target, problem, what is needed, scope |
| [01-success-metric-and-economics.md](stages/01-success-metric-and-economics.md) | Churn definition, prediction window, economics, metrics, guardrails |

### Context
| File | Purpose |
|---|---|
| [01-jetflix-platform.md](context/01-jetflix-platform.md) | How Jetflix works: plan, billing, size, economics |
| [02-domain-knowledge.md](context/02-domain-knowledge.md) | General OTT knowledge: terms, revenue, churn types, offers |
| [03-governance-and-legal.md](context/03-governance-and-legal.md) | Privacy and consent rules, and which data and features are allowed |

### Decisions
One file per decision, with the decision, the alternatives and the reasons.

| File | Decision |
|---|---|
| [001-scope-v1-to-one-region.md](decisions/001-scope-v1-to-one-region.md) | Build v1 for one region (US) |
| [002-jetflix-us-monthly-plan-and-price.md](decisions/002-jetflix-us-monthly-plan-and-price.md) | One monthly plan at $15.99 |
| [003-jetflix-cost-and-value-assumptions.md](decisions/003-jetflix-cost-and-value-assumptions.md) | Subscribers, costs, CAC, and company profit |

### Logs
| File | Purpose |
|---|---|
| [ideas.md](logs/ideas.md) | Ideas to keep, added whenever they come up |
| [experiment-log.md](logs/experiment-log.md) | Experiments and results, added from the modeling stage onward |

## Status

| Item | Status |
|---|---|
| Problem framing | Done |
| Domain knowledge | Done |
| Jetflix platform | Done |
| Decisions 001 to 003 | Done |
| Success metric and economics | In progress (churn definition done, the rest after the data) |
| Governance and legal | Starter written, fields listed at Stage 2 |
| Ideas and experiment log | Ongoing |

## Conventions
- All Jetflix numbers are assumptions set for this portfolio project, not real data.
