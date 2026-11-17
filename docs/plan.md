# Plan

**What it is:** a tool that checks whether a building's money is going where its repair plan said it would. It sorts invoices to building parts, warns when spending drifts from the plan, and lets a person review the warnings. All data is made up.

## Defaults

These are my recommendations. Change any of them before the step that uses it.

- **Data:** 20 made-up Philadelphia-area associations in 3 kinds (mid-rise condo, garden apartments, single-family HOA), 10 years of invoices (2016–2025) and a 10-year forecast.
- **Invoices:** about 3,000 with messy vendor names and memos. Roughly 70% routine upkeep, 25% for a planned building part, 5% unclear.
- **Answer key:** about 15 planted problems (early failures, cost overruns, deferred work, miscoded spend), kept out of the app's database.
- **AI:** rules first, Claude on Amazon Bedrock for the rest. Tests never call it. Ask before any live run.
- **Users:** board member (read-only), property manager (reviews), admin.
- **Stack:** Tick & Tie's runtime (FastAPI, LangGraph, React) on Postgres, deployed on AWS.

## Week 1: a demo you can send

| Day | Step | Done when |
| --- | --- | --- |
| 1 | Data model and fake-data generator | Tables migrate on Postgres. The generator makes the 20 associations, invoices and answer key. Tests pass. |
| 2 | Invoice sorting with rules | Each invoice is marked upkeep, a building part, or unsure. Accuracy is scored against the answer key. |
| 3 | AI sorting for the leftovers | Claude handles the unsure ones (stubbed in tests). Before/after accuracy and cost are reported. |
| 4 | Drift warnings | Each building part's spend is checked against plan over time. It reports how early the warnings fire and how many are false alarms. |
| 5 | Review queue | Warnings and unsure matches land in Tick & Tie's queue. Decisions are logged. |
| 6–7 | Screens | Portfolio view (who's red), association timeline (plan vs. actual, with warnings) and a results page. |

## Week 2: polish (optional)

1. A forecast of which associations run out of reserve money first.
2. Deploy on AWS (RDS, App Runner, S3 and CloudFront, Bedrock). Only with your go-ahead.
3. A 2-minute walkthrough recording and a short message to FiXA's founders.

## Rules

- Make one commit per step, and run `make test` and `make lint` before each.
- Use only made-up data, labelled as made up wherever it appears.
- Nothing goes public until you say so.
- Keep the credit to Shreyash at the top of the README.

## Settled

- Tick & Tie is separate from the user's Tech Observer work (confirmed on 2026-11-16).
